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
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": _redact(proc.stderr or proc.stdout),
            "query": soql,
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
        return {
            "ok": False,
            "returncode": proc.returncode,
            "error": _redact(proc.stderr or proc.stdout),
            "sobject": sobject,
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
        "returncode": deploy.returncode,
        "id": deploy_result.get("id") or deploy_result.get("deployId"),
        "status": deploy_result.get("status"),
        "success": deploy_result.get("success"),
        "details": deploy_result.get("details", {}),
        "stdoutTail": _redact(deploy.stdout)[-4000:],
        "stderrTail": _redact(deploy.stderr)[-4000:],
    }
    result["ok"] = deploy.returncode == 0
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
