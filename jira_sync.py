#!/usr/bin/env python3
"""Sync Jira issues into local raw JSON and normalized markdown files.

HEAL triage defaults follow CaseOps intake rules:
- JQL is used only to select open issue keys assigned to CASEOPS_DEFAULT_ASSIGNEE.
- Each issue is fetched by key with a lean triage field subset by default:
  summary, status,
  assignee, reporter, request type, description, request participants,
  portal summary, and portal description.
- Comments, changelog, worklogs, search results, and field names are paginated
  or refreshed separately.
- Attachments are downloaded to a per-issue local directory by default.
- Attached Jira Forms are retrieved through the Forms API by default when
  available.

Authentication is intentionally external to this script. It loads `.env.jira`
by default, or `CASEOPS_JIRA_ENV_FILE` when set. Prefer
JIRA_AUTH_HEADER_COMMAND with a local OAuth/session helper that prints an
Authorization header, for example:

  export JIRA_AUTH_HEADER_COMMAND='op read op://...'

Fallbacks are provided for JIRA_BEARER_TOKEN or JIRA_EMAIL + JIRA_API_TOKEN,
but no secret is stored in the repo or written to disk.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from caseops_paths import default_jira_dir, default_jira_env_file


DEFAULT_BASE_URL = os.environ.get("JIRA_BASE_URL", "https://your-company.atlassian.net")
DEFAULT_OUT_DIR = default_jira_dir(for_write=True)
DEFAULT_ENV_FILE = default_jira_env_file()
DEFAULT_ASSIGNEE = "user@example.com"
TRIAGE_REQUIRED_FIELDS = [
    "summary",
    "status",
    "assignee",
    "reporter",
    "description",
    "created",
    "updated",
    "attachment",
    "customfield_10010",  # Request Type
    "customfield_10032",  # Request participants
    "customfield_10194",  # Portal Summary
    "customfield_10195",  # Portal Description
]


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))
    auth_header = get_auth_header(args)
    base_url = (args.base_url or os.environ.get("JIRA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
    cloud_id_arg = args.cloud_id or os.environ.get("JIRA_CLOUD_ID")
    out_dir = Path(args.out_dir)

    raw_dir = out_dir / "raw"
    summary_dir = out_dir / "summary"
    attachment_dir = out_dir / "attachments"
    raw_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    attachment_dir.mkdir(parents=True, exist_ok=True)

    state_path = out_dir / "state.json"
    state = read_json_file(state_path, default={})

    print(f"Connecting to {base_url}...", flush=True)
    fields = resolve_issue_fields(args)
    jql = args.jql or default_jql()
    print(f"JQL: {jql}", flush=True)
    if args.incremental and state.get("newestUpdated"):
        base_jql = strip_order_by(jql)
        jql = f'({base_jql}) AND updated >= "{state["newestUpdated"]}" ORDER BY updated ASC'

    client = JiraClient(base_url=base_url, auth_header=auth_header)
    cloud_id = cloud_id_arg or client.get_cloud_id()

    field_map = client.get_field_map()
    write_json(out_dir / "field-map.json", field_map)
    fields = filter_known_fields(fields, field_map)

    keys = [args.issue] if args.issue else client.search_issue_keys(
        jql=jql,
        page_size=args.page_size,
        max_issues=args.max_issues,
    )
    newest_updated = state.get("newestUpdated")
    manifest_rows = []

    print(f"Found {len(keys)} issue(s). Syncing...")
    for i, key in enumerate(keys, 1):
        print(f"[{i}/{len(keys)}] {key} - fetching...", flush=True)
        issue = client.get_issue(key=key, fields=fields)
        status = get_nested(issue, ["fields", "status", "name"]) or "?"
        summary = (issue.get("fields", {}).get("summary") or "")[:60]
        print(f"[{i}/{len(keys)}] {key} - {status}: {summary}", flush=True)

        print(f"[{i}/{len(keys)}] {key} - fetching comments, changelog, worklogs...", flush=True)
        comments = client.get_paginated(f"/rest/api/3/issue/{key}/comment", "comments", args.page_size)
        changelog = client.get_paginated(f"/rest/api/3/issue/{key}/changelog", "values", args.page_size)
        worklogs = client.get_paginated(f"/rest/api/3/issue/{key}/worklog", "worklogs", args.page_size)
        attachments = []
        if not args.no_attachments:
            print(f"[{i}/{len(keys)}] {key} - downloading attachments...", flush=True)
            attachments = client.download_attachments(
                issue=issue,
                issue_attachment_dir=attachment_dir / key,
            )
        forms = []
        if not args.no_forms:
            print(f"[{i}/{len(keys)}] {key} - fetching forms...", flush=True)
            forms = client.get_attached_forms(issue_key=key, cloud_id=cloud_id)

        bundle = {
            "issue": issue,
            "comments": comments,
            "changelog": changelog,
            "worklogs": worklogs,
            "attachments": attachments,
            "forms": forms,
            "fieldNames": field_names_for_issue(fields, field_map),
            "fieldMapPath": str(out_dir / "field-map.json").replace("\\", "/"),
            "cloudId": cloud_id,
            "syncedAt": now_iso(),
        }

        write_json(raw_dir / f"{key}.json", bundle)
        (summary_dir / f"{key}.md").write_text(render_summary(bundle), encoding="utf-8")
        print(f"[{i}/{len(keys)}] {key} - written ({len(comments)} comments, {len(attachments)} attachments, {len(forms)} forms)", flush=True)

        updated = issue.get("fields", {}).get("updated")
        newest_updated = max_jira_datetime(newest_updated, updated)

        manifest_rows.append(
            {
                "Key": key,
                "Status": get_nested(issue, ["fields", "status", "name"]) or "",
                "Summary": issue.get("fields", {}).get("summary") or "",
                "Updated": updated or "",
                "RawPath": str(raw_dir / f"{key}.json").replace("\\", "/"),
                "SummaryPath": str(summary_dir / f"{key}.md").replace("\\", "/"),
                "AttachmentCount": str(len(attachments)),
                "FormCount": str(len(forms)),
            }
        )

    write_manifest(out_dir / "manifest.csv", manifest_rows)
    write_json(
        state_path,
        {
            "lastRunAt": now_iso(),
            "newestUpdated": newest_updated,
            "lastJql": jql,
            "lastIssueCount": len(keys),
        },
    )

    print(f"Synced {len(keys)} issue(s) into {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Jira issues into a local directory.")
    parser.add_argument("--base-url", help=f"Defaults to JIRA_BASE_URL or {DEFAULT_BASE_URL}.")
    parser.add_argument("--cloud-id", help="Atlassian cloud id for Forms API.")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Local ignored env file to load.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--jql",
        help="Defaults to open issues assigned to CASEOPS_DEFAULT_ASSIGNEE or JIRA_ASSIGNEE.",
    )
    parser.add_argument("--issue", help="Fetch one issue key instead of running JQL.")
    parser.add_argument("--fields", help="Comma-separated Jira fields. Overrides the default triage fields.")
    parser.add_argument("--all-fields", action="store_true", help='Fetch audit-style fields ["*all"].')
    parser.add_argument("--incremental", action="store_true", help="Add updated >= state.newestUpdated to the JQL.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-issues", type=int, help="Maximum number of issues to sync from a JQL search.")
    parser.add_argument("--no-attachments", action="store_true", help="Skip attachment file downloads.")
    parser.add_argument("--no-forms", action="store_true", help='Skip Jira "Attached forms" retrieval.')
    parser.add_argument("--auth-header-command")
    return parser.parse_args()


def default_assignee() -> str:
    return os.environ.get("CASEOPS_DEFAULT_ASSIGNEE") or os.environ.get("JIRA_ASSIGNEE") or DEFAULT_ASSIGNEE


def default_jql() -> str:
    return f'assignee = "{default_assignee()}" AND statusCategory != Done ORDER BY created ASC'


def resolve_issue_fields(args: argparse.Namespace) -> list[str]:
    if args.fields:
        return split_csv(args.fields)
    if args.all_fields:
        return ["*all"]
    return TRIAGE_REQUIRED_FIELDS


def strip_order_by(jql: str) -> str:
    match = re.search(r"\border\s+by\b", jql, re.IGNORECASE)
    if not match:
        return jql.strip()
    return jql[: match.start()].strip()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class JiraClient:
    def __init__(self, base_url: str, auth_header: str) -> None:
        self.base_url = base_url
        self.auth_header = auth_header

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header,
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Jira API error {error.code} for {path}: {details}") from error

    def request_absolute(
        self,
        method: str,
        url: str,
        *,
        accept: str = "application/json",
        experimental: bool = False,
        allow_statuses: set[int] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        headers = {
            "Accept": accept,
            "Authorization": self.auth_header,
        }
        if experimental:
            headers["X-ExperimentalApi"] = "opt-in"

        request = urllib.request.Request(url, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request) as response:
                raw_body = response.read()
                if not raw_body:
                    return None
                return json.loads(raw_body.decode("utf-8"))
        except urllib.error.HTTPError as error:
            if allow_statuses and error.code in allow_statuses:
                return {
                    "error": {
                        "status": error.code,
                        "body": error.read().decode("utf-8", errors="replace"),
                    }
                }
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Jira API error {error.code} for {url}: {details}") from error

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "*/*",
                "Authorization": self.auth_header,
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Jira attachment download error {error.code} for {url}: {details}") from error

    def get_field_map(self) -> dict[str, str]:
        fields = self.request("GET", "/rest/api/3/field")
        return {field["id"]: field.get("name", field["id"]) for field in fields}

    def get_cloud_id(self) -> str:
        tenant_info = self.request("GET", "/_edge/tenant_info")
        cloud_id = tenant_info.get("cloudId")
        if not cloud_id:
            raise RuntimeError("Could not discover Jira cloudId from /_edge/tenant_info.")
        return cloud_id

    def search_issue_keys(self, jql: str, page_size: int, max_issues: int | None = None) -> list[str]:
        try:
            return self.search_issue_keys_enhanced(jql=jql, page_size=page_size, max_issues=max_issues)
        except RuntimeError as error:
            if "Jira API error 404" not in str(error) and "Jira API error 410" not in str(error):
                raise
            return self.search_issue_keys_classic(jql=jql, page_size=page_size, max_issues=max_issues)

    def search_issue_keys_enhanced(self, jql: str, page_size: int, max_issues: int | None = None) -> list[str]:
        keys = []
        next_page_token = None

        while True:
            remaining = None if max_issues is None else max_issues - len(keys)
            if remaining is not None and remaining <= 0:
                return keys

            body = {
                "jql": jql,
                "fields": ["key", "updated"],
                "maxResults": min(page_size, remaining) if remaining is not None else page_size,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            result = self.request(
                "POST",
                "/rest/api/3/search/jql",
                body,
            )
            issues = result.get("issues", [])
            keys.extend(issue["key"] for issue in issues)
            if max_issues is not None and len(keys) >= max_issues:
                return keys[:max_issues]

            next_page_token = result.get("nextPageToken")
            if result.get("isLast", not next_page_token) or not issues:
                return keys

    def search_issue_keys_classic(self, jql: str, page_size: int, max_issues: int | None = None) -> list[str]:
        keys = []
        start_at = 0

        while True:
            remaining = None if max_issues is None else max_issues - len(keys)
            if remaining is not None and remaining <= 0:
                return keys

            body = {
                "jql": jql,
                "fields": ["key", "updated"],
                "maxResults": min(page_size, remaining) if remaining is not None else page_size,
                "startAt": start_at,
            }

            result = self.request("POST", "/rest/api/3/search", body)
            issues = result.get("issues", [])
            keys.extend(issue["key"] for issue in issues)
            if max_issues is not None and len(keys) >= max_issues:
                return keys[:max_issues]

            start_at += len(issues)
            if start_at >= result.get("total", 0) or not issues:
                return keys

    def get_issue(self, key: str, fields: list[str]) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {
                "fields": ",".join(fields),
            }
        )
        return self.request("GET", f"/rest/api/3/issue/{urllib.parse.quote(key)}?{query}")

    def get_paginated(self, path: str, item_key: str, page_size: int) -> list[dict[str, Any]]:
        items = []
        start_at = 0

        while True:
            sep = "&" if "?" in path else "?"
            result = self.request("GET", f"{path}{sep}startAt={start_at}&maxResults={page_size}")
            page_items = result.get(item_key, [])
            items.extend(page_items)

            start_at += len(page_items)
            if start_at >= result.get("total", 0) or not page_items:
                return items

    def download_attachments(self, issue: dict[str, Any], issue_attachment_dir: Path) -> list[dict[str, Any]]:
        attachments = issue.get("fields", {}).get("attachment") or []
        if not attachments:
            return []

        issue_attachment_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []

        for attachment in attachments:
            attachment_id = str(attachment.get("id") or "unknown")
            filename = safe_filename(attachment.get("filename") or f"attachment-{attachment_id}")
            local_path = issue_attachment_dir / f"{attachment_id}-{filename}"
            local_path.write_bytes(self.download(attachment["content"]))

            downloaded.append(
                {
                    "id": attachment_id,
                    "filename": attachment.get("filename"),
                    "mimeType": attachment.get("mimeType"),
                    "size": attachment.get("size"),
                    "created": attachment.get("created"),
                    "author": attachment.get("author"),
                    "content": attachment.get("content"),
                    "thumbnail": attachment.get("thumbnail"),
                    "localPath": str(local_path).replace("\\", "/"),
                }
            )

        return downloaded

    def get_attached_forms(self, issue_key: str, cloud_id: str) -> list[dict[str, Any]]:
        forms = []
        seen_form_ids = set()

        for scope in ("issue", "request"):
            index_url = forms_api_url(cloud_id, f"/{scope}/{urllib.parse.quote(issue_key)}/form")
            index = self.request_absolute(
                "GET",
                index_url,
                experimental=True,
                allow_statuses={403, 404},
            )
            if isinstance(index, dict) and "error" in index:
                forms.append({"scope": scope, "error": index["error"]})
                continue
            if not isinstance(index, list):
                continue

            for entry in index:
                form_id = entry.get("id")
                if not form_id:
                    continue
                if form_id in seen_form_ids:
                    continue
                seen_form_ids.add(form_id)

                form_path = f"/{scope}/{urllib.parse.quote(issue_key)}/form/{urllib.parse.quote(form_id)}"
                form = self.request_absolute(
                    "GET",
                    forms_api_url(cloud_id, form_path),
                    experimental=True,
                    allow_statuses={403, 404, 412},
                )
                answers = self.request_absolute(
                    "GET",
                    forms_api_url(cloud_id, f"{form_path}/format/answers"),
                    experimental=True,
                    allow_statuses={403, 404, 412},
                )
                external_data = self.request_absolute(
                    "GET",
                    forms_api_url(cloud_id, f"{form_path}/externaldata"),
                    experimental=True,
                    allow_statuses={400, 403, 404, 412},
                )
                form_attachments = self.request_absolute(
                    "GET",
                    forms_api_url(cloud_id, f"{form_path}/attachment"),
                    experimental=True,
                    allow_statuses={403, 404, 412},
                )

                forms.append(
                    {
                        "scope": scope,
                        "index": entry,
                        "form": form,
                        "answers": answers,
                        "externalData": external_data,
                        "attachmentMetadata": form_attachments,
                    }
                )

        return forms


def get_auth_header(args: argparse.Namespace) -> str:
    auth_header_command = args.auth_header_command or os.environ.get("JIRA_AUTH_HEADER_COMMAND")
    if auth_header_command:
        header = subprocess.check_output(auth_header_command, shell=True, text=True).strip()
        if header.lower().startswith("authorization:"):
            return header.split(":", 1)[1].strip()
        return header

    bearer = os.environ.get("JIRA_BEARER_TOKEN")
    if bearer:
        return f"Bearer {bearer}"

    email = os.environ.get("JIRA_EMAIL")
    api_token = os.environ.get("JIRA_API_TOKEN")
    if email and api_token:
        token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    raise RuntimeError(
        "No Jira auth found. Prefer JIRA_AUTH_HEADER_COMMAND that prints an OAuth/session Authorization header. "
        "Fallbacks: JIRA_BEARER_TOKEN or JIRA_EMAIL + JIRA_API_TOKEN."
    )


def render_summary(bundle: dict[str, Any]) -> str:
    issue = bundle["issue"]
    fields = issue.get("fields", {})
    key = issue.get("key", "")
    field_map = bundle.get("fieldNames", {})

    lines = [
        f"# {key} Jira Summary",
        "",
        f"- Summary: {fields.get('summary') or ''}",
        f"- Status: {get_nested(fields, ['status', 'name']) or ''}",
        f"- Assignee: {display_name(fields.get('assignee'))}",
        f"- Reporter: {display_name(fields.get('reporter'))}",
        f"- Request participants: {display_names(fields.get('customfield_10032'))}",
        f"- Created: {fields.get('created') or ''}",
        f"- Updated: {fields.get('updated') or ''}",
        f"- Request type: {get_nested(fields, ['customfield_10010', 'requestType', 'name']) or ''}",
        f"- System description: {plain_text(fields.get('description'))}",
        f"- Portal summary ({field_map.get('customfield_10194', 'customfield_10194')}): {plain_text(fields.get('customfield_10194'))}",
        f"- Portal description ({field_map.get('customfield_10195', 'customfield_10195')}): {plain_text(fields.get('customfield_10195'))}",
        f"- Comments: {len(bundle.get('comments', []))}",
        f"- Changelog entries: {len(bundle.get('changelog', []))}",
        f"- Worklogs: {len(bundle.get('worklogs', []))}",
        f"- Attachments: {len(bundle.get('attachments', []))}",
        f"- Attached forms: {count_available_forms(bundle.get('forms', []))}",
        "",
        "## Attachments",
        "",
    ]

    for attachment in bundle.get("attachments", []):
        lines.append(
            f"- {attachment.get('filename') or attachment.get('id')} "
            f"({attachment.get('mimeType') or 'unknown'}, {attachment.get('size') or 0} bytes): "
            f"`{attachment.get('localPath') or ''}`"
        )

    lines.extend(
        [
            "",
            "## Attached Forms",
            "",
        ]
    )

    for form in bundle.get("forms", []):
        if form.get("error"):
            lines.append(f"- {form.get('scope')} forms unavailable: HTTP {form['error'].get('status')}")
            continue

        index = form.get("index") or {}
        form_name = index.get("name") or get_nested(form, ["form", "design", "settings", "name"]) or index.get("id")
        lines.extend(
            [
                f"### {form_name}",
                "",
                f"- Scope: {form.get('scope')}",
                f"- Form id: {index.get('id') or get_nested(form, ['form', 'id']) or ''}",
                f"- Submitted: {index.get('submitted')}",
                f"- Internal: {index.get('internal')}",
                f"- Updated: {index.get('updated') or get_nested(form, ['form', 'updated']) or ''}",
                "",
            ]
        )

        answers = form.get("answers")
        if isinstance(answers, list) and answers:
            lines.append("| Field | Answer | Choice |")
            lines.append("| --- | --- | --- |")
            for answer in answers:
                lines.append(
                    f"| {escape_table(answer.get('label') or answer.get('fieldKey') or '')} "
                    f"| {escape_table(answer.get('answer') or '')} "
                    f"| {escape_table(answer.get('choice') or '')} |"
                )
            lines.append("")
        elif isinstance(answers, dict) and answers.get("error"):
            lines.append(f"Answers unavailable: HTTP {answers['error'].get('status')}")
            lines.append("")

    lines.extend(
        [
            "",
            "## Comments",
            "",
        ]
    )

    for comment in bundle.get("comments", []):
        visibility = "public" if comment.get("jsdPublic") is True else "internal/unknown"
        lines.extend(
            [
                f"### {comment.get('created', '')} - {display_name(comment.get('author'))} ({visibility})",
                "",
                plain_text(comment.get("body")),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        if value.get("type") == "doc":
            return " ".join(" ".join(extract_adf_text(value)).split())
        if "value" in value:
            return str(value["value"])
        if "name" in value:
            return str(value["name"])
    return " ".join(json.dumps(value, ensure_ascii=False).split())


def extract_adf_text(node: Any) -> list[str]:
    if isinstance(node, dict):
        pieces = []
        if node.get("type") == "text" and "text" in node:
            pieces.append(node["text"])
        for child in node.get("content", []):
            pieces.extend(extract_adf_text(child))
        return pieces
    if isinstance(node, list):
        pieces = []
        for child in node:
            pieces.extend(extract_adf_text(child))
        return pieces
    return []


def display_name(user: Any) -> str:
    if isinstance(user, dict):
        return user.get("displayName") or user.get("name") or ""
    return ""


def display_names(users: Any) -> str:
    if isinstance(users, list):
        return ", ".join(name for name in (display_name(user) for user in users) if name)
    return display_name(users)


def safe_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value)
    sanitized = sanitized.strip().strip(".")
    return sanitized or "attachment"


def forms_api_url(cloud_id: str, path: str) -> str:
    return f"https://api.atlassian.com/jira/forms/cloud/{urllib.parse.quote(cloud_id)}{path}"


def count_available_forms(forms: list[dict[str, Any]]) -> int:
    return sum(1 for form in forms if not form.get("error"))


def escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def get_nested(value: Any, path: list[str]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def field_names_for_issue(fields: list[str], field_map: dict[str, str]) -> dict[str, str]:
    if fields == ["*all"]:
        return {
            field_id: name
            for field_id, name in field_map.items()
            if field_id in TRIAGE_REQUIRED_FIELDS or field_id.startswith("customfield_")
        }

    return {field_id: field_map.get(field_id, field_id) for field_id in fields}


def filter_known_fields(fields: list[str], field_map: dict[str, str]) -> list[str]:
    if fields == ["*all"]:
        return fields

    known_fields = [field for field in fields if field in field_map]
    if not known_fields:
        raise RuntimeError("None of the requested Jira fields are available in this Jira site.")
    return known_fields


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["Key", "Status", "Summary", "Updated", "RawPath", "SummaryPath", "AttachmentCount", "FormCount"]
    # Merge: preserve existing rows for keys not in the new batch.
    existing: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                key = row.get("Key", "")
                if key:
                    existing[key] = row
    for row in rows:
        existing[row["Key"]] = row
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing.values())


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def max_jira_datetime(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return max(left, right)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
