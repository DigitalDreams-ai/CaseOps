#!/usr/bin/env python3
"""Lightweight Jira comments poller. Updates manifest.csv every 10 minutes with new comment counts."""

import base64
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).parent.parent))

from caseops_paths import default_jira_dir
from jira_sync import JiraClient

POLL_INTERVAL = 600  # 10 minutes in seconds
MANIFEST_LOCK = Lock()


def load_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    """Load manifest.csv into memory."""
    manifest = {}
    if not manifest_path.exists():
        return manifest
    try:
        with manifest_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("Key"):
                    manifest[row["Key"]] = row
    except Exception as e:
        print(f"Error reading manifest: {e}", flush=True)
    return manifest


def save_manifest(manifest_path: Path, manifest: dict[str, dict[str, str]]) -> None:
    """Save manifest.csv from memory."""
    if not manifest:
        return
    fieldnames = [
        "Key",
        "Status",
        "Assignee",
        "Summary",
        "Updated",
        "Due",
        "Priority",
        "RawPath",
        "SummaryPath",
        "AttachmentCount",
        "FormCount",
        "CommentCount",
        "HasNewComments",
        "EscalationReady",
    ]
    try:
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(manifest.values())
    except Exception as e:
        print(f"Error writing manifest: {e}", flush=True)


def poll_comments(client: JiraClient, issues: list[str], manifest: dict[str, dict[str, str]]) -> list[str]:
    """Fetch comment counts for issues. Return list of changed issue keys."""
    if not issues:
        return []

    changed_keys = []
    for key in issues:
        try:
            comments = client.get_paginated(f"/rest/api/3/issue/{key}/comment", "comments", page_size=100)
            new_count = len(comments)
            old_row = manifest.get(key, {})
            old_count = int(old_row.get("CommentCount", "0") or "0")

            # Update if count changed
            if new_count != old_count:
                manifest[key]["CommentCount"] = str(new_count)
                manifest[key]["HasNewComments"] = "true" if new_count > old_count else old_row.get(
                    "HasNewComments", "false"
                )
                changed_keys.append(key)
        except Exception as e:
            print(f"Error fetching comments for {key}: {str(e)[:100]}", flush=True)

    return changed_keys


def poll_status_and_assignee(client: JiraClient, issues: list[str], manifest: dict[str, dict[str, str]]) -> list[str]:
    """Fetch Status and Assignee for issues. Return list of changed issue keys."""
    if not issues:
        return []

    changed_keys = []
    for key in issues:
        try:
            issue = client.get_issue(key, ["status", "assignee"])
            if not issue:
                continue

            fields = issue.get("fields", {})
            new_status = fields.get("status", {}).get("name", "")
            assignee_obj = fields.get("assignee") or {}
            new_assignee = assignee_obj.get("displayName") or assignee_obj.get("name") or ""

            old_row = manifest.get(key, {})
            old_status = old_row.get("Status", "")
            old_assignee = old_row.get("Assignee", "")

            # Update if Status or Assignee changed
            if new_status != old_status or new_assignee != old_assignee:
                manifest[key]["Status"] = new_status
                manifest[key]["Assignee"] = new_assignee
                if key not in changed_keys:
                    changed_keys.append(key)
        except Exception as e:
            print(f"Error fetching status/assignee for {key}: {str(e)[:100]}", flush=True)

    return changed_keys


def signal_manifest_changed(changed_keys: list[str]) -> None:
    """Notify Flask app that manifest changed via HTTP POST."""
    if not changed_keys:
        return
    try:
        url = "http://localhost:5000/api/manifest-changed"
        data = json.dumps({"keys": changed_keys}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        print(f"Warning: Failed to signal manifest change: {str(e)[:100]}", flush=True)


def main() -> int:
    """Run comment poller loop."""
    # Load env
    env_file = Path(__file__).parent.parent / ".env.jira"
    if not env_file.exists():
        print("ERROR: .env.jira not found", file=sys.stderr, flush=True)
        return 1

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ[key] = value

    # Validate Jira auth
    base_url = os.environ.get("JIRA_BASE_URL", "").strip()
    email = os.environ.get("JIRA_EMAIL", "").strip()
    api_token = os.environ.get("JIRA_API_TOKEN", "").strip()

    if not base_url:
        print("ERROR: JIRA_BASE_URL not set in .env.jira", file=sys.stderr, flush=True)
        return 1
    if not email or not api_token:
        print("ERROR: JIRA_EMAIL and JIRA_API_TOKEN required in .env.jira", file=sys.stderr, flush=True)
        return 1

    # Build auth header (Basic auth with base64-encoded email:token)
    auth_token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
    auth_header = f"Basic {auth_token}"

    client = JiraClient(
        base_url=base_url,
        auth_header=auth_header,
    )

    jira_dir = default_jira_dir(for_write=True)
    manifest_path = jira_dir / "manifest.csv"

    print(f"[Comments Poller] Starting (poll interval: {POLL_INTERVAL}s)", flush=True)
    print(f"[Comments Poller] Manifest: {manifest_path}", flush=True)

    iteration = 0
    while True:
        try:
            iteration += 1
            with MANIFEST_LOCK:
                manifest = load_manifest(manifest_path)
                if not manifest:
                    print(f"[{iteration}] No issues in manifest yet", flush=True)
                    time.sleep(POLL_INTERVAL)
                    continue

                issues = list(manifest.keys())
                comment_changes = poll_comments(client, issues, manifest)
                status_changes = poll_status_and_assignee(client, issues, manifest)
                changed_keys = list(set(comment_changes + status_changes))

                if changed_keys:
                    save_manifest(manifest_path, manifest)
                    print(f"[{iteration}] Updated {len(changed_keys)}/{len(issues)} issues", flush=True)
                    signal_manifest_changed(changed_keys)
                else:
                    print(f"[{iteration}] No updates ({len(issues)} issues)", flush=True)
        except KeyboardInterrupt:
            print("\n[Comments Poller] Interrupted by user", flush=True)
            return 0
        except Exception as e:
            print(f"[{iteration}] Error: {str(e)[:100]}", flush=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
