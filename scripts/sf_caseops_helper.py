#!/usr/bin/env python3
"""Deterministic Salesforce helpers for CaseOps pipeline agents.

These helpers keep high-volume Salesforce mechanics out of Claude's prompt and
operator log. They intentionally use `sf` JSON output and never request visible
access tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SF_TOKEN_RE = re.compile(r"\b00D[A-Za-z0-9]{12,18}![A-Za-z0-9._~=-]{20,}\b")


def _redact(value: str) -> str:
    return SF_TOKEN_RE.sub("[REDACTED_SF_ACCESS_TOKEN]", value)


def _sf_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("SF_DISABLE_TELEMETRY", "true")
    env.setdefault("SF_AUTOUPDATE_DISABLE", "true")
    env.setdefault("SF_DISABLE_AUTOUPDATE", "true")
    env.setdefault("SF_USE_PROGRESS_BAR", "false")
    env.setdefault("SF_JSON_TO_STDOUT", "true")
    env.setdefault("NO_COLOR", "1")
    return env


def _run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    sf = shutil.which("sf")
    if not sf:
        raise RuntimeError("Salesforce CLI `sf` is not on PATH")
    if cmd and cmd[0] == "sf":
        cmd = [sf] + cmd[1:]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_sf_env(),
        timeout=timeout,
    )


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    if not text.startswith("{"):
        idx = text.find("{")
        if idx >= 0:
            text = text[idx:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_parse_error(stdout: str) -> str | None:
    text = (stdout or "").strip()
    if not text:
        return None
    if not text.startswith("{"):
        idx = text.find("{")
        if idx >= 0:
            text = text[idx:]
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return str(exc)
    return None


def _classify_failure(text: str, *, returncode: int | None = None, operation: str = "") -> tuple[str | None, bool, str]:
    lower = (text or "").lower()
    if "invalidprojectworkspaceerror" in lower or "does not contain a valid salesforce dx project" in lower:
        return "invalid_project_workspace", False, "Run workspace-init or execute the command from an issue-scoped Salesforce DX project."
    if "invalid_type" in lower or "invalid type:" in lower:
        return "invalid_query_type", False, "Verify the object or metadata type exists before retrying. Use verify-sobject, sobject-fields, describe, or a focused helper check first."
    if "permission denied" in lower and ("/app" in lower or "\\app" in lower):
        return "permission_denied_app_path", False, "Use /data or the configured CaseOps metadata workspace, not /app."
    if "invalid_field" in lower or "no such column" in lower or "didn't understand relationship" in lower:
        return "invalid_field", False, "Verify the field with verify-field or sobject-fields before retrying the query."
    if "nothingtodeploy" in lower or "nothing to deploy" in lower:
        return "nothing_to_deploy", False, "Verify the candidate directory and use deploy-mdapi for deterministic issue-scoped metadata."
    if "--source-dir" in lower and "--metadata" in lower:
        return "bad_cli_flag_combo", False, "Use either --source-dir or --metadata, not both."
    if "specify exactly one" in lower or "mutually exclusive" in lower:
        return "bad_cli_flag_combo", False, "Use one deploy/retrieve selector at a time."
    if operation == "metadata-convert" or "metadata conversion" in lower or "project convert source" in lower:
        return "metadata_conversion_failed", False, "Fix the source-format candidate package before retrying deploy."
    if "timed out" in lower or returncode == 124:
        return "timeout", True, "Retry once with a narrower operation or longer timeout; do not repeat identical broad commands."
    if returncode not in (None, 0):
        return "sf_cli_error", True, "Inspect the structured error and retry only after changing the command or scope."
    return None, False, ""


def _command_result(
    *,
    kind: str,
    proc: subprocess.CompletedProcess[str],
    command: list[str],
    operation: str = "",
    include_result: bool = True,
) -> dict[str, Any]:
    parsed = _json_from_stdout(proc.stdout)
    parse_error = _json_parse_error(proc.stdout) if proc.returncode == 0 and proc.stdout and not parsed else None
    combined = "\n".join(part for part in (proc.stderr, proc.stdout, parse_error or "") if part)
    failure_class, retryable, next_action = _classify_failure(combined, returncode=proc.returncode, operation=operation)
    ok = proc.returncode == 0 and parse_error is None
    result: dict[str, Any] = {
        "kind": kind,
        "ok": ok,
        "returncode": proc.returncode,
        "command": _redact(" ".join(command)),
        "failure_class": None if ok else (failure_class or "unknown"),
        "retryable": False if ok else retryable,
        "next_action": "" if ok else next_action,
        "stdoutTail": _redact(proc.stdout)[-4000:],
        "stderrTail": _redact(proc.stderr)[-4000:],
    }
    if parse_error:
        result["failure_class"] = "json_parse_failed"
        result["retryable"] = False
        result["next_action"] = "The CLI returned non-JSON output. Capture stderr/stdout and re-run with --json only after fixing the command."
        result["json_parse_error"] = parse_error
    if include_result and parsed:
        result["sf"] = parsed
    return result


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "salesforce"


def _write_output(out_dir: str | None, filename: str, data: dict[str, Any]) -> None:
    if not out_dir:
        return
    _write_json(Path(out_dir) / filename, data)


def _extract_primary_sobject(soql: str) -> str | None:
    match = re.search(r"\bfrom\s+([A-Za-z0-9_]+(?:__c|__mdt|__Share|Share|History)?)\b", soql or "", flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _query(org: str, soql: str, *, tooling: bool = False, timeout: int = 90) -> dict[str, Any]:
    cmd = [
        "sf",
        "data",
        "query",
        "--target-org",
        org,
        "--query",
        soql,
        "--json",
    ]
    if tooling:
        cmd.append("--use-tooling-api")
    proc = _run(cmd, timeout=timeout)
    data = _json_from_stdout(proc.stdout)
    if proc.returncode != 0:
        failure_class, retryable, next_action = _classify_failure(proc.stderr or proc.stdout, returncode=proc.returncode)
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": _redact(proc.stderr or proc.stdout),
            "query": soql,
            "failure_class": failure_class or "sf_cli_error",
            "retryable": retryable,
            "next_action": next_action,
        }
    parse_error = _json_parse_error(proc.stdout) if proc.stdout and not data else None
    if parse_error:
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": parse_error,
            "query": soql,
            "failure_class": "json_parse_failed",
            "retryable": False,
            "next_action": "The CLI returned non-JSON output. Re-run only after fixing command shape or environment noise.",
        }
    return {
        "ok": True,
        "query": soql,
        "records": data.get("result", {}).get("records", []),
        "totalSize": data.get("result", {}).get("totalSize", 0),
    }


def _describe_sobject(org: str, sobject: str, *, timeout: int = 90) -> dict[str, Any]:
    proc = _run([
        "sf",
        "sobject",
        "describe",
        "--target-org",
        org,
        "--sobject",
        sobject,
        "--json",
    ], timeout=timeout)
    data = _json_from_stdout(proc.stdout)
    if proc.returncode != 0:
        failure_class, retryable, next_action = _classify_failure(proc.stderr or proc.stdout, returncode=proc.returncode)
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": _redact(proc.stderr or proc.stdout),
            "sobject": sobject,
            "failure_class": failure_class or "sf_cli_error",
            "retryable": retryable,
            "next_action": next_action,
        }
    parse_error = _json_parse_error(proc.stdout) if proc.stdout and not data else None
    if parse_error:
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": parse_error,
            "sobject": sobject,
            "failure_class": "json_parse_failed",
            "retryable": False,
            "next_action": "The CLI returned non-JSON output. Re-run only after fixing command shape or environment noise.",
        }
    result = data.get("result", {}) if isinstance(data, dict) else {}
    return {
        "ok": True,
        "sobject": sobject,
        "fields": result.get("fields", []),
        "name": result.get("name"),
        "label": result.get("label"),
        "queryable": result.get("queryable"),
        "retrieveable": result.get("retrieveable"),
    }


def _write_json(path: Path | None, data: dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalize_field_name(field: str) -> tuple[str, str]:
    raw = field.strip()
    developer = raw[:-3] if raw.endswith("__c") else raw
    api = raw if raw.endswith("__c") else f"{raw}__c"
    return developer, api


def custom_field(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else None
    developer, api = _normalize_field_name(args.field)
    object_api = args.object
    full_name = f"{object_api}.{api}"
    result: dict[str, Any] = {
        "kind": "custom-field",
        "org": args.org,
        "object": object_api,
        "fieldDeveloperName": developer,
        "fieldApiName": api,
        "fullName": full_name,
        "ok": True,
    }

    fd = _query(
        args.org,
        "SELECT Id, DeveloperName, Label, DataType "
        f"FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = '{object_api}' "
        f"AND DeveloperName = '{developer}'",
    )
    cf = _query(
        args.org,
        "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata "
        f"FROM CustomField WHERE TableEnumOrId = '{object_api}' AND DeveloperName = '{developer}'",
        tooling=True,
    )
    result["fieldDefinition"] = fd
    result["customField"] = cf
    result["exists"] = bool(fd.get("records") or cf.get("records"))

    records = cf.get("records") or []
    metadata = records[0].get("Metadata", {}) if records else {}
    values = (
        metadata.get("valueSet", {})
        .get("valueSetDefinition", {})
        .get("value", [])
    )
    if isinstance(values, list):
        active = [v for v in values if v.get("isActive") is True]
        inactive = [v for v in values if v.get("isActive") is False or v.get("isActive") is None]
        nbsp = [
            v.get("label") or v.get("valueName") or v.get("fullName") or ""
            for v in values
            if "\xa0" in str(v.get("label", "")) or "\xa0" in str(v.get("valueName", ""))
        ]
        trailing = [
            v.get("label") or v.get("valueName") or v.get("fullName") or ""
            for v in values
            if str(v.get("label", "")).rstrip() != str(v.get("label", ""))
            or str(v.get("valueName", "")).rstrip() != str(v.get("valueName", ""))
        ]
        result["picklistSummary"] = {
            "valueCount": len(values),
            "activeCount": len(active),
            "inactiveOrNullCount": len(inactive),
            "labelsWithNbspCount": len(nbsp),
            "labelsWithTrailingWhitespaceCount": len(trailing),
            "activeLabels": [v.get("label") or v.get("valueName") for v in active],
            "inactiveOrNullLabels": [v.get("label") or v.get("valueName") for v in inactive],
        }

    if out_dir:
        _write_json(out_dir / f"{object_api}.{api}.custom-field-summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def layout(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else None
    object_api = args.object
    if args.layout_id:
        where = f"Id = '{args.layout_id}'"
    elif args.name:
        safe = args.name.replace("'", "\\'")
        where = f"TableEnumOrId = '{object_api}' AND Name = '{safe}'"
    else:
        safe = (args.contains or object_api).replace("'", "\\'")
        where = f"TableEnumOrId = '{object_api}' AND Name LIKE '%{safe}%'"

    q = _query(args.org, f"SELECT Id, Name, TableEnumOrId, Metadata FROM Layout WHERE {where}", tooling=True)
    result: dict[str, Any] = {
        "kind": "layout",
        "org": args.org,
        "object": object_api,
        "ok": q.get("ok", False),
        "query": q,
        "layouts": [],
    }
    for rec in q.get("records", []):
        metadata = rec.get("Metadata") or {}
        sections = []
        field_placements = []
        for section in metadata.get("layoutSections", []) or []:
            label = section.get("label") or ""
            fields = []
            for column in section.get("layoutColumns", []) or []:
                for item in column.get("layoutItems", []) or []:
                    field = item.get("field")
                    if field:
                        fields.append(field)
                        if args.field and field.lower() == args.field.lower():
                            field_placements.append({"section": label, "field": field})
            sections.append({"label": label, "fields": fields})
        result["layouts"].append({
            "id": rec.get("Id"),
            "name": rec.get("Name"),
            "sectionCount": len(sections),
            "sections": sections,
            "fieldPlacements": field_placements,
        })

    if out_dir:
        _write_json(out_dir / f"{object_api}.layout-summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def fls(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else None
    q = _query(
        args.org,
        "SELECT Id, Field, PermissionsRead, PermissionsEdit, ParentId, Parent.Name, Parent.Type "
        f"FROM FieldPermissions WHERE Field = '{args.field}'",
    )
    records = q.get("records", [])
    summarized = []
    for rec in records:
        parent = rec.get("Parent") or {}
        summarized.append({
            "id": rec.get("Id"),
            "field": rec.get("Field"),
            "read": bool(rec.get("PermissionsRead")),
            "edit": bool(rec.get("PermissionsEdit")),
            "parentId": rec.get("ParentId"),
            "parentName": parent.get("Name"),
            "parentType": parent.get("Type"),
        })
    result = {
        "kind": "field-permissions",
        "org": args.org,
        "field": args.field,
        "ok": q.get("ok", False),
        "total": len(summarized),
        "readEditCount": sum(1 for rec in summarized if rec["read"] and rec["edit"]),
        "readOnlyCount": sum(1 for rec in summarized if rec["read"] and not rec["edit"]),
        "records": summarized,
        "query": q if not q.get("ok") else q.get("query"),
    }
    if out_dir:
        safe_field = args.field.replace(".", "_")
        _write_json(out_dir / f"{safe_field}.fls-summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def sobject_fields(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else None
    describe = _describe_sobject(args.org, args.sobject)
    fields = []
    contains = (args.contains or "").lower()
    for field in describe.get("fields", []):
        name = str(field.get("name") or "")
        if contains and contains not in name.lower():
            continue
        fields.append({
            "name": name,
            "label": field.get("label"),
            "type": field.get("type"),
            "relationshipName": field.get("relationshipName"),
            "referenceTo": field.get("referenceTo"),
            "queryable": field.get("queryable"),
            "createable": field.get("createable"),
            "updateable": field.get("updateable"),
        })
    result = {
        "kind": "sobject-fields",
        "org": args.org,
        "sobject": args.sobject,
        "ok": describe.get("ok", False),
        "contains": args.contains,
        "fieldCount": len(fields),
        "fields": fields,
    }
    if not describe.get("ok"):
        result["describe"] = describe
    if out_dir:
        safe_sobject = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.sobject)
        suffix = f".{re.sub(r'[^A-Za-z0-9_.-]+', '_', args.contains)}" if args.contains else ""
        _write_json(out_dir / f"{safe_sobject}{suffix}.sobject-fields.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def verify_sobject(args: argparse.Namespace) -> int:
    describe = _describe_sobject(args.org, args.sobject, timeout=args.timeout)
    result: dict[str, Any] = {
        "kind": "verify-sobject",
        "org": args.org,
        "sobject": args.sobject,
        "ok": bool(describe.get("ok")),
        "exists": bool(describe.get("ok")),
        "queryable": describe.get("queryable"),
        "retrieveable": describe.get("retrieveable"),
        "label": describe.get("label"),
        "name": describe.get("name"),
    }
    if not describe.get("ok"):
        result["failure_class"] = describe.get("failure_class") or "sf_cli_error"
        result["retryable"] = describe.get("retryable", False)
        result["next_action"] = describe.get("next_action") or "Verify the object API name before retrying the query."
        result["describe"] = describe
    elif describe.get("queryable") is False:
        result["ok"] = False
        result["failure_class"] = "not_queryable"
        result["retryable"] = False
        result["next_action"] = "The object exists but is not queryable. Use describe output to choose a different access path."
    _write_output(args.out_dir, f"{_safe_name(args.sobject)}.verify-sobject.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def workspace_init(args: argparse.Namespace) -> int:
    root = Path(args.root or os.environ.get("CASEOPS_METADATA_SANDBOX_WORK_DIR") or ".").resolve()
    attempt_name = args.attempt or "attempt-001"
    issue_dir = root / args.issue_key
    attempt_dir = issue_dir / attempt_name
    paths = {
        "issueDir": issue_dir,
        "attemptDir": attempt_dir,
        "baselineSandbox": attempt_dir / "baseline-sandbox",
        "candidate": attempt_dir / "candidate",
        "revert": attempt_dir / "revert",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    manifest_path = issue_dir / "metadata-workspace.json"
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    manifest = {
        **existing,
        "kind": "metadata-workspace",
        "issueKey": args.issue_key,
        "activeAttempt": attempt_name,
        "paths": {name: str(path) for name, path in paths.items()},
    }
    _write_json(manifest_path, manifest)
    result = {
        "kind": "workspace-init",
        "ok": True,
        "issueKey": args.issue_key,
        "attempt": attempt_name,
        "manifest": str(manifest_path),
        "paths": manifest["paths"],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def query_data(args: argparse.Namespace) -> int:
    primary_sobject = _extract_primary_sobject(args.soql)
    if not args.skip_existence_check and primary_sobject:
        precheck = _describe_sobject(args.org, primary_sobject, timeout=args.timeout)
        if not precheck.get("ok"):
            result = {
                "kind": "query-data",
                "org": args.org,
                "query": args.soql,
                "ok": False,
                "failure_class": precheck.get("failure_class") or "invalid_query_type",
                "retryable": precheck.get("retryable", False),
                "next_action": precheck.get("next_action") or "Verify the object exists before retrying the query.",
                "precheck": {
                    "kind": "verify-sobject",
                    "sobject": primary_sobject,
                    "ok": False,
                },
            }
            _write_output(args.out_dir, f"{_safe_name(args.name or 'query-data')}.json", result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1
        if precheck.get("queryable") is False:
            result = {
                "kind": "query-data",
                "org": args.org,
                "query": args.soql,
                "ok": False,
                "failure_class": "not_queryable",
                "retryable": False,
                "next_action": "The object exists but is not queryable. Use describe output to choose a different access path.",
                "precheck": {
                    "kind": "verify-sobject",
                    "sobject": primary_sobject,
                    "ok": True,
                    "queryable": False,
                },
            }
            _write_output(args.out_dir, f"{_safe_name(args.name or 'query-data')}.json", result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1
    result = _query(args.org, args.soql, tooling=False, timeout=args.timeout)
    result["kind"] = "query-data"
    result["org"] = args.org
    if primary_sobject:
        result["primarySObject"] = primary_sobject
    _write_output(args.out_dir, f"{_safe_name(args.name or 'query-data')}.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def query_tooling(args: argparse.Namespace) -> int:
    result = _query(args.org, args.soql, tooling=True, timeout=args.timeout)
    result["kind"] = "query-tooling"
    result["org"] = args.org
    _write_output(args.out_dir, f"{_safe_name(args.name or 'query-tooling')}.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def retrieve_metadata(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = args.metadata or []
    source_dirs = args.source_dir or []
    result: dict[str, Any] = {
        "kind": "retrieve-metadata",
        "org": args.org,
        "outDir": str(out_dir),
        "metadata": metadata,
        "sourceDir": source_dirs,
        "ok": False,
    }
    if bool(metadata) == bool(source_dirs):
        result.update({
            "failure_class": "bad_cli_flag_combo",
            "retryable": False,
            "next_action": "Provide metadata selectors or source-dir selectors, but not both.",
        })
        _write_output(str(out_dir), "retrieve-metadata-summary.json", result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    cmd = ["sf", "project", "retrieve", "start", "--target-org", args.org, "--output-dir", str(out_dir), "--json"]
    for item in metadata:
        cmd.extend(["--metadata", item])
    for item in source_dirs:
        cmd.extend(["--source-dir", item])
    proc = _run(cmd, timeout=args.timeout)
    result["retrieve"] = _command_result(kind="retrieve-metadata-command", proc=proc, command=cmd)
    result["ok"] = bool(result["retrieve"].get("ok"))
    if not result["ok"]:
        result["failure_class"] = result["retrieve"].get("failure_class")
        result["retryable"] = result["retrieve"].get("retryable")
        result["next_action"] = result["retrieve"].get("next_action")
    _write_output(str(out_dir), "retrieve-metadata-summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def deploy_source(args: argparse.Namespace) -> int:
    source_dir = Path(args.source_dir).resolve()
    attempt = Path(args.attempt).resolve() if args.attempt else source_dir.parent
    summary_path = attempt / "deploy-source-summary.json"
    result: dict[str, Any] = {
        "kind": "deploy-source",
        "sandboxOrg": args.sandbox_org,
        "sourceDir": str(source_dir),
        "attempt": str(attempt),
        "ok": False,
    }
    cmd = [
        "sf",
        "project",
        "deploy",
        "start",
        "--source-dir",
        str(source_dir),
        "--target-org",
        args.sandbox_org,
        "--json",
    ]
    if args.test_level:
        cmd.extend(["--test-level", args.test_level])
    for test_name in args.tests or []:
        cmd.extend(["--tests", test_name])
    proc = _run(cmd, timeout=args.timeout)
    result["deploy"] = _command_result(kind="deploy-source-command", proc=proc, command=cmd)
    result["ok"] = bool(result["deploy"].get("ok"))
    if not result["ok"]:
        result["failure_class"] = result["deploy"].get("failure_class")
        result["retryable"] = result["deploy"].get("retryable")
        result["next_action"] = result["deploy"].get("next_action")
    _write_json(summary_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def deploy_report(args: argparse.Namespace) -> int:
    cmd = ["sf", "project", "deploy", "report", "--target-org", args.org, "--job-id", args.deploy_id, "--json"]
    proc = _run(cmd, timeout=args.timeout)
    result = _command_result(kind="deploy-report", proc=proc, command=cmd)
    result["org"] = args.org
    result["deployId"] = args.deploy_id
    _write_output(args.out_dir, f"deploy-report-{_safe_name(args.deploy_id)}.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def verify_field(args: argparse.Namespace) -> int:
    describe = _describe_sobject(args.org, args.sobject, timeout=args.timeout)
    fields = describe.get("fields", []) if describe.get("ok") else []
    field = next((item for item in fields if str(item.get("name") or "").lower() == args.field.lower()), None)
    result = {
        "kind": "verify-field",
        "ok": bool(describe.get("ok") and field),
        "org": args.org,
        "sobject": args.sobject,
        "field": args.field,
        "exists": bool(field),
        "fieldDefinition": field,
    }
    if not describe.get("ok"):
        result["describe"] = describe
        result["failure_class"] = describe.get("failure_class") or "sf_cli_error"
        result["retryable"] = describe.get("retryable", True)
        result["next_action"] = describe.get("next_action") or "Verify the sObject name and org alias."
    elif not field:
        result["failure_class"] = "invalid_field"
        result["retryable"] = False
        result["next_action"] = "Use sobject-fields to discover the correct API field name before retrying SOQL or metadata work."
    _write_output(args.out_dir, f"{_safe_name(args.sobject)}.{_safe_name(args.field)}.verify-field.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def verify_flow(args: argparse.Namespace) -> int:
    developer_name = args.flow
    query = (
        "SELECT Id, DeveloperName, ActiveVersionId, LatestVersionId "
        f"FROM FlowDefinition WHERE DeveloperName = '{developer_name}'"
    )
    definition = _query(args.org, query, tooling=True, timeout=args.timeout)
    records = definition.get("records", []) if definition.get("ok") else []
    result: dict[str, Any] = {
        "kind": "verify-flow",
        "ok": bool(definition.get("ok") and records),
        "org": args.org,
        "flow": developer_name,
        "exists": bool(records),
        "definition": definition,
    }
    if records:
        rec = records[0]
        active_version_id = rec.get("ActiveVersionId")
        latest_version_id = rec.get("LatestVersionId")
        result["activeVersionId"] = active_version_id
        result["latestVersionId"] = latest_version_id
        if active_version_id:
            result["activeVersion"] = _query(
                args.org,
                f"SELECT Id, VersionNumber, Status, ProcessType FROM Flow WHERE Id = '{active_version_id}'",
                tooling=True,
                timeout=args.timeout,
            )
    if not result["ok"]:
        result["failure_class"] = definition.get("failure_class") or ("missing_flow" if definition.get("ok") else "sf_cli_error")
        result["retryable"] = bool(definition.get("retryable", False))
        result["next_action"] = definition.get("next_action") or "Verify the Flow DeveloperName before retrieving or deploying Flow metadata."
    _write_output(args.out_dir, f"{_safe_name(developer_name)}.verify-flow.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def deploy_mdapi(args: argparse.Namespace) -> int:
    candidate = Path(args.candidate).resolve()
    attempt = Path(args.attempt).resolve()
    mdapi_dir = attempt / "mdapi-converted"
    summary_path = attempt / "deploy-summary.json"
    result: dict[str, Any] = {
        "kind": "deploy-mdapi",
        "sandboxOrg": args.sandbox_org,
        "candidate": str(candidate),
        "attempt": str(attempt),
        "mdapiDir": str(mdapi_dir),
        "ok": False,
    }

    source_dir = candidate / "force-app"
    if source_dir.is_dir():
        convert = _run([
            "sf",
            "project",
            "convert",
            "source",
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(mdapi_dir),
        ], timeout=120)
        result["convert"] = {
            "returncode": convert.returncode,
            "stdout": _redact(convert.stdout)[-2000:],
            "stderr": _redact(convert.stderr)[-2000:],
        }
        if convert.returncode != 0:
            failure_class, retryable, next_action = _classify_failure(
                convert.stderr or convert.stdout,
                returncode=convert.returncode,
                operation="metadata-convert",
            )
            result["failure_class"] = failure_class or "metadata_conversion_failed"
            result["retryable"] = retryable
            result["next_action"] = next_action
            _write_json(summary_path, result)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1
    else:
        mdapi_dir = candidate
        result["mdapiDir"] = str(mdapi_dir)
        result["convert"] = {"skipped": True, "reason": "candidate has no force-app directory; treating candidate as metadata-dir"}

    deploy = _run([
        "sf",
        "project",
        "deploy",
        "start",
        "--metadata-dir",
        str(mdapi_dir),
        "--single-package",
        "--target-org",
        args.sandbox_org,
        "--json",
    ], timeout=args.timeout)
    deploy_json = _json_from_stdout(deploy.stdout)
    deploy_result = deploy_json.get("result", {}) if isinstance(deploy_json, dict) else {}
    result["deploy"] = {
        **_command_result(kind="deploy-mdapi-command", proc=deploy, command=[
            "sf",
            "project",
            "deploy",
            "start",
            "--metadata-dir",
            str(mdapi_dir),
            "--single-package",
            "--target-org",
            args.sandbox_org,
            "--json",
        ]),
        "id": deploy_result.get("id") or deploy_result.get("deployId"),
        "status": deploy_result.get("status"),
        "success": deploy_result.get("success"),
        "details": deploy_result.get("details", {}),
    }
    result["ok"] = bool(result["deploy"].get("ok"))
    if not result["ok"]:
        result["failure_class"] = result["deploy"].get("failure_class")
        result["retryable"] = result["deploy"].get("retryable")
        result["next_action"] = result["deploy"].get("next_action")
    _write_json(summary_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CaseOps deterministic Salesforce helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("custom-field", help="Inspect a custom field and picklist metadata")
    p.add_argument("--org", required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--out-dir")
    p.set_defaults(func=custom_field)

    p = sub.add_parser("layout", help="Inspect Tooling Layout.Metadata and optional field placement")
    p.add_argument("--org", required=True)
    p.add_argument("--object", required=True)
    p.add_argument("--name")
    p.add_argument("--contains")
    p.add_argument("--layout-id")
    p.add_argument("--field")
    p.add_argument("--out-dir")
    p.set_defaults(func=layout)

    p = sub.add_parser("fls", help="Inspect FieldPermissions for a field")
    p.add_argument("--org", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--out-dir")
    p.set_defaults(func=fls)

    p = sub.add_parser("sobject-fields", help="Describe sObject fields before writing SOQL")
    p.add_argument("--org", required=True)
    p.add_argument("--sobject", required=True)
    p.add_argument("--contains")
    p.add_argument("--out-dir")
    p.set_defaults(func=sobject_fields)

    p = sub.add_parser("verify-sobject", help="Verify an sObject exists and is queryable before writing SOQL")
    p.add_argument("--org", required=True)
    p.add_argument("--sobject", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(func=verify_sobject)

    p = sub.add_parser("workspace-init", help="Create an issue-scoped metadata attempt workspace")
    p.add_argument("--issue-key", required=True)
    p.add_argument("--attempt", default="attempt-001")
    p.add_argument("--root")
    p.set_defaults(func=workspace_init)

    p = sub.add_parser("query-data", help="Run a data SOQL query and return structured JSON")
    p.add_argument("--org", required=True)
    p.add_argument("--soql", required=True)
    p.add_argument("--name")
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=90)
    p.add_argument("--skip-existence-check", action="store_true")
    p.set_defaults(func=query_data)

    p = sub.add_parser("query-tooling", help="Run a Tooling API SOQL query and return structured JSON")
    p.add_argument("--org", required=True)
    p.add_argument("--soql", required=True)
    p.add_argument("--name")
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(func=query_tooling)

    p = sub.add_parser("retrieve-metadata", help="Retrieve targeted metadata to an issue-scoped output directory")
    p.add_argument("--org", required=True)
    p.add_argument("--metadata", action="append")
    p.add_argument("--source-dir", action="append")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--timeout", type=int, default=180)
    p.set_defaults(func=retrieve_metadata)

    p = sub.add_parser("deploy-source", help="Deploy a source-format directory to the allowlisted sandbox")
    p.add_argument("--sandbox-org", required=True)
    p.add_argument("--source-dir", required=True)
    p.add_argument("--attempt")
    p.add_argument("--test-level")
    p.add_argument("--tests", action="append")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=deploy_source)

    p = sub.add_parser("deploy-report", help="Fetch a structured Salesforce deploy report")
    p.add_argument("--org", required=True)
    p.add_argument("--deploy-id", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=deploy_report)

    p = sub.add_parser("verify-field", help="Verify an sObject field exists before SOQL or metadata work")
    p.add_argument("--org", required=True)
    p.add_argument("--sobject", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(func=verify_field)

    p = sub.add_parser("verify-flow", help="Verify a Flow definition and active version by DeveloperName")
    p.add_argument("--org", required=True)
    p.add_argument("--flow", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=90)
    p.set_defaults(func=verify_flow)

    p = sub.add_parser("deploy-mdapi", help="Deploy candidate metadata through deterministic MDAPI path")
    p.add_argument("--sandbox-org", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--attempt", required=True)
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=deploy_mdapi)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"ok": False, "error": f"Timed out: {_redact(str(exc))}"}, indent=2), file=sys.stderr)
        return 124
    except Exception as exc:
        print(json.dumps({"ok": False, "error": _redact(str(exc))}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
