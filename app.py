#!/usr/bin/env python3
"""CaseOps browser GUI.

Run:
    python app.py
Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import base64
import copy
import csv
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from caseops_paths import default_jira_dir
from jira_sync import JiraClient, update_manifest_status
from skill_registry import SkillRegistry


class PipelineState(Enum):
    """Pipeline progression states (mutually exclusive)."""
    UNTRIAGED = "untriaged"
    INVESTIGATING = "investigating"
    ANALYZED = "analyzed"
    VALIDATED = "validated"
    ENGINEERING_HANDOFF = "engineering_handoff"
    ESCALATED_TO_ENGINEERING = "escalated_to_engineering"

try:
    import markdown as md_lib
    import re

    def _fix_single_line_tables(text: str) -> str:
        """Convert single-line markdown tables to multi-line format."""
        # Pattern: | col1 | col2 | | --- | --- | | val1 | val2 |
        # Convert to proper multi-line table
        lines = text.split('\n')
        result = []
        for line in lines:
            # Check if line contains table pipes but is clearly single-line table
            if '|' in line and ' | --- |' in line:
                # Split by pipe, filter empty, reconstruct as rows
                parts = [p.strip() for p in line.split('|')]
                parts = [p for p in parts if p]  # Remove empty parts

                # Find separator row (contains dashes)
                sep_idx = next((i for i, p in enumerate(parts) if all(c in '-:' for c in p.strip())), -1)
                if sep_idx > 0:
                    # Split into header, separator, and data rows
                    header = parts[:sep_idx]
                    separator = parts[sep_idx]
                    data_rows = parts[sep_idx+1:]

                    # Reconstruct as proper markdown table
                    result.append('| ' + ' | '.join(header) + ' |')
                    result.append('| ' + ' | '.join(['---'] * len(header)) + ' |')

                    # Add data rows (every len(header) items is one row)
                    for i in range(0, len(data_rows), len(header)):
                        row = data_rows[i:i+len(header)]
                        if len(row) == len(header):
                            result.append('| ' + ' | '.join(row) + ' |')
                else:
                    result.append(line)
            else:
                result.append(line)
        return '\n'.join(result)

    def render_md(text: str) -> str:
        text = _fix_single_line_tables(text)
        return md_lib.markdown(text, extensions=["tables", "fenced_code"])

except ImportError:
    def render_md(text: str) -> str:
        import html
        return f"<pre style='white-space:pre-wrap'>{html.escape(text)}</pre>"

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[misc, assignment]


app = Flask(__name__)
ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"

# Set in `.env.jira`: how CaseOps passes auth to the `claude` subprocess (see caseops_llm_auth_uses_anthropic_api_key).
CASEOPS_LLM_AUTH_ENV = "CASEOPS_LLM_AUTH"

# ---------------------------------------------------------------------------
# Phase 2: In-memory caches (session-local, no Redis, 100-key LRU limit)
# ---------------------------------------------------------------------------
# Jira summary cache: key → {"html": str, "raw": str}
jira_summary_cache: dict[str, dict[str, str]] = {}

# Investigation file-flag cache: key → {"has_investigation": bool, "has_solution": bool}
investigation_cache: dict[str, dict[str, bool]] = {}

# Artifact metadata cache: "type:api_name" → {"id": "...", "expires": timestamp}
# TTL: 24 hours
artifact_metadata_cache: dict[str, dict[str, Any]] = {}

_CACHE_MAX_KEYS = 100
_ARTIFACT_CACHE_TTL_SECONDS = 86400  # 24 hours

# Skill registry: loads all skills once at startup, reuses cached data
skill_registry = SkillRegistry()

# Skill paths: registered at startup and passed to subprocesses via env vars
# Maps skill_name → absolute path to skill directory
SKILL_PATHS: dict[str, str] = {}

# Salesforce org cache: one-time auth validation per run (prevents sf org list re-runs)
# Stores: {"10xhealth": {...}, "10xhealth-sean": {...}}
_sf_orgs_cache: dict[str, dict[str, str]] | None = None
_sf_orgs_cache_time = 0
_SF_ORGS_CACHE_TTL = 600  # Cache for 10 minutes
_settings_status_cache: dict[str, Any] | None = None
_settings_status_cache_time = 0.0
_settings_status_refreshing = False
_SETTINGS_STATUS_CACHE_TTL = 120
_SETTINGS_STATUS_LOCK = threading.Lock()

_ENV_KEYS_RELOAD_FROM_FILE = {
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    CASEOPS_LLM_AUTH_ENV,
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_AUTH_HEADER_COMMAND",
    "JIRA_BEARER_TOKEN",
    "CASEOPS_ANTHROPIC_MODEL",
    "CASEOPS_USE_CCI_FOR_AUTH",
    "CASEOPS_PRODUCTION_READ_ORG",
    "CASEOPS_SANDBOX_TARGET_ORG",
    "CASEOPS_PRODUCTION_INSTANCE_URL",
    "CASEOPS_SANDBOX_INSTANCE_URL",
    "CASEOPS_PRODUCTION_MAGIC_LINK",
    "CASEOPS_SANDBOX_MAGIC_LINK",
    "SF_PROD_ACCESS_TOKEN",
    "SF_SANDBOX_ACCESS_TOKEN",
    "SF_PROD_REFRESH_TOKEN",
    "SF_SANDBOX_REFRESH_TOKEN",
    "SF_TOKENS_REFRESHED_AT",
    "SF_PROD_INSTANCE_URL",
    "SF_SANDBOX_INSTANCE_URL",
}

# Consolidated temp directory: instance-specific runtime workspace
TEMP_ROOT = None  # Path | None — Set in __main__


_ORG_KNOWLEDGE_DEFAULT_INDEX: dict[str, Any] = {
    "version": 1,
    "description": "CaseOps reusable Salesforce org knowledge. The orchestrator reads this index, then loads only matching files for each issue.",
    "always_read": ["run-rules.md"],
    "max_context_chars": 12000,
    "max_topic_files": 6,
    "topics": [
        {
            "id": "custom-field-picklist",
            "title": "Custom fields and picklist values",
            "keywords": [
                "custom field", "fielddefinition", "customfield", "picklist", "picklist value",
                "__c", "field-level", "field level", "supplement", "values"
            ],
            "files": [
                "helper-scripts.md",
                "query-patterns/custom-field.md",
                "query-patterns/picklist-values.md",
                "deploy-patterns/custom-field-mdapi.md",
            ],
        },
        {
            "id": "layouts",
            "title": "Layouts and field placement",
            "keywords": ["layout", "page layout", "section", "field placement", "lightning page"],
            "files": ["helper-scripts.md", "query-patterns/layouts.md"],
        },
        {
            "id": "permission-sets",
            "title": "Permission sets and FLS",
            "keywords": [
                "permission set", "permissionset", "fls", "fieldpermissions", "field permission",
                "read edit", "read/write", "access", "profile"
            ],
            "files": ["helper-scripts.md", "query-patterns/permission-sets.md"],
        },
        {
            "id": "deploy-troubleshooting",
            "title": "Deploy mechanics and source tracking pitfalls",
            "keywords": [
                "deploy", "sandbox", "metadata api", "mdapi", "nothingtodeploy", "source tracking",
                "candidate", "baseline", "revert", "gearset"
            ],
            "files": [
                "helper-scripts.md",
                "deploy-patterns/custom-field-mdapi.md",
                "deploy-patterns/source-tracking.md",
            ],
        },
        {
            "id": "flows",
            "title": "Flow investigation",
            "keywords": ["flow", "flowdefinition", "flow version", "triggered flow", "record-triggered"],
            "files": ["query-patterns/flows.md"],
        },
        {
            "id": "apex",
            "title": "Apex investigation",
            "keywords": ["apex", "class", "trigger", "test class", "debug log"],
            "files": ["query-patterns/apex.md"],
        },
    ],
}


_ORG_KNOWLEDGE_DEFAULT_FILES: dict[str, str] = {
    "helper-scripts.md": """# CaseOps Salesforce Helper Scripts

Use deterministic helpers before improvising Salesforce CLI/SOQL/curl commands.

Helper entrypoint:

```bash
python scripts/sf_caseops_helper.py --help
```

Available helpers:

```bash
python scripts/sf_caseops_helper.py custom-field --org "$ORG" --object Case --field Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py layout --org "$ORG" --object Case --contains "Customer Experience" --field Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py fls --org "$ORG" --field Case.Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py deploy-mdapi --sandbox-org "$SANDBOX_ORG" --candidate "$CANDIDATE" --attempt "$ATTEMPT"
```

Rules:

- Run helpers first for custom field, picklist, layout, FLS, and custom-field MDAPI deploy work.
- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands.
- Do not use `package.xml` or `--manifest` for routine CaseOps retrieve/deploy. Use `--metadata`, `--source-dir`, or `--metadata-dir`.
- Helpers write compact JSON summaries into the issue-scoped directory and avoid raw access-token output.
- If a helper fails, inspect the helper summary/error and replan. Do not try many ad hoc variants of the same query.
""",
    "run-rules.md": """# CaseOps Org Knowledge Run Rules

These rules are always safe to include in Salesforce pipeline runs.

- Read this file plus only the topic files selected by `index.json`; do not bulk-read the entire org-knowledge directory.
- Use org knowledge to avoid relearning Salesforce CLI behavior. Prefer the known pattern first, then investigate only if the known pattern fails.
- Use `python scripts/sf_caseops_helper.py ...` helpers first for known Salesforce mechanics before writing ad hoc SOQL/curl/Python snippets.
- Use `sf` CLI and SOQL for Salesforce API work. Do not use frontdoor links, magic links, or browser session IDs for API, SOQL, retrieve, deploy, or tests.
- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands. Do not use `package.xml` or `--manifest` unless the operator explicitly approves a metadata-type exception.
- Never print, export, or embed raw Salesforce access tokens. Do not run `SF_TEMP_SHOW_SECRETS=true sf org display`. If a REST call is unavoidable, use an internal helper that does not log the token.
- Stay inside the current issue workspace. Do not inspect other `HEAL-*` metadata or output directories unless the operator explicitly asks for cross-issue comparison.
- Stop after two failed variants of the same query/deploy pattern. Replan using the selected org knowledge instead of trying many small variations.
- Prefer `--json` output and parse concise fields. Do not read full persisted deploy/retrieve logs unless the concise status is insufficient.
- When a run discovers a durable, verified, reusable fact, update the most relevant org-knowledge topic file with one short bullet. Do not store secrets or customer-specific narrative.
""",
    "query-patterns/custom-field.md": """# Custom Field Query Pattern

Use these patterns before experimenting.

## Find a custom field

FieldDefinition commonly uses DeveloperName without the `__c` suffix:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, DeveloperName, Label, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = 'Case' AND DeveloperName = 'Field_Name'"
```

Tooling `CustomField` is often better for metadata details:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata FROM CustomField WHERE TableEnumOrId = 'Case' AND DeveloperName = 'Field_Name'"
```

Notes:

- `CustomField.DeveloperName` usually omits `__c`; `FullName` includes `Object.Field__c`.
- Use the returned `00N...` Id for Salesforce artifact links.
- Save large JSON to the issue-scoped metadata directory and summarize it; do not paste full metadata into the operator log.
""",
    "query-patterns/picklist-values.md": """# Picklist Value Query Pattern

Avoid repeated `PicklistValueInfo` experiments. In this org it can fail with unsupported fields, complicated filters, or zero rows depending on endpoint and filter shape.

Preferred path for custom picklist truth:

1. Run `python scripts/sf_caseops_helper.py custom-field --org "$ORG" --object Case --field Field_Name__c --out-dir "$RAW_DIR"`.
2. If the helper cannot answer the question, resolve the field through Tooling `CustomField`.
3. Inspect `CustomField.Metadata.valueSet.valueSetDefinition.value`.
4. If active/default behavior is ambiguous, perform Metadata API retrieve or a UI/API describe check and record which source was authoritative.

Example:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata FROM CustomField WHERE TableEnumOrId = 'Case' AND DeveloperName = 'Field_Name'" > "$RAW_DIR/Case.Field_Name__c.json"
```

Comparison guidance:

- Compare requested labels after trimming whitespace and normalizing non-breaking spaces.
- Detect merged values by comparing requested count vs actual count and by checking adjacent requested labels.
- Do not assume one source is definitive when it conflicts with user-visible behavior; verify with a second source and summarize.
""",
    "query-patterns/layouts.md": """# Layout Query Pattern

For layout section and field placement checks, Tooling `Layout.Metadata` is often faster and cleaner than repeated `sf project retrieve` attempts.

Preferred helper:

```bash
python scripts/sf_caseops_helper.py layout --org "$ORG" --object Case --contains "Customer Experience" --field Field_Name__c --out-dir "$RAW_DIR"
```

Find Case layouts:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, TableEnumOrId FROM Layout WHERE TableEnumOrId = 'Case'"
```

Fetch layout metadata:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, Metadata FROM Layout WHERE Id = '00h...'" > "$RAW_DIR/Case-Customer_Experience_layout.json"
```

Then parse `Metadata.layoutSections[].layoutColumns[].layoutItems[].field`.

Rules:

- Distinguish a section label from a nearby field label. A field beside `Call_Details__c` is not automatically in a section named `Call Details`.
- If an acceptance criterion names a section that does not exist, document both the actual placement and the ambiguity.
""",
    "query-patterns/permission-sets.md": """# Permission Set and FLS Query Pattern

Resolve candidate permission sets first:

Preferred helper:

```bash
python scripts/sf_caseops_helper.py fls --org "$ORG" --field Case.Field_Name__c --out-dir "$RAW_DIR"
```

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, Name, Label FROM PermissionSet WHERE Name LIKE '%Customer%' OR Label LIKE '%Customer%'"
```

Check FLS with parent details:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, Field, PermissionsRead, PermissionsEdit, ParentId, Parent.Name, Parent.Type FROM FieldPermissions WHERE Field = 'Case.Field_Name__c'"
```

Guidance:

- Report Read+Edit vs Read-only separately.
- Ignore session/profile-like permission records only when they are not part of the requested audience, and say why.
- If the customer asked for a team, map labels to that team explicitly instead of assuming every matching permission set is in scope.
""",
    "query-patterns/flows.md": """# Flow Query Pattern

Use Tooling queries to resolve FlowDefinition and active versions before retrieving full XML.

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, DeveloperName, ActiveVersionId, LatestVersionId FROM FlowDefinition WHERE DeveloperName = 'Flow_API_Name'"
```

Retrieve full metadata only for the flow(s) implicated by the issue. Do not retrieve every flow unless the issue is explicitly broad.
""",
    "query-patterns/apex.md": """# Apex Query Pattern

Resolve Apex classes/triggers with Tooling API before reading or testing broadly.

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, Status FROM ApexClass WHERE Name = 'ClassName'"
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, TableEnumOrId, Status FROM ApexTrigger WHERE Name = 'TriggerName'"
```

Run targeted tests first. Broad test runs need a clear reason.
""",
    "deploy-patterns/custom-field-mdapi.md": """# Custom Field Deploy Pattern

If source deploy returns `NothingToDeploy` or appears affected by source tracking, do not inspect `.sf` internals for long. Use the deterministic `sf project deploy start --metadata-dir ...` path.

Preferred helper:

```bash
python scripts/sf_caseops_helper.py deploy-mdapi --sandbox-org "$SANDBOX_ORG" --candidate "$CANDIDATE" --attempt "$ATTEMPT"
```

Preferred sequence:

1. Build candidate source under the issue attempt directory.
2. Do not create or use `package.xml` for routine CaseOps deploys. Prefer explicit `--source-dir`, `--metadata`, or `--metadata-dir`.
3. Convert source to metadata-dir when possible:

```bash
sf project convert source --source-dir "$CANDIDATE/force-app" --output-dir "$ATTEMPT/mdapi-converted"
```

4. Deploy with metadata-dir:

```bash
sf project deploy start --metadata-dir "$ATTEMPT/mdapi-converted" --single-package --target-org "$SANDBOX_ORG" --json
```

Rules:

- Use only the allowlisted Sandbox org for deploys.
- Do not deploy to Production from CaseOps.
- Capture concise deploy status and deploy id. Do not read thousands of progress lines.
- If conversion/deploy fails twice, stop and summarize the exact blocker rather than trying many variants.
""",
    "deploy-patterns/source-tracking.md": """# Source Tracking Pitfalls

Sandbox source tracking can make a valid metadata change look like `NothingToDeploy`.

Rules:

- Do not delete or inspect `.sf` tracking internals unless the operator specifically requests it.
- Prefer `sf project deploy start --metadata-dir ... --single-package --json` for deterministic issue-scoped packages.
- Treat source tracking as a deploy mechanism detail, not as evidence that the candidate is empty.
""",
    "lessons-learned.md": """# Org Knowledge Lessons Learned

Append only durable, verified, reusable lessons here when no more specific topic file fits.

Format:

- YYYY-MM-DD: Short reusable lesson. Evidence source: CLI/SOQL/metadata. No secrets. No customer narrative.
""",
}


_ORG_KNOWLEDGE_REQUIRED_LINES: dict[str, list[str]] = {
    "run-rules.md": [
        "- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands. Do not use `package.xml` or `--manifest` unless the operator explicitly approves a metadata-type exception.",
    ],
    "helper-scripts.md": [
        "- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands.",
        "- Do not use `package.xml` or `--manifest` for routine CaseOps retrieve/deploy. Use `--metadata`, `--source-dir`, or `--metadata-dir`.",
    ],
    "deploy-patterns/custom-field-mdapi.md": [
        "2. Do not create or use `package.xml` for routine CaseOps deploys. Prefer explicit `--source-dir`, `--metadata`, or `--metadata-dir`.",
    ],
}


def _metadata_workspace_dirs() -> dict[str, Path]:
    """Return the instance-scoped Salesforce metadata workspace directories."""
    base_temp = TEMP_ROOT if TEMP_ROOT is not None else OUTPUTS.parent / ".temp"
    root = base_temp / "metadata"
    return {
        "root": root,
        "raw_prod": root / "raw-production",
        "sandbox_work": root / "sandbox-work",
        "confirmed": root / "confirmed",
    }


def _ensure_metadata_workspace_dirs() -> None:
    """Create the shared directory contract used by Salesforce pipeline agents."""
    for path in _metadata_workspace_dirs().values():
        path.mkdir(parents=True, exist_ok=True)


def _org_knowledge_dir() -> Path:
    """Return the instance-scoped reusable org knowledge directory."""
    return OUTPUTS / "org-knowledge"


def _merge_org_knowledge_index(index: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Merge new default topic wiring without replacing operator-edited content."""
    if not isinstance(index, dict):
        return copy.deepcopy(_ORG_KNOWLEDGE_DEFAULT_INDEX), True

    merged = copy.deepcopy(index)
    changed = False

    for key in ("version", "description", "max_context_chars", "max_topic_files"):
        if key not in merged:
            merged[key] = copy.deepcopy(_ORG_KNOWLEDGE_DEFAULT_INDEX.get(key))
            changed = True

    existing_always = merged.get("always_read")
    if not isinstance(existing_always, list):
        merged["always_read"] = copy.deepcopy(_ORG_KNOWLEDGE_DEFAULT_INDEX["always_read"])
        changed = True
    else:
        for rel in _ORG_KNOWLEDGE_DEFAULT_INDEX["always_read"]:
            if rel not in existing_always:
                existing_always.append(rel)
                changed = True

    topics = merged.get("topics")
    if not isinstance(topics, list):
        merged["topics"] = copy.deepcopy(_ORG_KNOWLEDGE_DEFAULT_INDEX["topics"])
        return merged, True

    existing_by_id = {
        topic.get("id"): topic
        for topic in topics
        if isinstance(topic, dict) and isinstance(topic.get("id"), str)
    }
    for default_topic in _ORG_KNOWLEDGE_DEFAULT_INDEX["topics"]:
        topic_id = default_topic.get("id")
        existing_topic = existing_by_id.get(topic_id)
        if not existing_topic:
            topics.append(copy.deepcopy(default_topic))
            changed = True
            continue

        for key in ("title", "keywords", "files"):
            if key not in existing_topic:
                existing_topic[key] = copy.deepcopy(default_topic.get(key))
                changed = True

        for list_key in ("keywords", "files"):
            current = existing_topic.get(list_key)
            if not isinstance(current, list):
                existing_topic[list_key] = copy.deepcopy(default_topic.get(list_key, []))
                changed = True
                continue
            for item in default_topic.get(list_key, []):
                if item not in current:
                    current.append(item)
                    changed = True

    return merged, changed


def _ensure_org_knowledge_defaults() -> None:
    """Seed editable org knowledge files without overwriting user updates."""
    root = _org_knowledge_dir()
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.json"
    if not index_path.exists():
        index_path.write_text(
            json.dumps(_ORG_KNOWLEDGE_DEFAULT_INDEX, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    for rel, content in _ORG_KNOWLEDGE_DEFAULT_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    for rel, lines in _ORG_KNOWLEDGE_REQUIRED_LINES.items():
        path = root / rel
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        missing = [line for line in lines if line not in existing]
        if missing:
            suffix = "\n" if existing and not existing.endswith("\n") else ""
            path.write_text(existing + suffix + "\n".join(missing) + "\n", encoding="utf-8")
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    merged, changed = _merge_org_knowledge_index(data if isinstance(data, dict) else {})
    if changed:
        index_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _read_org_knowledge_index() -> dict[str, Any]:
    _ensure_org_knowledge_defaults()
    index_path = _org_knowledge_dir() / "index.json"
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _ORG_KNOWLEDGE_DEFAULT_INDEX
    return data if isinstance(data, dict) else _ORG_KNOWLEDGE_DEFAULT_INDEX


def _read_small_text(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:max_chars]


def _issue_org_knowledge_search_text(key: str, row: dict[str, str]) -> str:
    parts = [
        key,
        row.get("Summary", ""),
        row.get("Status", ""),
        _read_small_text(OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key), 12000),
        _read_small_text(OUTPUTS / FILE_LOCATIONS["step4_hypothesis"].format(key=key), 8000),
        _read_small_text(OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key), 12000),
    ]
    return "\n".join(part for part in parts if part).lower()


def _select_org_knowledge_files(key: str, row: dict[str, str]) -> list[Path]:
    """Select only the org-knowledge files relevant to this issue."""
    index = _read_org_knowledge_index()
    root = _org_knowledge_dir()
    selected: list[str] = []
    always_read = [rel for rel in index.get("always_read", []) if isinstance(rel, str)]
    always_read_set = set(always_read)
    for rel in always_read:
        if isinstance(rel, str) and rel not in selected:
            selected.append(rel)

    search_text = _issue_org_knowledge_search_text(key, row)
    topic_scores: list[tuple[int, str, list[str]]] = []
    for topic in index.get("topics", []):
        if not isinstance(topic, dict):
            continue
        files = [str(f) for f in topic.get("files", []) if isinstance(f, str)]
        if not files:
            continue
        score = 0
        for keyword in topic.get("keywords", []):
            if isinstance(keyword, str) and keyword.lower() in search_text:
                score += 1
        if score:
            topic_scores.append((score, str(topic.get("id", "")), files))

    max_topic_files = int(index.get("max_topic_files") or 6)
    for _score, _topic_id, files in sorted(topic_scores, key=lambda item: (-item[0], item[1])):
        for rel in files:
            if rel not in selected:
                selected.append(rel)
            topic_file_count = sum(1 for relpath in selected if relpath not in always_read_set)
            if topic_file_count >= max_topic_files:
                break
        topic_file_count = sum(1 for relpath in selected if relpath not in always_read_set)
        if topic_file_count >= max_topic_files:
            break

    paths: list[Path] = []
    for rel in selected:
        path = (root / rel).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file():
            paths.append(path)
    return paths


def _build_org_knowledge_context_block(key: str, row: dict[str, str]) -> str:
    """Build a capped progressive-disclosure context block for Claude runs."""
    index = _read_org_knowledge_index()
    paths = _select_org_knowledge_files(key, row)
    max_chars = int(index.get("max_context_chars") or 12000)
    remaining = max(4000, max_chars)
    chunks: list[str] = []
    rel_paths: list[str] = []
    root = _org_knowledge_dir()

    for path in paths:
        rel = path.relative_to(root).as_posix()
        rel_paths.append(f"- `{_path_relative_for_prompt(path)}`")
        if remaining <= 0:
            continue
        text = _read_small_text(path, min(remaining, 3500)).strip()
        if not text:
            continue
        remaining -= len(text)
        chunks.append(f"### {rel}\n{text}")

    selected_list = "\n".join(rel_paths) if rel_paths else "- None selected"
    content = "\n\n".join(chunks) if chunks else "(No org knowledge content selected.)"
    return (
        "## Org Knowledge Context (selected, progressive disclosure)\n"
        f"Org knowledge directory: `{_path_relative_for_prompt(root)}`\n"
        "CaseOps selected only the reusable files below for this issue. Do not bulk-read the org-knowledge directory.\n"
        "When spawning Step 5, Step 6, Step 8, or Step 9 sub-agents, include the relevant bullets from this section in the sub-agent prompt so the sub-agent does not relearn known Salesforce CLI behavior.\n\n"
        f"Selected files:\n{selected_list}\n\n"
        f"{content}\n\n"
        "Learning rule: if this run discovers a durable, verified, reusable org fact, update the most specific selected topic file with one short bullet. Do not store secrets, access tokens, frontdoor links, or customer-private narrative.\n\n"
    )


def _cache_evict(cache: dict) -> None:
    """Evict oldest entries when cache exceeds _CACHE_MAX_KEYS."""
    while len(cache) > _CACHE_MAX_KEYS:
        cache.pop(next(iter(cache)))


def _persistent_canned_messages_file() -> Path:
    """Return the writable, mounted canned-message customization path.

    In Docker/NAS deployments only OUTPUTS is mounted persistently. Root-level files
    inside /app are image/container state and are lost on container replacement.
    """
    return OUTPUTS / "settings" / "canned-messages.json"


def _legacy_canned_messages_file() -> Path | None:
    """Return the old workspace-specific canned-message path, if applicable."""
    workspace = app.config.get("WORKSPACE") or os.environ.get("CASEOPS_WORKSPACE", "default")
    if workspace and workspace != "default":
        return ROOT / workspace / "canned-messages.json"
    legacy_instance_file = OUTPUTS.parent / "canned-messages.json"
    if legacy_instance_file != ROOT / "canned-messages.json":
        return legacy_instance_file
    return None


def _active_canned_messages_file() -> tuple[Path, bool]:
    """Return the file to read and whether it is a custom/persistent override."""
    persistent = _persistent_canned_messages_file()
    if persistent.exists():
        return persistent, True

    legacy = _legacy_canned_messages_file()
    if legacy and legacy.exists():
        return legacy, True

    return ROOT / "canned-messages.json", False


def _refresh_salesforce_token_from_refresh_token(instance_url: str, refresh_token: str, client_id: str = "PlatformCLI") -> tuple[bool, str | None]:
    """Use Salesforce OAuth 2.0 refresh_token grant to get a new access token.

    Returns: (success, new_access_token or error_message)
    """
    if not refresh_token:
        return False, "No refresh token"

    try:
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }).encode("utf-8")

        token_url = f"{instance_url.rstrip('/')}/services/oauth2/token"
        req = urllib.request.Request(token_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            new_token = result.get("access_token")
            if new_token:
                return True, new_token
            return False, result.get("error_description", "No access_token in response")
    except Exception as e:
        return False, str(e)


def _extract_salesforce_refresh_token(value: str | None) -> str:
    """Accept a raw refresh token or an SFDX auth URL and return the refresh token."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("force://"):
        match = re.match(r"^force://[^:]*:[^:]*:([^@]+)@.+$", raw)
        if match:
            return urllib.parse.unquote(match.group(1))
    return raw


def _env_first(*keys: str, settings: dict[str, str] | None = None, default: str = "") -> str:
    """Return the first non-empty value from os.environ or an optional parsed env file."""
    settings = settings or {}
    for key in keys:
        value = os.environ.get(key) or settings.get(key) or ""
        if str(value).strip():
            return str(value).strip()
    return default


def _check_and_refresh_salesforce_tokens(env_file_path: Path) -> None:
    """Check SF token age. Auto-refresh if expiring/expired, warn on failure but don't crash."""
    try:
        env_content = env_file_path.read_text(encoding="utf-8")

        # Extract timestamp and tokens
        match_ts = re.search(r'SF_TOKENS_REFRESHED_AT=(\d+)', env_content)
        match_prod_token = re.search(r'SF_PROD_REFRESH_TOKEN=([^\n]+)', env_content)
        match_sandbox_token = re.search(r'SF_SANDBOX_REFRESH_TOKEN=([^\n]+)', env_content)

        now = int(time.time())

        # If timestamp missing, initialize it now and attempt refresh if refresh tokens exist
        if not match_ts:
            print("[WARN] SF_TOKENS_REFRESHED_AT not in .env.jira. Initializing...")
            if match_prod_token or match_sandbox_token:
                _attempt_token_refresh(env_file_path, env_content, match_prod_token, match_sandbox_token)
            else:
                # No refresh tokens, just set timestamp
                lines = env_content.split("\n")
                new_lines = [l for l in lines if not l.startswith("SF_TOKENS_REFRESHED_AT=")]
                new_lines.append(f"SF_TOKENS_REFRESHED_AT={now}")
                env_file_path.write_text("\n".join(new_lines), encoding="utf-8")
                print("[WARN] No refresh tokens available. Manual token refresh required every 8h.")
            return

        refreshed_at = int(match_ts.group(1))
        age_hours = (now - refreshed_at) / 3600

        # Warn if expired, but don't crash - let API handle auth
        if age_hours > 8:
            print(f"[WARN] Salesforce tokens EXPIRED ({age_hours:.1f}h old). Auto-refresh will attempt on next API call.")
            if match_prod_token or match_sandbox_token:
                _attempt_token_refresh(env_file_path, env_content, match_prod_token, match_sandbox_token)
            return

        # Auto-refresh if <4h left (4h into 8h TTL) or expired
        if age_hours > 4:
            print(f"[*] Salesforce tokens {age_hours:.1f}h old (<4h until expiry). Auto-refreshing...")
            _attempt_token_refresh(env_file_path, env_content, match_prod_token, match_sandbox_token)
            return

        if age_hours > 6:
            print(f"[WARN] Tokens {age_hours:.1f}h old. <2h until auto-refresh needed.")
        else:
            print(f"[OK] Salesforce tokens valid ({age_hours:.1f}h old, auto-refresh at 4h)")

    except Exception as e:
        print(f"[WARN] Token refresh check failed: {e}")


def _attempt_token_refresh(env_file_path: Path, env_content: str, prod_token_match, sandbox_token_match) -> None:
    """Attempt to refresh SF tokens using refresh tokens. Update .env on success."""
    prod_ok, prod_new = False, None
    sandbox_ok, sandbox_new = False, None
    settings = _read_env_file(env_file_path)
    prod_url = _env_first(
        "SF_PROD_INSTANCE_URL",
        "CASEOPS_PRODUCTION_INSTANCE_URL",
        settings=settings,
        default="https://login.salesforce.com",
    )
    sandbox_url = _env_first(
        "SF_SANDBOX_INSTANCE_URL",
        "CASEOPS_SANDBOX_INSTANCE_URL",
        settings=settings,
        default="https://test.salesforce.com",
    )

    if prod_token_match:
        prod_ok, prod_new = _refresh_salesforce_token_from_refresh_token(
            prod_url,
            _extract_salesforce_refresh_token(prod_token_match.group(1))
        )

    if sandbox_token_match:
        sandbox_ok, sandbox_new = _refresh_salesforce_token_from_refresh_token(
            sandbox_url,
            _extract_salesforce_refresh_token(sandbox_token_match.group(1))
        )

    if prod_ok or sandbox_ok:
        # Update .env.jira with new tokens and timestamp
        lines = env_content.split("\n")
        new_lines = [l for l in lines if not l.startswith(("SF_PROD_ACCESS_TOKEN=", "SF_SANDBOX_ACCESS_TOKEN=", "SF_TOKENS_REFRESHED_AT="))]
        if prod_new:
            new_lines.append(f"SF_PROD_ACCESS_TOKEN={prod_new}")
        if sandbox_new:
            new_lines.append(f"SF_SANDBOX_ACCESS_TOKEN={sandbox_new}")
        new_lines.append(f"SF_TOKENS_REFRESHED_AT={int(time.time())}")
        env_file_path.write_text("\n".join(new_lines), encoding="utf-8")
        _load_jira_env(env_file_path)
        print(f"[OK] Salesforce tokens auto-refreshed (prod={prod_ok}, sandbox={sandbox_ok})")
    else:
        print(f"[WARN] Auto-refresh failed (prod: {prod_new}, sandbox: {sandbox_new})")


def _instance_cache_key(key: str) -> str:
    """Generate instance-specific cache key to prevent cross-instance contamination.

    Prefixes key with current WORKSPACE so instance1 and instance2 don't share cache entries.
    """
    workspace = os.environ.get("CASEOPS_WORKSPACE", "default")
    return f"{workspace}:{key}"


def _validate_instance_path(path: Path, operation: str = "write") -> None:
    """Hard rule: Prevent writes/operations to shared directories.

    CRITICAL for multi-instance isolation. Raises RuntimeError if path violates
    instance-routing rules.

    Allowed patterns:
    - OUTPUTS / ... (instance-specific outputs)
    - instance1/ ... (instance1 state)
    - instance2/ ... (instance2 state)
    - skills/ ... (shared read-only)
    - static/ ... (shared read-only)
    - templates/ ... (shared read-only)

    Forbidden patterns (HARD STOP):
    - ROOT/outputs (use OUTPUTS instead)
    - ROOT/temp* (use CASEOPS_METADATA_* directories)
    - ROOT/retrieved_metadata* (use CASEOPS_METADATA_* directories)
    - ROOT/retrieve-prod (use CASEOPS_METADATA_* directories)
    - Any write to ROOT/.sfdx or ROOT/.claude (use env vars: SF_DATA_DIR, CLAUDE_CODE_DIR)
    """
    path_resolved = path.resolve()

    # Forbidden patterns for ANY operation to shared directories
    forbidden_patterns = [
        ROOT / "outputs",  # Must use OUTPUTS (instance-specific)
        ROOT / "temp",
        ROOT / "temp-retrieve",
        ROOT / "temp_retrieve",
        ROOT / "Ctemp-sf-retrieve",
        ROOT / "retrieved_metadata",
        ROOT / "retrieved_metadata_sharing",
        ROOT / "retrieve-prod",
        ROOT / "temp_admin_team",
    ]

    # Enforce: path must not be under any forbidden pattern
    for forbidden in forbidden_patterns:
        try:
            path_resolved.relative_to(forbidden.resolve())
            # If we reach here, path IS under a forbidden directory
            raise RuntimeError(
                f"INSTANCE ROUTING VIOLATION: Cannot {operation} to {path}\n"
                f"Reason: Path is in shared directory {forbidden}\n"
                f"Rule: All instance operations must use OUTPUTS (currently: {OUTPUTS})\n"
                f"For Salesforce metadata: use CASEOPS_METADATA_RAW_PROD_DIR, "
                f"CASEOPS_METADATA_SANDBOX_WORK_DIR, or CASEOPS_METADATA_CONFIRMED_DIR\n"
                f"This is a HARD STOP to prevent cross-instance contamination."
            )
        except ValueError:
            # path is NOT under forbidden, which is what we want
            pass

    # For write operations, enforce path must be under OUTPUTS or instance directory
    if operation in ("write", "mkdir", "create"):
        outputs_resolved = OUTPUTS.resolve()
        try:
            path_resolved.relative_to(outputs_resolved)
            # Path IS under OUTPUTS, allowed
            return
        except ValueError:
            # Path is NOT under OUTPUTS, check if it's under instance-specific directory
            pass

        # Check if it's under instance1/ or instance2/ state directories
        instance_dirs = [ROOT / "instance1", ROOT / "instance2"]
        for inst_dir in instance_dirs:
            try:
                path_resolved.relative_to(inst_dir.resolve())
                # Path IS under instance dir, allowed
                return
            except ValueError:
                pass

        # Path not under OUTPUTS or instance dirs - this is risky for writes
        # Allow shared read-only dirs and specific ROOT files for now
        read_only_dirs = [ROOT / "skills", ROOT / "static", ROOT / "templates", ROOT / "scripts"]
        for ro_dir in read_only_dirs:
            try:
                path_resolved.relative_to(ro_dir.resolve())
                if operation == "write":
                    raise RuntimeError(
                        f"INSTANCE ROUTING VIOLATION: Cannot write to read-only shared directory {path}\n"
                        f"Path: {path_resolved}\n"
                        f"Rule: {ro_dir.name}/ is read-only shared code, do not write."
                    )
                # Read operations OK
                return
            except ValueError:
                pass


def _load_jira_env(env_file: Path | None = None) -> None:
    """Load .env.jira (or workspace-specific variant) into os.environ.

    By default does not overwrite existing non-empty values.
    Exceptions:
    - Runtime settings and secrets listed in `_ENV_KEYS_RELOAD_FROM_FILE` are always
      set from the file when the line has a non-empty value. This lets the Settings
      and token-refresh pages update the running Flask process without a restart.
    - Any key: if currently unset or empty/whitespace, the file value is applied.
    """
    if env_file is None:
        env_file = ROOT / ".env.jira"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        if not value:
            continue
        if key in _ENV_KEYS_RELOAD_FROM_FILE:
            os.environ[key] = value
            continue
        cur = os.environ.get(key, "")
        if key not in os.environ or not str(cur).strip():
            os.environ[key] = value


JIRA_BASE_URL = ""  # Set in __main__ after _load_jira_env()


def caseops_llm_auth_uses_anthropic_api_key() -> bool:
    """If True, CaseOps LLM calls use the **Anthropic Messages API** (API key billing).

    If False, CaseOps spawns the **Claude Code CLI** and omits ``ANTHROPIC_API_KEY`` so the CLI uses
    ``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token``.
    Unrecognized ``CASEOPS_LLM_AUTH`` values default to API mode (backward compatible).
    """
    raw = (os.environ.get(CASEOPS_LLM_AUTH_ENV) or "api_key").strip().lower()
    if raw in ("claude_code", "claude", "subscription", "max"):
        return False
    # api_key, anthropic_api, api, empty, or anything else → keep API key in env for subprocess
    return True


def _jira_auth_header() -> str:
    cmd = os.environ.get("JIRA_AUTH_HEADER_COMMAND")
    if cmd:
        h = subprocess.check_output(cmd, shell=True, text=True).strip()
        return h.split(":", 1)[1].strip() if h.lower().startswith("authorization:") else h
    bearer = os.environ.get("JIRA_BEARER_TOKEN")
    if bearer:
        return f"Bearer {bearer}"
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if email and token:
        return f"Basic {base64.b64encode(f'{email}:{token}'.encode()).decode()}"
    raise RuntimeError("No Jira auth found in .env.jira")


def _mask_secret(value: str) -> str:
    """Mask secret by showing only last 4 chars: 'secret123' → '••••••••3'."""
    if not value or len(value) < 4:
        return ""
    return "••••••••" + value[-4:]


def _read_env_file(env_file: Path | None = None) -> dict[str, str]:
    """Read .env.jira and return dict of all keys/values (including empty lines, comments stripped)."""
    if env_file is None:
        env_file = ROOT / ".env.jira"
    result: dict[str, str] = {}
    if not env_file.exists():
        return result
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def _write_env_file(updates: dict[str, str], env_file: Path | None = None) -> None:
    """Update .env.jira with new values, preserving comments and structure.

    If a key already exists in the file, update its value. If not, append it.
    Then reload the environment.
    """
    if env_file is None:
        env_file = ROOT / ".env.jira"

    # Read existing file
    existing_lines: list[str] = []
    existing_keys: set[str] = set()
    if env_file.exists():
        existing_lines = env_file.read_text(encoding="utf-8").splitlines()

    # Update or keep existing lines
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" not in line:
            new_lines.append(line)
            continue

        key = stripped.partition("=")[0].strip()
        if key in updates:
            # Replace line with new value
            new_lines.append(f"{key}={updates[key]}")
            existing_keys.add(key)
        else:
            # Keep line unchanged
            new_lines.append(line)
            existing_keys.add(key)

    # Append any new keys not in file
    for key, value in updates.items():
        if key not in existing_keys and value:  # Don't append empty values
            new_lines.append(f"{key}={value}")

    # Write back
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Reload env in running process
    _load_jira_env(env_file)


def _remove_env_keys(keys: set[str], env_file: Path | None = None) -> None:
    """Remove keys from .env.jira and the running process environment."""
    if env_file is None:
        env_file = ROOT / ".env.jira"
    if not env_file.exists():
        for key in keys:
            os.environ.pop(key, None)
        return

    new_lines: list[str] = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key not in keys:
            new_lines.append(line)

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    for key in keys:
        os.environ.pop(key, None)

CLOSED_STATUSES = {"closed", "resolved", "canceled", "cancelled"}
ESCALATED_STATUS = "escalated to engineering"

FILE_LOCATIONS: dict[str, str] = {
    "jira_summary":       "jira/summary/{key}.md",
    "investigation":      "investigations/{key}.md",
    "step4_hypothesis":   "step-4-hypothesis/{key}.md",
    "internal_notes":     "internal-notes/{key}.md",
    "jira_message":       "jira-messages/{key}.md",
    "test_report":        "test-reports/{key}.md",
    "eng_handoff":        "engineering-escalations/{key}.md",
    "closed_resolved":    "closed-resolved/{key}.md",
}

FILE_LABELS: dict[str, str] = {
    "jira_summary":    "Jira Summary",
    "investigation":   "Investigation",
    "step4_hypothesis": "Step 4 Hypothesis",
    "internal_notes":  "Internal Notes",
    "jira_message":    "Jira Message",
    "test_report":     "Test Report",
    "eng_handoff":     "Eng Handoff",
    "closed_resolved": "Closed / Resolved / Canceled",
    "attachments":     "Attachments",
}

# Global actions (sync, triage, full) use this sentinel key.
_GLOBAL_KEY = "__global__"

# Set in __main__ after OUTPUTS is determined; declared here for type checking
OUTPUTS_PIPELINE_LOGS: Path = None  # type: ignore # Initialized in __main__ block
_PIPELINE_LOG_LOCK = threading.Lock()
_PIPELINE_LOG_TAIL_BYTES = 3 * 1024 * 1024
_PIPELINE_LOG_TAIL_LINES = 12_000
_ANSI_CONTROL_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
)
_BROKEN_ANSI_CONTROL_RE = re.compile(r"\uFFFD\[[0-?]*[ -/]*[@-~]")
_SALESFORCE_ACCESS_TOKEN_RE = re.compile(r"\b00D[A-Za-z0-9]{12,18}![A-Za-z0-9._~=-]{20,}\b")


def _pipeline_log_path(run_key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", run_key) or "unknown"
    return OUTPUTS_PIPELINE_LOGS / f"{safe}.jsonl"


def _sanitize_pipeline_log_text(text: str) -> str:
    """Remove terminal redraw/color controls before logs are stored or shown."""
    cleaned = _ANSI_CONTROL_RE.sub("", str(text))
    cleaned = _BROKEN_ANSI_CONTROL_RE.sub("", cleaned)
    cleaned = _SALESFORCE_ACCESS_TOKEN_RE.sub("[REDACTED_SF_ACCESS_TOKEN]", cleaned)
    cleaned = cleaned.replace("\r", "\n").replace("\b", "")
    return cleaned.rstrip()


def _persist_pipeline_record(run_key: str, text: str, *, kind: str = "line") -> None:
    OUTPUTS_PIPELINE_LOGS.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_key": run_key,
        "kind": kind,
        "text": text,
    }
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    log_path = _pipeline_log_path(run_key)
    _validate_instance_path(log_path, "write")  # HARD RULE: instance-routed writes only
    with _PIPELINE_LOG_LOCK:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def _format_run_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _log_emit_run_start(run_key: str, label: str | None = None) -> None:
    target = label or run_key
    _log_emit_line(run_key, f"Run started: {target} at {_format_run_timestamp()}")


def _log_emit_line(run_key: str, text: str) -> None:
    """Notify SSE clients and append to per-key pipeline history on disk."""
    text = _sanitize_pipeline_log_text(text)
    _log_q.put(f"{run_key}|{text}")
    _persist_pipeline_record(run_key, text, kind="line")


def _log_emit_done(run_key: str) -> None:
    _log_q.put(f"__done__|{run_key}")
    _persist_pipeline_record(run_key, "", kind="done")


def _path_relative_for_prompt(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _read_text_for_resume(path: Path, max_chars: int = 80_000) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= max_chars else text[:max_chars]


def _artifact_snapshot(path: Path, source_mtime: float | None = None) -> dict[str, Any]:
    exists = path.is_file()
    stat = None
    if exists:
        try:
            stat = path.stat()
        except OSError:
            exists = False
            stat = None
    current = bool(exists and (source_mtime is None or (stat and stat.st_mtime + 1 >= source_mtime)))
    return {
        "path": _path_relative_for_prompt(path),
        "exists": exists,
        "current": current,
        "size": stat.st_size if stat else 0,
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else "",
    }


def _directory_has_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(child.is_file() for child in path.rglob("*"))
    except OSError:
        return False


def _parse_jira_updated_mtime(value: str | None) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _issue_source_mtime(key: str, jira_updated: str | None = None) -> float | None:
    parsed_updated = _parse_jira_updated_mtime(jira_updated)
    if parsed_updated is not None:
        return parsed_updated

    mtimes: list[float] = []
    for path in (
        OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key),
        OUTPUTS / "jira" / "raw" / f"{key}.json",
    ):
        try:
            if path.exists():
                mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else None


def _resume_step(step: int, name: str, status: str, reason: str, action: str, artifacts: list[str] | None = None) -> dict[str, Any]:
    return {
        "step": step,
        "name": name,
        "status": status,
        "reason": reason,
        "action": action,
        "artifacts": artifacts or [],
    }


def _build_pipeline_resume_plan(key: str, status: str = "", jira_updated: str | None = None) -> dict[str, Any]:
    """Build a conservative file-based resume plan for a single issue run."""
    source_mtime = _issue_source_mtime(key, jira_updated)
    paths = {
        "jira_summary": OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key),
        "investigation": OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key),
        "step4_hypothesis": OUTPUTS / FILE_LOCATIONS["step4_hypothesis"].format(key=key),
        "test_report": OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key),
        "internal_notes": OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key),
        "jira_message": OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key),
        "eng_handoff": OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key),
        "closed_resolved": OUTPUTS / FILE_LOCATIONS["closed_resolved"].format(key=key),
    }
    artifacts = {name: _artifact_snapshot(path, source_mtime) for name, path in paths.items()}

    investigation = _read_text_for_resume(paths["investigation"])
    hypothesis = _read_text_for_resume(paths["step4_hypothesis"])
    test_report = _read_text_for_resume(paths["test_report"])
    internal_notes = _read_text_for_resume(paths["internal_notes"])
    jira_message = _read_text_for_resume(paths["jira_message"])
    eng_handoff = _read_text_for_resume(paths["eng_handoff"])
    diagnosis_text = "\n".join([investigation, hypothesis, internal_notes, eng_handoff])

    metadata_dirs = _metadata_workspace_dirs()
    raw_metadata_dir = metadata_dirs["raw_prod"] / key
    sandbox_work_dir = metadata_dirs["sandbox_work"] / key
    confirmed_dir = metadata_dirs["confirmed"] / key
    metadata_manifest = sandbox_work_dir / "metadata-workspace.json"
    metadata = {
        "raw_production_dir": {"path": _path_relative_for_prompt(raw_metadata_dir), "has_files": _directory_has_files(raw_metadata_dir)},
        "sandbox_work_dir": {"path": _path_relative_for_prompt(sandbox_work_dir), "has_files": _directory_has_files(sandbox_work_dir)},
        "confirmed_dir": {"path": _path_relative_for_prompt(confirmed_dir), "has_files": _directory_has_files(confirmed_dir)},
        "workspace_manifest": _artifact_snapshot(metadata_manifest, None),
    }

    steps: list[dict[str, Any]] = []
    disposition = _disposition(status or "")
    if disposition == "closed":
        closed_current = artifacts["closed_resolved"]["current"]
        steps.append(_resume_step(
            2,
            "Triage closed/resolved issue",
            "complete" if closed_current else "pending",
            "Jira status is closed/resolved/canceled.",
            "Stop issue processing after closed/resolved archive is current." if closed_current else "Create or refresh closed/resolved archive, then stop for this key.",
            [artifacts["closed_resolved"]["path"]],
        ))
    elif disposition == "escalated":
        handoff_current = artifacts["eng_handoff"]["current"]
        steps.append(_resume_step(
            2,
            "Triage pre-escalated issue",
            "complete" if handoff_current else "pending",
            "Jira status is already Escalated to Engineering.",
            "Stop issue processing after engineering escalation archive is current." if handoff_current else "Create or refresh engineering escalation archive, then stop for this key.",
            [artifacts["eng_handoff"]["path"]],
        ))
    else:
        inv_current = artifacts["investigation"]["current"] and artifacts["investigation"]["size"] > 80
        step4_current = artifacts["step4_hypothesis"]["current"] and artifacts["step4_hypothesis"]["size"] > 80
        step4_inline = bool(artifacts["investigation"]["current"] and re.search(r"(?is)root cause hypothesis|smallest viable fix|sandbox validation plan|solution plan", investigation))
        problem_location = bool(artifacts["investigation"]["current"] and re.search(r"(?is)problem location|specific artifact|failure point|confirmed root cause|root cause", investigation))
        route_known = bool(artifacts["eng_handoff"]["current"] or re.search(r"(?is)support-resolvable|engineering[- ]required|engineering escalation|escalate to engineering", diagnosis_text))
        candidate_exists = bool(
            metadata["sandbox_work_dir"]["has_files"]
            or metadata["confirmed_dir"]["has_files"]
            or re.search(r"(?is)proposed solution|candidate|changed files|components changed|deploy", "\n".join([investigation, test_report]))
        )
        test_current = artifacts["test_report"]["current"] and artifacts["test_report"]["size"] > 80
        test_passed = _test_report_confirms_fix(key)
        test_failed = bool(test_current and not test_passed and re.search(r"(?is)\bfail(?:ed|ing)?\b|not fixed|revert|required: yes|blocked", test_report))
        engineering_path = bool(artifacts["eng_handoff"]["current"] or re.search(r"(?is)engineering escalation|escalate to engineering|engineering-required", diagnosis_text))
        step10_artifacts_current = bool(
            artifacts["internal_notes"]["current"]
            and artifacts["internal_notes"]["size"] > 80
            and artifacts["jira_message"]["current"]
            and artifacts["jira_message"]["size"] > 80
            and (not engineering_path or artifacts["eng_handoff"]["current"])
        )
        step10_complete = bool(step10_artifacts_current and test_current and test_passed)

        steps.extend([
            _resume_step(
                3,
                "Analyze issue",
                "complete" if inv_current else "pending",
                "Current investigation artifact exists." if inv_current else "No current investigation artifact, or Jira source changed after it was written.",
                "Emit STEP_3 resume-skip; do not spawn Step 3 sub-agent unless Jira changed materially." if inv_current else "Run Step 3 and write investigation record.",
                [artifacts["investigation"]["path"]],
            ),
            _resume_step(
                4,
                "Synthesize problem hypothesis",
                "complete" if (step4_current or step4_inline) else ("blocked" if not inv_current else "pending"),
                "Step 4 hypothesis artifact or required hypothesis sections are current." if (step4_current or step4_inline) else "Requires current Step 3 investigation first." if not inv_current else "No current Step 4 hypothesis found.",
                "Emit STEP_4 resume-skip; do not rewrite hypothesis unless later evidence invalidates it." if (step4_current or step4_inline) else "Create/update Step 4 hypothesis from Step 3 summary.",
                [artifacts["step4_hypothesis"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                5,
                "Retrieve relevant Production metadata",
                "complete" if (problem_location and metadata["raw_production_dir"]["has_files"]) else ("blocked" if not (step4_current or step4_inline) else "pending"),
                "Investigation identifies problem evidence and raw Production metadata exists." if (problem_location and metadata["raw_production_dir"]["has_files"]) else "Requires Step 4 hypothesis first." if not (step4_current or step4_inline) else "Production metadata evidence is missing or not indexed.",
                "Emit STEP_5 resume-skip; reuse raw Production metadata unless the hypothesis changed." if (problem_location and metadata["raw_production_dir"]["has_files"]) else "Run targeted Step 5 metadata retrieval using sf CLI.",
                [metadata["raw_production_dir"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                6,
                "Identify exact problem location",
                "complete" if problem_location else ("blocked" if not metadata["raw_production_dir"]["has_files"] else "pending"),
                "Investigation contains root cause/problem location signals." if problem_location else "Requires targeted Production metadata first." if not metadata["raw_production_dir"]["has_files"] else "Problem location is not documented clearly enough.",
                "Emit STEP_6 resume-skip; do not reread full investigation unless Step 8/9 needs exact component details." if problem_location else "Run Step 6 drilling and update investigation with exact artifact and failure point.",
                [artifacts["investigation"]["path"]],
            ),
            _resume_step(
                7,
                "Engineering escalation gate",
                "complete" if route_known else ("blocked" if not problem_location else "pending"),
                "Routing decision is already documented." if route_known else "Requires exact problem location first." if not problem_location else "Routing decision is not explicit.",
                "Emit STEP_7 resume-skip; preserve existing Support vs Engineering route." if route_known else "Classify Support-resolvable vs Engineering-required and document decision.",
                [artifacts["eng_handoff"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                8,
                "Prepare candidate solution",
                "complete" if candidate_exists and not test_failed else ("blocked" if not route_known else "pending"),
                "Candidate/proposed solution files or confirmed package evidence exist." if candidate_exists and not test_failed else "Requires routing decision first." if not route_known else "No usable candidate solution package/evidence found.",
                "Emit STEP_8 resume-skip; reuse existing candidate unless Step 9 failed." if candidate_exists and not test_failed else "Prepare or revise candidate solution in the metadata workspace.",
                [metadata["sandbox_work_dir"]["path"], metadata["confirmed_dir"]["path"]],
            ),
            _resume_step(
                9,
                "Deploy and test in Sandbox",
                "complete" if (test_current and test_passed) else ("stale" if test_failed else "blocked" if not candidate_exists else "pending"),
                "Current test report affirmatively confirms the fix." if (test_current and test_passed) else "Existing test report is not a pass; revert/iteration is required." if test_failed else "Requires candidate solution first." if not candidate_exists else "No passing current test report found.",
                "Emit STEP_9 resume-skip; do not redeploy unless candidate changed." if (test_current and test_passed) else "Re-enter Step 4/5/8/9 loop, reverting non-viable Sandbox attempts first." if test_failed else "Run Step 9 deploy/test against the allowlisted Sandbox.",
                [artifacts["test_report"]["path"], metadata["workspace_manifest"]["path"]],
            ),
            _resume_step(
                10,
                "Draft internal notes and Jira message",
                "complete" if step10_complete else ("stale" if step10_artifacts_current and not (test_current and test_passed) else "blocked" if not (test_current and test_passed) else "pending"),
                "Internal notes and Jira message are current and based on a passing current Step 9." if step10_complete else "Drafts exist, but Step 9 is not currently passing; they must be refreshed after validation." if step10_artifacts_current else "Requires passing Step 9 first." if not (test_current and test_passed) else "Draft artifacts are missing, stale, or incomplete.",
                "Emit STEP_10 resume-skip; do not rewrite drafts unless new test evidence changed." if step10_complete else "Refresh drafts after Step 9 passes." if step10_artifacts_current else "Draft/update internal notes, Jira message, and engineering handoff if required.",
                [artifacts["internal_notes"]["path"], artifacts["jira_message"]["path"], artifacts["eng_handoff"]["path"]],
            ),
        ])

        summary_path = _latest_issue_summary_path()
        summary_mtime = summary_path.stat().st_mtime if summary_path and summary_path.exists() else None
        issue_mtimes = []
        for path in paths.values():
            try:
                if path.exists():
                    issue_mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
        newest_issue_mtime = max(issue_mtimes) if issue_mtimes else None
        summary_current = bool(summary_mtime and newest_issue_mtime and summary_mtime + 1 >= newest_issue_mtime)
        steps.append(_resume_step(
            11,
            "Update dated summary",
            "complete" if summary_current and step10_complete else ("blocked" if not step10_complete else "pending"),
            "Latest dated summary is newer than issue artifacts." if summary_current and step10_complete else "Requires Step 10 first." if not step10_complete else "Latest dated summary is missing or older than issue artifacts.",
            "Emit STEP_11 __summary__ resume-skip unless the run changed artifacts." if summary_current and step10_complete else "Update today's issue summary once issue artifacts are complete.",
            [_path_relative_for_prompt(summary_path) if summary_path else "issue-summary-YYYY-MM-DD.md"],
        ))
        steps.append(_resume_step(
            12,
            "Inform operator",
            "pending",
            "Always report the result of this run.",
            "Emit STEP_12 __complete__ and summarize only what changed or what remains blocked.",
            [],
        ))

    next_step = next((s for s in steps if s["status"] not in {"complete", "skipped"}), steps[-1] if steps else None)
    return {
        "key": key,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mtime": datetime.fromtimestamp(source_mtime, timezone.utc).isoformat() if source_mtime else "",
        "mode": disposition,
        "next_step": next_step,
        "artifacts": artifacts,
        "metadata": metadata,
        "steps": steps,
    }


def _write_pipeline_resume_plan(plan: dict[str, Any]) -> Path:
    key = str(plan.get("key") or "unknown")
    path = OUTPUTS / "pipeline-state" / f"{key}.json"
    _validate_instance_path(path, "write")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _format_resume_plan_for_prompt(plan: dict[str, Any], plan_path: Path) -> str:
    next_step = plan.get("next_step") or {}
    lines = [
        "## Resume State Plan (authoritative for this rerun)",
        f"- Plan file: `{_path_relative_for_prompt(plan_path)}`",
        f"- Next required step: STEP_{next_step.get('step')} — {next_step.get('name')} ({next_step.get('status')})",
        "- Rule: completed steps are not work items. Emit one concise `STEP_N <KEY> resume-skip` line if needed for progress, then continue.",
        "- Rule: do not reread or rewrite completed artifacts unless a pending/stale downstream step needs exact details.",
        "- Rule: if Jira source changed after an artifact, treat that artifact and downstream artifacts as stale.",
        "",
        "| Step | Status | Action |",
        "| --- | --- | --- |",
    ]
    for step in plan.get("steps", []):
        lines.append(f"| {step.get('step')} {step.get('name')} | {step.get('status')} | {step.get('action')} |")
    return "\n".join(lines)


def _prepare_resume_plan(key: str, status: str = "", jira_updated: str | None = None) -> tuple[dict[str, Any], Path, str]:
    plan = _build_pipeline_resume_plan(key, status, jira_updated)
    plan_path = _write_pipeline_resume_plan(plan)
    return plan, plan_path, _format_resume_plan_for_prompt(plan, plan_path)


def _log_resume_plan_summary(run_key: str, plan: dict[str, Any], plan_path: Path) -> None:
    next_step = plan.get("next_step") or {}
    steps = plan.get("steps") or []
    completed = sum(1 for step in steps if step.get("status") == "complete")
    total = len(steps)
    step_num = next_step.get("step", "?")
    name = next_step.get("name", "Unknown")
    status = next_step.get("status", "unknown")
    _log_emit_line(
        run_key,
        f"Resume planner: next STEP_{step_num} ({name}, {status}); {completed}/{total} step checkpoints complete. Plan: {_path_relative_for_prompt(plan_path)}",
    )


def manifest_changed(changed_keys: list[str] | None = None) -> None:
    """Signal that manifest.csv was updated. Broadcasts to all SSE clients."""
    msg = f"updated:{','.join(changed_keys)}" if changed_keys else "updated:all"
    _manifest_q.put(msg)


def _read_pipeline_log_entries(run_key: str) -> list[dict[str, Any]]:
    path = _pipeline_log_path(run_key)
    if not path.is_file():
        return []
    with _PIPELINE_LOG_LOCK:
        blob = path.read_bytes()
    if len(blob) > _PIPELINE_LOG_TAIL_BYTES:
        blob = blob[-_PIPELINE_LOG_TAIL_BYTES:]
        nl = blob.find(b"\n")
        if nl != -1:
            blob = blob[nl + 1 :]
    rows: list[dict[str, Any]] = []
    for raw_line in blob.decode("utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
            if isinstance(row, dict) and "text" in row:
                row["text"] = _sanitize_pipeline_log_text(row.get("text", ""))
            rows.append(row)
        except json.JSONDecodeError:
            continue
    if len(rows) > _PIPELINE_LOG_TAIL_LINES:
        rows = rows[-_PIPELINE_LOG_TAIL_LINES :]
    return rows

# -- run state ---------------------------------------------------------------
# Multiple issue-specific runs are allowed in parallel.
# Global actions block each other and block new issue runs.
# Issue runs are blocked only while a global action is active.

_state_lock = threading.Lock()
_active_keys: set[str] = set()          # currently running run keys
_log_q: queue.Queue[str] = queue.Queue()  # tagged messages: "key|line" or "__done__|key"
_manifest_q: queue.Queue[str] = queue.Queue()  # manifest change notifications


def _claude_process_env() -> dict[str, str]:
    """Environment for Claude Code CLI subprocess.

    For claude_code mode: omit ANTHROPIC_API_KEY. Claude Code CLI uses the
    long-lived token generated by `claude setup-token` in CLAUDE_CODE_OAUTH_TOKEN.
    For api_key mode: pass ANTHROPIC_API_KEY (API billing auth).
    Instance-specific output directories so Skill writes to correct location.
    """
    env = os.environ.copy()
    if not caseops_llm_auth_uses_anthropic_api_key():
        # Claude Code subscription mode: prefer CLAUDE_CODE_OAUTH_TOKEN.
        # Do not pass ANTHROPIC_API_KEY; it takes precedence over subscription auth.
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OAUTH_TOKEN", None)

    chrome = (env.get("CASEOPS_CLAUDE_BROWSER") or "").strip()
    if chrome:
        env["BROWSER"] = chrome
        if not (env.get("CLAUDE_CODE_CHROME_PATH") or "").strip():
            env["CLAUDE_CODE_CHROME_PATH"] = chrome
    # Pass instance-specific directories to Claude Skill
    env["CASEOPS_OUTPUTS_DIR"] = str(OUTPUTS)
    env["CASEOPS_JIRA_OUT_DIR"] = str(OUTPUTS / "jira")
    env["CASEOPS_JIRA_ENV_FILE"] = app.config.get("ENV_FILE_PATH", str(ROOT / ".env.jira"))
    if TEMP_ROOT:
        env["CASEOPS_TEMP_DIR"] = str(TEMP_ROOT)
    metadata_dirs = _metadata_workspace_dirs()
    env["CASEOPS_METADATA_ROOT"] = str(metadata_dirs["root"])
    env["CASEOPS_METADATA_RAW_PROD_DIR"] = str(metadata_dirs["raw_prod"])
    env["CASEOPS_METADATA_SANDBOX_WORK_DIR"] = str(metadata_dirs["sandbox_work"])
    env["CASEOPS_METADATA_CONFIRMED_DIR"] = str(metadata_dirs["confirmed"])

    # Keep Salesforce CLI subprocesses deterministic in noninteractive Docker runs.
    # The CLI can otherwise spend time on telemetry/update/progress initialization
    # before even returning from simple commands such as `sf --version`.
    env.setdefault("SF_DISABLE_TELEMETRY", "true")
    env.setdefault("SF_AUTOUPDATE_DISABLE", "true")
    env.setdefault("SF_DISABLE_AUTOUPDATE", "true")
    env.setdefault("SF_USE_PROGRESS_BAR", "false")
    env.setdefault("SF_JSON_TO_STDOUT", "true")
    env.setdefault("NO_COLOR", "1")

    # Pass skill paths (registered at startup, avoid find / loops in subprocesses)
    env["CASEOPS_SKILL_PATHS"] = json.dumps(SKILL_PATHS)
    for skill_name, skill_path in SKILL_PATHS.items():
        env_var = f"CASEOPS_SKILL_{skill_name.upper().replace('-', '_')}"
        env[env_var] = skill_path

    return env


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    """Parse JSON from CLI stdout that may include warning text before the object."""
    text = (stdout or "").strip()
    if not text:
        return {}
    if not text.startswith("{"):
        idx = text.find("{")
        if idx < 0:
            return {}
        text = text[idx:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _command_error(proc: subprocess.CompletedProcess[str]) -> str:
    text = (proc.stderr or proc.stdout or "").strip()
    return text[:500] if text else f"exit {proc.returncode}"


def _decoded_timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run_cli_command(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout: int,
    retries: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run a CLI command and return a CompletedProcess even on timeout.

    Preflight should report actionable failures, not crash with TimeoutExpired.
    """
    last_timeout: subprocess.TimeoutExpired | None = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            last_timeout = exc
            if attempt < retries:
                continue
    assert last_timeout is not None
    stdout = _decoded_timeout_text(last_timeout.stdout)
    stderr = _decoded_timeout_text(last_timeout.stderr)
    message = f"Timed out after {timeout} seconds: {' '.join(cmd)}"
    stderr = f"{stderr}\n{message}".strip() if stderr else message
    return subprocess.CompletedProcess(cmd, 124, stdout=stdout, stderr=stderr)


def _content_text_fragments(value: Any) -> list[str]:
    """Extract readable text fragments from Claude stream-json content blocks."""
    fragments: list[str] = []
    if value is None:
        return fragments
    if isinstance(value, str):
        if value.strip():
            fragments.append(value)
        return fragments
    if isinstance(value, list):
        for item in value:
            fragments.extend(_content_text_fragments(item))
        return fragments
    if isinstance(value, dict):
        for key in ("text", "content", "output", "stdout", "stderr"):
            if key in value:
                fragments.extend(_content_text_fragments(value.get(key)))
    return fragments


def _is_file_read_tool(tool: str, detail: str) -> bool:
    tool_name = (tool or "").lower()
    normalized = (detail or "").replace("\\", "/").lower()
    if tool_name in {"read", "glob", "grep"}:
        return True
    read_commands = (
        "cat ",
        "type ",
        "get-content",
        "gc ",
        "sed ",
        "more ",
        "less ",
        "head ",
        "tail ",
    )
    return tool_name in {"bash", "powershell", "shell"} and any(cmd in normalized for cmd in read_commands)


def _emit_tool_result_text(run_key: str, text: str, *, suppress: bool, max_lines: int = 80) -> None:
    if suppress:
        return
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[:max_lines]:
        _log_emit_line(run_key, line)
    if len(lines) > max_lines:
        _log_emit_line(
            run_key,
            f"... [tool output truncated: {len(lines) - max_lines} additional line(s)]",
        )


def _collect_runtime_preflight(run_soql: bool = False) -> dict[str, Any]:
    """Validate the exact runtime environment used for Claude Code subprocesses."""
    settings = _read_env_file(Path(app.config["ENV_FILE_PATH"]) if app.config.get("ENV_FILE_PATH") else None)
    prod_alias = _env_first("CASEOPS_PRODUCTION_READ_ORG", settings=settings)
    sandbox_alias = _env_first("CASEOPS_SANDBOX_TARGET_ORG", settings=settings)
    env = _claude_process_env()

    result: dict[str, Any] = {
        "ok": True,
        "issues": [],
        "home": env.get("HOME") or str(Path.home()),
        "caseops_llm_auth": "api_key" if caseops_llm_auth_uses_anthropic_api_key() else "claude_code",
        "claude": {"ok": False},
        "sf": {
            "ok": False,
            "installed": False,
            "prod": {"alias": prod_alias, "authenticated": False, "soql_ok": False},
            "sandbox": {"alias": sandbox_alias, "authenticated": False, "soql_ok": False},
        },
    }

    def fail(message: str) -> None:
        result["ok"] = False
        result["issues"].append(message)

    if caseops_llm_auth_uses_anthropic_api_key():
        api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        result["claude"] = {"ok": bool(api_key), "mode": "api_key"}
        if not api_key:
            fail("ANTHROPIC_API_KEY is required when CASEOPS_LLM_AUTH=api_key.")
    else:
        claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
        version = _run_cli_command([claude_bin, "--version"], env=env, timeout=10, retries=1)
        result["claude"]["installed"] = version.returncode == 0
        result["claude"]["version"] = (version.stdout or version.stderr).strip()
        if version.returncode != 0:
            fail(f"Claude Code CLI is not available: {_command_error(version)}")
        else:
            auth = _run_cli_command([claude_bin, "auth", "status"], env=env, timeout=15, retries=1)
            auth_json = _json_from_stdout(auth.stdout)
            result["claude"]["authenticated"] = auth.returncode == 0
            result["claude"]["auth_status"] = auth_json or None
            result["claude"]["token_configured"] = bool((env.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip())
            result["claude"]["ok"] = auth.returncode == 0
            if auth.returncode != 0:
                fail("Claude Code CLI is not authenticated in the pipeline runtime environment.")

    sf_bin = shutil.which("sf")
    if not sf_bin:
        fail("Salesforce CLI (`sf`) is not installed or not on PATH.")
        return result

    result["sf"]["installed"] = True
    result["sf"]["path"] = sf_bin
    version = _run_cli_command([sf_bin, "--version"], env=env, timeout=15, retries=1)
    result["sf"]["version_ok"] = version.returncode == 0
    result["sf"]["version"] = (version.stdout or version.stderr).strip()
    if version.returncode != 0:
        # Version is useful diagnostics, but org display + SOQL are the real
        # runtime gates. Do not abort the pipeline only because version startup
        # was slow.
        result["sf"]["version_warning"] = _command_error(version)

    def check_org(role: str, alias: str) -> None:
        role_status = result["sf"][role]
        if not alias:
            fail(f"Missing {role} Salesforce org alias in .env.jira.")
            return

        display = _run_cli_command(
            [sf_bin, "org", "display", "--target-org", alias, "--json"],
            env=env,
            timeout=25,
            retries=1,
        )
        role_status["display_returncode"] = display.returncode
        if display.returncode != 0:
            role_status["error"] = _command_error(display)
            fail(f"Salesforce {role} org `{alias}` is not authenticated in the pipeline runtime environment.")
            return

        data = _json_from_stdout(display.stdout)
        org = data.get("result", {}) if isinstance(data, dict) else {}
        role_status.update({
            "authenticated": True,
            "username": org.get("username", ""),
            "orgId": org.get("id", ""),
            "instanceUrl": org.get("instanceUrl", ""),
        })

        if run_soql:
            query = _run_cli_command(
                [
                    sf_bin,
                    "data",
                    "query",
                    "--target-org",
                    alias,
                    "--query",
                    "SELECT Id FROM Organization LIMIT 1",
                    "--json",
                ],
                env=env,
                timeout=30,
                retries=1,
            )
            role_status["soql_returncode"] = query.returncode
            role_status["soql_ok"] = query.returncode == 0
            if query.returncode != 0:
                role_status["soql_error"] = _command_error(query)
                fail(f"Salesforce {role} org `{alias}` failed SOQL preflight in the pipeline runtime environment.")

    check_org("prod", prod_alias)
    check_org("sandbox", sandbox_alias)
    result["sf"]["ok"] = (
        result["sf"]["installed"]
        and result["sf"]["prod"]["authenticated"]
        and result["sf"]["sandbox"]["authenticated"]
        and (not run_soql or (result["sf"]["prod"]["soql_ok"] and result["sf"]["sandbox"]["soql_ok"]))
    )
    return result


def _emit_runtime_preflight_or_stop(run_key: str, run_soql: bool = True) -> bool:
    """Log and enforce runtime preflight before Claude-backed pipeline work starts."""
    _log_emit_line(run_key, "Preflight: validating Claude runtime, Salesforce CLI auth, and SOQL access")
    try:
        preflight = _collect_runtime_preflight(run_soql=run_soql)
    except Exception as e:
        _log_emit_line(run_key, f"ERROR: Runtime preflight failed unexpectedly: {type(e).__name__}: {e}")
        return False

    home = preflight.get("home") or ""
    sf_status = preflight.get("sf", {})
    prod = preflight.get("sf", {}).get("prod", {})
    sandbox = preflight.get("sf", {}).get("sandbox", {})
    _log_emit_line(run_key, f"Preflight: subprocess HOME={home}")
    if sf_status.get("version_warning"):
        _log_emit_line(run_key, f"Preflight warning: sf --version did not complete cleanly: {sf_status.get('version_warning')}")
    _log_emit_line(run_key, f"Preflight: Production org `{prod.get('alias')}` authenticated={bool(prod.get('authenticated'))} soql={bool(prod.get('soql_ok')) if run_soql else 'skipped'}")
    _log_emit_line(run_key, f"Preflight: Sandbox org `{sandbox.get('alias')}` authenticated={bool(sandbox.get('authenticated'))} soql={bool(sandbox.get('soql_ok')) if run_soql else 'skipped'}")

    if preflight.get("ok"):
        _log_emit_line(run_key, "Preflight: OK")
        return True

    _log_emit_line(run_key, "ERROR: CaseOps runtime preflight failed. Pipeline not started.")
    for issue in preflight.get("issues", []):
        _log_emit_line(run_key, f"       - {issue}")
    _log_emit_line(run_key, "       Fix Settings/auth first; do not use Salesforce frontdoor links as an API fallback.")
    return False


def _salesforce_browser_prompt_section() -> str:
    """Tell Claude how to open Salesforce when CaseOps spawns the CLI (no secrets logged to SSE)."""
    chrome = (os.environ.get("CASEOPS_CLAUDE_BROWSER") or "").strip()
    generic = (os.environ.get("CASEOPS_SALESFORCE_MAGIC_LINK") or "").strip()
    prod_magic = (os.environ.get("CASEOPS_PRODUCTION_MAGIC_LINK") or "").strip()
    sand_magic = (os.environ.get("CASEOPS_SANDBOX_MAGIC_LINK") or "").strip()
    prod_label = (os.environ.get("CASEOPS_PRODUCTION_READ_ORG") or "Production").strip()
    sand_label = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "Sandbox").strip()

    has_magic = bool(generic or prod_magic or sand_magic)
    if not has_magic and not chrome:
        return ""

    lines = [
        "## Salesforce browser access (visual-only fallback)",
        "Default Salesforce access is `sf` CLI plus SOQL. Use frontdoor / magic links only when visual UI inspection is absolutely necessary.",
        "**Do not use frontdoor session IDs as API bearer tokens.** Frontdoor links authenticate a browser UI session; they are not the API credential for `curl`, SOQL, metadata retrieval, deploy, or test execution.",
        "**Permission model (mandatory):** Production UI access is read-only. Sandbox UI access may be used for visual testing or UI-only actions after CLI/SOQL options are exhausted.",
    ]
    if chrome:
        lines.append(
            f"- Open OAuth or Salesforce URLs using **Google Chrome Dev** at: `{chrome}`. "
            "This subprocess sets `BROWSER` (and `CLAUDE_CODE_CHROME_PATH`) when configured; "
            "if a tool still opens another browser, use Chrome Dev manually at that path."
        )
    if generic:
        lines.append(
            "- Open this **session / frontdoor link** in Chrome Dev only for visual inspection when the target org is not specified below "
            "(do not paste into Jira, git commits, or customer-facing artifacts):"
        )
        lines.append(generic)
    if prod_magic:
        lines.append(
            f"- **Production ({prod_label})** via `CASEOPS_PRODUCTION_MAGIC_LINK` — **visual read-only only**. "
            "Use `sf` CLI/SOQL for queries and metadata inspection. No Production creates, edits, deletes, deployments, or API calls with the frontdoor SID:"
        )
        lines.append(prod_magic)
    if sand_magic:
        lines.append(
            f"- **Sandbox ({sand_label})** via `CASEOPS_SANDBOX_MAGIC_LINK` — visual UI fallback only. "
            "Use `sf project deploy`, `sf data query`, Apex tests, and other CLI commands for investigation/deploy/test unless a browser-only action is required:"
        )
        lines.append(sand_magic)
    if not has_magic:
        lines.append(
            "- No Salesforce session link is set in `.env.jira` "
            "(`CASEOPS_SALESFORCE_MAGIC_LINK`, `CASEOPS_PRODUCTION_MAGIC_LINK`, and/or `CASEOPS_SANDBOX_MAGIC_LINK`). "
            "If login blocks progress, say what you need."
        )
    lines.append("")
    return "\n".join(lines)


def _do_stream_proc(cmd: list[str], run_key: str) -> int:
    """Stream subprocess output to log queue. Returns exit code."""
    if cmd and cmd[0] == sys.executable:
        cmd = [cmd[0], "-u"] + cmd[1:]
    try:
        env = os.environ.copy()
        env["COLUMNS"] = "999"  # Prevent terminal wrapping in subprocess output
        env["CASEOPS_JIRA_OUT_DIR"] = str(OUTPUTS / "jira")  # Instance-specific Jira output dir
        env["CASEOPS_JIRA_ENV_FILE"] = app.config.get("ENV_FILE_PATH", str(ROOT / ".env.jira"))
        if TEMP_ROOT:
            env["CASEOPS_TEMP_DIR"] = str(TEMP_ROOT)

        # Pass skill paths (registered at startup)
        env["CASEOPS_SKILL_PATHS"] = json.dumps(SKILL_PATHS)
        for skill_name, skill_path in SKILL_PATHS.items():
            env_var = f"CASEOPS_SKILL_{skill_name.upper().replace('-', '_')}"
            env[env_var] = skill_path

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            bufsize=1,
            env=env,
        )
        assert proc.stdout
        for line in proc.stdout:
            _log_emit_line(run_key, line.rstrip())
        proc.wait()
        _log_emit_line(run_key, f"-- exit code {proc.returncode} --")
        return proc.returncode
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: {exc}")
        return 1


def _retry_with_backoff(max_attempts: int = 3, backoff_factor: float = 2.0):
    """Decorator for exponential backoff retry on transient errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff_factor ** attempt
                        time.sleep(wait_time)
            raise last_exc
        return wrapper
    return decorator


def _do_stream_anthropic_messages_api(prompt: str, run_key: str, issue_key: str | None = None) -> None:
    """Stream a single user turn via Anthropic Messages API (API key on your Anthropic account).

    If issue_key is provided, parse Suggested reply and [INTERNAL] output into separate files.
    """
    if Anthropic is None:
        _log_emit_line(
            run_key,
            "ERROR: Python package `anthropic` is not installed. "
            "Install with: pip install anthropic",
        )
        return
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        _log_emit_line(
            run_key,
            "ERROR: ANTHROPIC_API_KEY is empty. Set it in `.env.jira` when using CASEOPS_LLM_AUTH=api_key.",
        )
        return
    model = (os.environ.get("CASEOPS_ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
    max_raw = (os.environ.get("CASEOPS_ANTHROPIC_MAX_TOKENS") or "16384").strip()
    try:
        max_tokens = max(256, min(int(max_raw), 64_000))
    except ValueError:
        max_tokens = 16384
    _log_emit_line(
        run_key,
        "CaseOps LLM: Anthropic Messages API (CASEOPS_LLM_AUTH=api_key). "
        "Responses bill to your API key. **No agent tools** (no Bash/Read/skills runtime).",
    )
    _log_emit_line(run_key, f"model={model} max_tokens={max_tokens}")

    @_retry_with_backoff(max_attempts=3, backoff_factor=2.0)
    def call_api() -> str:
        """Returns full API response text."""
        client = Anthropic(api_key=api_key)
        buf = ""
        full_response = ""
        system_prompt = """You are CaseOps, a Jira triage and issue investigation assistant owned by Sean.

## Your voice
Sound like Sean, not like a perfect LLM. Be direct, concrete, human.

## Message formats: two audiences

### 1. Suggested reply (customer / portal / reporter)
Plain-language note to the requester. What you checked, what it means for them, one clear question or offer to help validate.

**Voice for customer messages:**
- Short, human, straightforward wording. No corporate fluff.
- No "we," "we've," "let's," "us." Prefer you / I / neutral facts.
- Don't bury them in Salesforce IDs, file paths, or admin jargon unless they asked.
- Prefer short paragraphs; avoid bullet lists unless they asked for steps.
- Thank them in a concrete way if they gave good repro, screenshots, or clear steps.
- Avoid em dashes. Avoid hyphen between clauses as punctuation.

**Every customer-facing draft must pass all of:**
- ✓ No em dash; no hyphen as clause punctuation
- ✓ Brief (not a full investigation replay)
- ✓ Casual, normal tone
- ✓ Specific thanks when repro/detail helped
- ✓ No bullets unless they asked for steps
- ✓ No internal IDs, repo paths, heavy jargon unless they asked
- ✓ No we / we've / we're / us / let us

If anything fails → rewrite and run the checklist again.

### 2. ## [INTERNAL]
Lean root-cause memo: not agent chatter. Intended as paste-ready Jira internal text only.

**Structure:**
- What it is NOT (negative space)
- Where the real gap is
- Why the symptom shows up
- Keep it short. Full evidence stays in Investigation section.
- Include Action: {what Sean does next} if applicable.

## Your task
Analyze the issue. Draft both formats. If you don't have enough info for a solid Suggested reply, ask clarifying questions instead of guessing. Better to ask than to send weak prose."""

        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                buf += text
                full_response += text
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if line.strip():
                        _log_emit_line(run_key, line.rstrip())
            if buf.strip():
                _log_emit_line(run_key, buf.strip())
        _log_emit_line(run_key, "-- stream complete --")
        return full_response

    try:
        full_output = call_api()
        if issue_key:
            _save_claude_output(full_output, issue_key)
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: Anthropic API (after retries): {exc}")


def _do_stream_claude_code_cli(prompt: str, run_key: str, issue_key: str | None = None) -> None:
    """Run Claude Code CLI non-interactively, parsing stream-json output.

    If issue_key is provided, parse output for Suggested reply and [INTERNAL] sections
    and save to separate files.

    Falls back to spawning Claude in a new PowerShell window if direct subprocess fails.
    """
    # Use full path to claude binary (PATH may not include /usr/local/bin in subprocess)
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    cmd = [
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    try:
        _log_emit_line(
            run_key,
            "CaseOps LLM: Claude Code CLI (CASEOPS_LLM_AUTH=claude_code).",
        )
        _log_emit_line(run_key, f"Claude binary: {claude_bin}")

        # Check auth availability before invoking CLI. Do not log token values.
        if not caseops_llm_auth_uses_anthropic_api_key():
            if (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip():
                _log_emit_line(run_key, "Claude Code OAuth token configured: CLAUDE_CODE_OAUTH_TOKEN")
            else:
                _log_emit_line(run_key, "WARNING: Claude Code auth token not configured.")
                _log_emit_line(run_key, "Run /setup/claude-login and paste output from `claude setup-token`.")

        env = _claude_process_env()
        env["CASEOPS_OUTPUTS_DIR"] = str(OUTPUTS)
        _log_emit_line(run_key, f"Invoking: {claude_bin} -p [prompt redacted] --output-format stream-json ...")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            bufsize=1,
        )
        _log_emit_line(run_key, f"Process started (PID: {proc.pid})")
        assert proc.stdout
        assistant_text = []
        tool_uses: dict[str, tuple[str, str]] = {}
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                _log_emit_line(run_key, raw)
                continue

            etype = event.get("type", "")

            if etype == "assistant":
                for block in event.get("message", {}).get("content", []):
                    btype = block.get("type", "")
                    if btype == "text":
                        text = block.get("text", "")
                        if issue_key:
                            assistant_text.append(text)
                        for line in text.splitlines():
                            if line.strip():
                                _log_emit_line(run_key, line)
                    elif btype == "tool_use":
                        tool = block.get("name", "tool")
                        inp = block.get("input", {})
                        detail = inp.get("command") or inp.get("file_path") or inp.get("path") or ""
                        detail = str(detail).replace("\r", " ").replace("\n", " ").strip()
                        tool_id = str(block.get("id") or "")
                        if tool_id:
                            tool_uses[tool_id] = (str(tool), detail)
                        _log_emit_line(run_key, f"[{tool}]{' ' + detail if detail else ''}")

            elif etype == "user":
                # Claude Code reports tool results as user/tool_result stream events.
                # Keep command/sub-agent output visible for progress, but avoid dumping
                # file contents and playbooks into the operator log.
                for block in event.get("message", {}).get("content", []):
                    tool = ""
                    detail = ""
                    if isinstance(block, dict):
                        tool_id = str(block.get("tool_use_id") or "")
                        tool, detail = tool_uses.get(tool_id, ("", ""))
                    suppress_result = _is_file_read_tool(tool, detail)
                    for text in _content_text_fragments(block):
                        if issue_key and not suppress_result:
                            assistant_text.append(text)
                        _emit_tool_result_text(run_key, text, suppress=suppress_result)

            elif etype == "result":
                subtype = event.get("subtype", "")
                cost = event.get("cost_usd")
                cost_str = f"  cost: ${cost:.4f}" if cost else ""
                _log_emit_line(run_key, f"-- {subtype}{cost_str} --")

            elif etype == "system":
                pass  # ignore init events

        if proc.stderr:
            err = proc.stderr.read().strip()
            if err:
                for line in err.splitlines():
                    _log_emit_line(run_key, f"ERR: {line}")

        try:
            returncode = proc.wait(timeout=600)  # 10 min timeout
        except subprocess.TimeoutExpired:
            _log_emit_line(run_key, "ERROR: Claude process timeout (10 min) — killing subprocess")
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
            return

        if returncode == 0 and issue_key and assistant_text:
            full_output = "\n".join(assistant_text)
            _save_claude_output(full_output, issue_key)
        elif returncode != 0:
            _log_emit_line(run_key, f"-- exit code {returncode} --")

    except FileNotFoundError:
        _log_emit_line(run_key, "WARNING: 'claude' CLI not found on PATH")
        _log_emit_line(run_key, "Attempting fallback: launching Claude Code in new window via PowerShell script...")
        _fallback_launch_claude_window(issue_key, prompt, run_key)
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: {exc}")


def _fallback_launch_claude_window(issue_key: str | None, prompt: str, run_key: str) -> None:
    """Fallback: spawn Claude Code in a new PowerShell window if direct CLI fails.

    This opens an interactive session so the user can see Claude's reasoning in real-time.
    The prompt is displayed in the terminal so the user can copy/paste it if needed.
    """
    if not issue_key:
        _log_emit_line(run_key, "ERROR: Cannot use fallback without issue_key")
        return

    try:
        # Use PowerShell script launcher if available
        launcher_script = ROOT / "scripts" / "launch-claude-skill.ps1"
        if launcher_script.exists():
            _log_emit_line(run_key, f"Launching Claude Code for {issue_key} in new PowerShell window...")
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(launcher_script),
                    "-IssueKey", issue_key,
                ],
                cwd=str(ROOT),
            )
            _log_emit_line(run_key, "New window opened. Check it for Claude's output.")
            _log_emit_line(run_key, "This window will show only status messages.")
            return

        # Fallback: print the prompt so user can manually copy/paste into Claude
        _log_emit_line(run_key, "=== MANUAL LAUNCH INSTRUCTIONS ===")
        _log_emit_line(run_key, "Claude Code CLI not found and fallback script not available.")
        _log_emit_line(run_key, "To continue, open a terminal and run:")
        _log_emit_line(run_key, "")
        _log_emit_line(run_key, f"claude -p '{prompt[:100]}...'")
        _log_emit_line(run_key, "")
        _log_emit_line(run_key, "Or open Claude Code IDE and paste this prompt:")
        for line in prompt.split("\n")[:10]:
            _log_emit_line(run_key, f"  {line}")
        _log_emit_line(run_key, "  ...")
        _log_emit_line(run_key, "=== END MANUAL INSTRUCTIONS ===")

    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: Fallback launch failed: {exc}")


def _do_stream_claude(prompt: str, run_key: str, issue_key: str | None = None) -> None:
    """LLM entry: API Messages when ``api_key`` auth; else Claude Code CLI.

    If issue_key is provided, parse Suggested reply and [INTERNAL] output into separate files.
    """
    if caseops_llm_auth_uses_anthropic_api_key():
        _do_stream_anthropic_messages_api(prompt, run_key, issue_key)
    else:
        _do_stream_claude_code_cli(prompt, run_key, issue_key)


def _stream_proc(cmd: list[str], run_key: str) -> None:
    try:
        _do_stream_proc(cmd, run_key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        # Invalidate jira_summary caches after operations
        # - Global operations: clear all caches so fresh data is fetched from disk
        # - Individual issue operations: clear that issue's cache entry
        if run_key == _GLOBAL_KEY:
            jira_summary_cache.clear()
        else:
            # For individual issue syncs/runs, clear that issue's cached data
            jira_summary_cache.pop(run_key, None)
        _log_emit_line(run_key, "Done: global run" if run_key == _GLOBAL_KEY else f"Done: {run_key}")
        _log_emit_done(run_key)


def _save_claude_output(content: str, key: str) -> None:
    """Parse Claude output with Suggested reply and [INTERNAL] sections into separate files.

    Expected format:
      ## Suggested reply
      ...customer message...

      ## [INTERNAL]
      ...internal memo...
    """
    suggested_start = content.find("## Suggested reply")
    internal_start = content.find("## [INTERNAL]")

    if suggested_start == -1 and internal_start == -1:
        return

    # Extract Suggested reply (customer message)
    if suggested_start != -1:
        if internal_start != -1:
            suggested_text = content[suggested_start:internal_start].strip()
        else:
            suggested_text = content[suggested_start:].strip()
        # Remove header line
        suggested_text = "\n".join(suggested_text.split("\n")[1:]).strip()
        if suggested_text:
            path = OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key)
            _validate_instance_path(path, "write")  # HARD RULE: instance-routed writes only
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(suggested_text, encoding="utf-8")

    # Extract [INTERNAL] (internal notes)
    if internal_start != -1:
        internal_text = content[internal_start:].strip()
        # Remove header line
        internal_text = "\n".join(internal_text.split("\n")[1:]).strip()
        if internal_text:
            path = OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)
            _validate_instance_path(path, "write")  # HARD RULE: instance-routed writes only
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(internal_text, encoding="utf-8")


def _stream_claude_proc(prompt: str, run_key: str, issue_key: str | None = None) -> None:
    try:
        if issue_key:
            _log_emit_run_start(run_key, issue_key)
        if not _emit_runtime_preflight_or_stop(run_key):
            return
        _do_stream_claude(prompt, run_key, issue_key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        # Phase 2: invalidate caches when pipeline completes so stale flags aren't served
        if issue_key:
            jira_summary_cache.pop(issue_key, None)
            investigation_cache.pop(issue_key, None)
        _log_emit_line(run_key, "Done: global run" if run_key == _GLOBAL_KEY else f"Done: {run_key}")
        _log_emit_done(run_key)


def _stream_full_issue(key: str, run_key: str) -> None:
    """Run full CaseOps fix pipeline via the mounted jira-salesforce-fix-pipeline playbook.

    This invokes Claude Code with direct file-path instructions for Steps 1-12 orchestration.
    Do NOT call deprecated run_pipeline.py — that calls removed agents.
    """
    try:
        _log_emit_run_start(run_key, key)
        _log_emit_line(run_key, f"-- Processing {key} via jira-salesforce-fix-pipeline playbook --")

        # Safety check: CASEOPS_SANDBOX_TARGET_ORG must be set before Step 9
        sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
        if not sandbox_target:
            _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env.jira")
            _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
            _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env.jira and retry.")
            return
        if not _emit_runtime_preflight_or_stop(run_key):
            return

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, then use `/setup/claude-login` with `claude setup-token`.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        row = next((r for r in _read_manifest() if r.get("Key") == key), {})
        resume_plan, resume_path, resume_block = _prepare_resume_plan(key, row.get("Status", ""), row.get("Updated", ""))
        _log_resume_plan_summary(run_key, resume_plan, resume_path)
        prompt = _build_claude_prompt(
            key,
            "Run the full CaseOps fix pipeline for this issue through completion of investigation, "
            "internal notes, and Jira customer message (and any sandbox/escalation steps the playbook "
            "requires for this issue). Read the mounted playbook files directly; do not invoke a slash-skill.",
            resume_block,
        )
        _do_stream_claude(prompt, run_key, key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        # Phase 2: invalidate caches for this issue when full-issue run completes
        jira_summary_cache.pop(key, None)
        investigation_cache.pop(key, None)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _stream_reprocess_issue(key: str, run_key: str) -> None:
    """Reprocess single issue without Jira sync via the mounted jira-salesforce-fix-pipeline playbook.

    Useful for re-running a single issue that failed or needs investigation updates.
    """
    try:
        _log_emit_run_start(run_key, f"{key} reprocess")
        _log_emit_line(run_key, f"-- Reprocessing {key} (no sync) via jira-salesforce-fix-pipeline playbook --")

        # Safety check: CASEOPS_SANDBOX_TARGET_ORG must be set before Step 9
        sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
        if not sandbox_target:
            _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env.jira")
            _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
            _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env.jira and retry.")
            return
        if not _emit_runtime_preflight_or_stop(run_key):
            return

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, then use `/setup/claude-login` with `claude setup-token`.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        row = next((r for r in _read_manifest() if r.get("Key") == key), {})
        resume_plan, resume_path, resume_block = _prepare_resume_plan(key, row.get("Status", ""), row.get("Updated", ""))
        _log_resume_plan_summary(run_key, resume_plan, resume_path)
        prompt = _build_claude_prompt(
            key,
            "Reprocess the CaseOps fix pipeline for this issue without re-syncing from Jira. "
            "Read the mounted jira-salesforce-fix-pipeline playbook files directly; do not invoke a slash-skill.",
            resume_block,
        )
        _do_stream_claude(prompt, run_key, key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        jira_summary_cache.pop(key, None)
        investigation_cache.pop(key, None)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _stream_global_skill(instruction: str, run_key: str) -> None:
    """Run global CaseOps pipeline via the mounted jira-salesforce-fix-pipeline playbook.

    This invokes Claude Code for global actions like "full" (sync + process all)
    or "reprocess" (process existing without sync).
    """
    try:
        _log_emit_line(run_key, f"-- Running CaseOps pipeline: {instruction.split(':')[1].strip() if ':' in instruction else instruction} --")

        # Safety check: CASEOPS_SANDBOX_TARGET_ORG must be set before Step 9
        sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
        if not sandbox_target:
            _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env.jira")
            _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
            _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env.jira and retry.")
            return
        if not _emit_runtime_preflight_or_stop(run_key):
            return

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, then use `/setup/claude-login` with `claude setup-token`.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        prompt = (
            f"Run the CaseOps jira-salesforce-fix-pipeline playbook with instruction:\n\n{instruction}\n\n"
            f"Do not invoke a slash-skill. Read the mounted playbook entrypoint at "
            f"skills/jira-salesforce-fix-pipeline/SKILL.md and read "
            f"ORCHESTRATOR-PROMPT.md for decision logic.\n\n"
            f"At the start of processing each issue, emit `Run started: <ISSUE_KEY> at YYYY-MM-DD HH:MM:SS <TZ>`.\n\n"
            f"Operator log hygiene: do not echo, restate, or summarize the playbook, this prompt, "
            f"skill files, or reference files into stdout. Stream the actual run only: step markers, "
            f"concise status, commands/tools used, files written, test results, and blockers.\n\n"
            f"Resume efficiency: for each active issue, inspect existing artifacts first and skip completed "
            f"checkpoints unless Jira source changed after the artifact or downstream evidence invalidates it. "
            f"Do not reread or rewrite full existing artifacts just to restate them; read targeted sections only "
            f"when a pending/stale step requires exact details.\n\n"
            f"Org knowledge efficiency: for each active issue, read `{_path_relative_for_prompt(_org_knowledge_dir() / 'index.json')}` "
            f"and `{_path_relative_for_prompt(_org_knowledge_dir() / 'run-rules.md')}` first, then select only the matching "
            f"topic files for that issue. Do not bulk-read `{_path_relative_for_prompt(_org_knowledge_dir())}`. "
            f"Pass relevant selected bullets into Step 5, Step 6, Step 8, and Step 9 sub-agent prompts."
        )
        _do_stream_claude(prompt, run_key, issue_key=None)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _build_claude_prompt(key: str, instruction: str, resume_block: str | None = None) -> str:
    """Build a context-rich prompt for CaseOps LLM runs (API or Claude Code CLI)."""
    issues = _read_manifest()
    row = next((r for r in issues if r.get("Key") == key), {})
    summary = row.get("Summary", "")
    status  = row.get("Status", "")
    if resume_block is None:
        _resume_plan, _resume_path, resume_block = _prepare_resume_plan(key, status, row.get("Updated", ""))

    existing = []
    for ftype, rel in FILE_LOCATIONS.items():
        if ftype == "attachments":
            continue
        path = OUTPUTS / rel.format(key=key)
        if path.exists():
            existing.append(f"  - {FILE_LABELS[ftype]}: {path.relative_to(ROOT).as_posix()}")

    files_block = "\n".join(existing) if existing else "  - None yet"
    org_knowledge_block = _build_org_knowledge_context_block(key, row)

    skill_md = (ROOT / "skills" / "jira-salesforce-fix-pipeline" / "SKILL.md").resolve()
    skill_line = str(skill_md) if skill_md.is_file() else f"(missing) {skill_md}"

    # Instance-specific outputs directory (may differ from ROOT/outputs in multi-instance setup)
    outputs_dir_relative = OUTPUTS.relative_to(ROOT).as_posix() if OUTPUTS.is_relative_to(ROOT) else str(OUTPUTS)

    # Instance-specific env file (may differ from ROOT/.env.jira in multi-instance setup)
    env_file_path = app.config.get("ENV_FILE_PATH", str(ROOT / ".env.jira"))
    env_file_relative = Path(env_file_path).relative_to(ROOT).as_posix() if Path(env_file_path).is_relative_to(ROOT) else env_file_path

    core = (
        f"Issue: {key} — {summary}\n"
        f"Status: {status}\n\n"
        f"Existing pipeline files:\n{files_block}\n\n"
        f"{resume_block}\n\n"
        f"{org_knowledge_block}"
        f"## Playbook (mandatory — read first)\n"
        f"Do not invoke `/jira-salesforce-fix-pipeline` or a Claude Code Skill tool in this subprocess. "
        f"The entrypoint is the mounted file below. Read SKILL.md fully, then read "
        f"`skills/jira-salesforce-fix-pipeline/references/workflow.md` end-to-end (authoritative steps 1–11), "
        f"then execute for issue {key}:\n"
        f"  {skill_line}\n"
        f"Use `references/sub-agent-prompts.md`, `references/safety-policy.md`, `references/quality-checklist.md`, "
        f"and `assets/` under that skill when the playbook points to them.\n\n"
        f"## Instance Output Directory\n"
        f"**CRITICAL for multi-instance deployments:** All file paths in this run must use:\n"
        f"`{outputs_dir_relative}/` instead of the generic `outputs/` references in the playbook.\n"
        f"Example: Instead of `outputs/investigations/{{KEY}}.md`, use `{outputs_dir_relative}/investigations/{{KEY}}.md`\n\n"
        f"## Instance Configuration (.env.jira)\n"
        f"**CRITICAL for multi-instance deployments:** Use the instance-specific configuration file:\n"
        f"- Read Jira credentials and Salesforce orgs from: `{env_file_relative}`\n"
        f"- Do NOT read from `ROOT/.env.jira` (this is another instance's config)\n"
        f"- Environment variable available: `CASEOPS_JIRA_ENV_FILE={env_file_path}`\n"
        f"- Example: `source {env_file_relative}` or pass it explicitly to commands that need Jira/Salesforce config\n\n"
        f"## Salesforce Metadata Workspace\n"
        f"**CRITICAL for multi-instance deployments and clean rollback:** Do not use root-level `temp*`, "
        f"`retrieve*`, `deploy*`, or `metadata*` directories. Use this instance-scoped workspace contract:\n"
        f"- Raw Production retrievals, read-only: `${{CASEOPS_METADATA_RAW_PROD_DIR}}/{key}/`\n"
        f"- Sandbox solution attempts: `${{CASEOPS_METADATA_SANDBOX_WORK_DIR}}/{key}/attempt-001/`, "
        f"`attempt-002/`, etc.\n"
        f"- Confirmed packages: `${{CASEOPS_METADATA_CONFIRMED_DIR}}/{key}/support-owned/` or "
        f"`${{CASEOPS_METADATA_CONFIRMED_DIR}}/{key}/engineering-proposal/`\n"
        f"- Environment variables available:\n"
        f"  - `CASEOPS_METADATA_ROOT={str(_metadata_workspace_dirs()['root'])}`\n"
        f"  - `CASEOPS_METADATA_RAW_PROD_DIR={str(_metadata_workspace_dirs()['raw_prod'])}`\n"
        f"  - `CASEOPS_METADATA_SANDBOX_WORK_DIR={str(_metadata_workspace_dirs()['sandbox_work'])}`\n"
        f"  - `CASEOPS_METADATA_CONFIRMED_DIR={str(_metadata_workspace_dirs()['confirmed'])}`\n"
        f"- Production metadata is read-only reference material. Never edit files under "
        f"`CASEOPS_METADATA_RAW_PROD_DIR`.\n"
        f"- Before each Sandbox deploy attempt, retrieve the current Sandbox baseline for every component "
        f"you will change into `attempt-N/baseline-sandbox/`, place candidate metadata in "
        f"`attempt-N/candidate/`, and keep rollback metadata in `attempt-N/revert/`.\n"
        f"- If an attempt is not viable, revert the Sandbox to the captured baseline before starting the "
        f"next attempt, then record the revert command/result in the test report.\n"
        f"- Maintain `${{CASEOPS_METADATA_SANDBOX_WORK_DIR}}/{key}/metadata-workspace.json` with "
        f"attempt number, components touched, baseline path, candidate path, revert status, and confirmed "
        f"package path when applicable.\n"
        f"- Sub-agents spawned in Steps 5, 6, and 9 must follow this workspace contract "
        f"(see sub-agent-prompts.md).\n\n"
        f"## Instruction\n"
        f"{instruction}\n\n"
        f"## Live Progress Requirement\n"
        f"- Execute the pipeline in this Claude Code process. Do not start background work and say you will be notified later.\n"
        f"- Before each numbered pipeline step, print a standalone progress line exactly like `STEP_N {key}`.\n"
        f"- For Step 11 print `STEP_11 __summary__`; for Step 12 print `STEP_12 __complete__`.\n"
        f"- Continue streaming concise status after each step completes, including file paths written and blockers.\n\n"
        f"## Operator Log Hygiene\n"
        f"- Do not echo, restate, or summarize the playbook, this prompt, skill files, or reference files into stdout.\n"
        f"- The operator log should show the actual run: step markers, concise status, commands/tools used, files written, test results, and blockers.\n"
        f"- Keep playbook analysis internal unless a playbook conflict blocks the run.\n\n"
        f"## Salesforce Queries: Use sf CLI + SOQL (DEFAULT)\n"
        f"**For metadata queries, field inspection, permission checks, and configuration verification:**\n"
        f"1. **Use `sf` CLI commands** (read-only, fast, no browser needed):\n"
        f"   - `sf org display --target-org <alias>` and `sf org list` to verify auth\n"
        f"   - `sf project retrieve start --metadata [type]` (pull metadata)\n"
        f"   - `sf sobject get --sobject [type]` (inspect objects/fields)\n"
        f"2. **Use SOQL queries** via `sf data query` to inspect data, field values, record types, assignments\n"
        f"3. **Never use Playwright, browser automation, frontdoor links, or frontdoor SIDs** for metadata queries, SOQL/API access, field inspection, permission checks, retrieval, deploy, or Apex tests\n"
        f"4. **Only open browser / frontdoor links for:**\n"
        f"   - Visual verification (testing layouts, field placement, visual tests)\n"
        f"   - UI clicks (when automation can't use CLI, e.g., custom buttons, flow runs)\n"
        f"   - Human-readable confirmation\n"
        f"5. If `sf` reports no authenticated orgs, treat that as a CaseOps/container auth configuration blocker. Do **not** test frontdoor SIDs with `curl` and do not conclude Salesforce API is unreachable from frontdoor 401s.\n"
        f"\n{_salesforce_browser_prompt_section()}"
        f"## CaseOps Output Files (update these when your task is complete)\n"
        f"You can read and write these files directly for issue {key}:\n"
        f"(Use `{outputs_dir_relative}/` prefix for multi-instance deployments)\n"
        f"\n"
        f"| File | Purpose | When to Update |\n"
        f"|------|---------|----------------|\n"
        f"| `{outputs_dir_relative}/investigations/{key}.md` | Investigation record (issue understanding, Salesforce problem, similar items analysis) | After diagnosis, before drafting notes |\n"
        f"| `{outputs_dir_relative}/internal-notes/{key}.md` | Internal notes for operator (root cause, escalation decision, fix notes) | When you've diagnosed the issue |\n"
        f"| `{outputs_dir_relative}/jira-messages/{key}.md` | Customer-facing Jira message (confirmed fix OR engineering escalation) | When ready to respond to customer |\n"
        f"| `{outputs_dir_relative}/test-reports/{key}.md` | Test cases, results, and fix validation | After testing the fix in Sandbox |\n"
        f"| `{outputs_dir_relative}/engineering-escalations/{key}.md` | Engineering handoff (if escalating) | When escalating to Engineering team |\n"
        f"\n"
        f"**Update guidance:**\n"
        f"- Read existing files first (if they exist) to preserve prior work\n"
        f"- Update them directly (do not ask operator or wait for confirmation)\n"
        f"- Commit your changes with `git add` + `git commit` if substantial updates\n"
        f"- If you cannot complete a task, update the relevant file to document progress and blockers\n"
        f"\n"
        f"## Rules\n"
        f"- Do not ask the user to pick a workflow; the playbook above is the workflow.\n"
        f"- Proceed with the next pipeline steps implied by the playbook and by which files "
        f"already exist for {key} in `{outputs_dir_relative}/`.\n"
        f"- Create or update artifacts in `{outputs_dir_relative}/` that this issue needs (paths as shown above).\n"
        f"- In every confirmed solution, state **Production vs Sandbox** clearly: what Production has (read-only verification), "
        f"what is **Sandbox-only**, and whether **Production metadata deploy** is required (**Yes — e.g. Gearset** / **No** / **N/A**). "
        f"Never imply Production has new metadata just because Sandbox validation passed. Do not deploy to Production unless the operator explicitly requests it.\n"
    )
    if caseops_llm_auth_uses_anthropic_api_key():
        core += (
            "\n## CaseOps runtime: Anthropic Messages API (no tools)\n\n"
            "This request is executed with the **Anthropic Messages API** only (`CASEOPS_LLM_AUTH=api_key`). "
            "You have **no** agent tools: you cannot read paths from disk, run shell commands, use a browser, "
            "or run Claude Code skills. Playbook file paths above are **not** available to you automatically. "
            "Ground yourself in the Issue line, Status, the **Existing pipeline files** path list, and the "
            "**Instruction** section. If the task requires autonomous repo execution, say so and tell the operator "
            "to set **`CASEOPS_LLM_AUTH=claude_code`** (Claude Code CLI with tools) or run Claude Code in the repo.\n"
        )
    return core


# -- helpers -----------------------------------------------------------------

def _manifest_path() -> Path:
    return OUTPUTS / "jira" / "manifest.csv"


def _read_manifest() -> list[dict[str, str]]:
    path = _manifest_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _count_open_issues(issues: list[dict[str, str]]) -> int:
    """Count issues not in closed/resolved/escalated states."""
    closed_statuses = {"closed", "resolved", "canceled", "cancelled", "escalated to engineering"}
    return sum(1 for issue in issues if issue.get("Status", "").lower() not in closed_statuses)


def _disposition(status: str) -> str:
    s = status.lower()
    if s in CLOSED_STATUSES:
        return "closed"
    if s == ESCALATED_STATUS:
        return "escalated"
    return "active"


def _is_jira_engineering_escalated(status: str = "") -> bool:
    return (status or "").strip().lower() == ESCALATED_STATUS


def _is_jira_escalated_any(status: str = "") -> bool:
    return "escalated" in (status or "").strip().lower()


def _available_tabs(key: str) -> list[dict[str, str]]:
    tabs = []
    internal_only = {"step4_hypothesis"}
    for ftype, rel in FILE_LOCATIONS.items():
        if ftype == "attachments" or ftype in internal_only:
            continue
        path = OUTPUTS / rel.format(key=key)
        if path.exists():
            tabs.append({"id": ftype, "label": FILE_LABELS[ftype]})
    return tabs


def _raw_json(key: str) -> dict:
    path = OUTPUTS / "jira" / "raw" / f"{key}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _attachment_count(key: str) -> int:
    return len(_raw_json(key).get("attachments", []))


_ROLLUP_FILENAME = re.compile(r"^issue-summary-\d{4}-\d{2}-\d{2}\.md$")


def _pipeline_file_flags(key: str, status: str = "") -> dict[str, bool]:
    """Which pipeline output files exist for this issue (for dashboard / API)."""
    # Phase 2: check investigation_cache before disk I/O for investigation/solution flags
    cache_key = _instance_cache_key(key)
    if cache_key in investigation_cache:
        cached = investigation_cache[cache_key]
        has_investigation = cached["has_investigation"]
        has_solution = cached["has_solution"]
    else:
        has_investigation = (OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)).exists()
        has_solution = (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists() and (OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key)).exists()
        investigation_cache[cache_key] = {"has_investigation": has_investigation, "has_solution": has_solution}  # has_solution: analysis complete + customer notified
        _cache_evict(investigation_cache)

    has_internal_notes = (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists()
    has_eng_handoff = (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).exists()
    is_jira_escalated = _is_jira_engineering_escalated(status)
    is_jira_escalated_any = _is_jira_escalated_any(status)
    state = _calculate_pipeline_state(key, status)

    return {
        # Legacy flags (kept for backward compatibility during transition)
        "has_jira_summary": (OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key)).exists(),
        "has_investigation": has_investigation,
        "has_internal_notes": has_internal_notes,
        "has_jira_message": (OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key)).exists(),
        "has_test_report": (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists(),
        "has_eng_handoff": has_eng_handoff,
        "has_confirmed_solution": _test_report_confirms_fix(key),
        "has_solution": has_solution,
        "needs_escalation": has_eng_handoff and not is_jira_escalated_any,
        "is_jira_escalated": is_jira_escalated,
        "is_jira_escalated_any": is_jira_escalated_any,

        # Pipeline state machine: all determined by file existence
        "pipeline_state": state.value,
        "is_escalation_path": has_eng_handoff,  # Source of truth: eng_handoff file presence
        "is_blocked": _investigation_indicates_blocked(key),
        "is_data_only": _test_report_is_data_only(key),
    }


def _investigation_indicates_blocked(key: str) -> bool:
    """True when the investigation explicitly marks the issue as externally blocked.

    Do not treat narrative/debugging phrases such as "I am completely blocked"
    as an issue blocker; those are Claude/runtime statements, not customer-facing
    workflow state.
    """
    path = OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _text_indicates_issue_blocked(text)


def _blocker_section_text(text: str) -> str:
    m = re.search(r"(?im)^##\s*Blocker\s*:?\s*$", text)
    if not m:
        return ""
    after = text[m.end() :]
    lines: list[str] = []
    for raw in after.splitlines():
        if re.match(r"^\s*##\s", raw) and lines:
            break
        if raw.strip():
            lines.append(raw.strip())
    return "\n".join(lines).strip()


def _text_indicates_issue_blocked(text: str) -> bool:
    """Classify explicit issue blockers without matching generic prose."""
    blocker = _blocker_section_text(text)
    if blocker:
        if re.search(r"(?im)^\s*(none|n/a|not\s+blocked|no\s+blocker|no\s+external\s+blocker)\b", blocker):
            return False
        if re.search(
            r"(?im)\b("
            r"waiting\s+(?:for|on)|awaiting|pending\s+(?:customer|user|requester|support|engineering)|"
            r"requires?\s+(?:customer|user|requester|external|support|engineering)|"
            r"blocked\s+by|on\s+hold|cannot\s+proceed\s+until"
            r")\b",
            blocker,
        ):
            return True

    explicit_line_patterns = (
        r"^\s*(?:status|pipeline\s+status|issue\s+status)\s*:\s*(?:blocked|on\s+hold)\b",
        r"^\s*(?:blocked\s+by|blocker)\s*:\s*(?!none\b|n/a\b|no\s+blocker\b).+",
        r"^\s*(?:waiting\s+(?:for|on)|awaiting)\s+(?:customer|user|requester|support|engineering|external)\b",
        r"^\s*(?:pending|requires?)\s+(?:customer|user|requester|external|support|engineering)\b",
        r"^\s*cannot\s+proceed\s+until\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) for pattern in explicit_line_patterns)


def _extract_blocker_reason(key: str) -> str:
    """Extract blocker reason from ## Blocker: section in investigation file."""
    path = OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    blocker = _blocker_section_text(text)
    if not blocker:
        return ""
    block_lines: list[str] = []
    for raw in blocker.splitlines():
        s = raw.strip()
        if s:
            block_lines.append(s)
        if len(block_lines) > 5:
            break
    return " ".join(block_lines) if block_lines else ""


def _test_report_is_data_only(key: str) -> bool:
    """True when test report indicates fix is data-only (no metadata deployment)."""
    path = OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r"(?im)data.?only|no\s+metadata|no\s+deploy|permission\s+set|report|record\s+update", text))


def _calculate_pipeline_state(key: str, status: str = "") -> PipelineState:
    """Calculate current pipeline state based on file existence.

    Jira status is the only source of truth for actual Jira escalation.
    An eng_handoff file means CaseOps has prepared/recommended escalation.
    Support-resolvable progression based on pipeline file artifacts.
    """
    has_investigation = (OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)).exists()
    has_internal_notes = (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists()
    has_test_report = (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists()
    has_eng_handoff = (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).exists()

    if _is_jira_engineering_escalated(status):
        return PipelineState.ESCALATED_TO_ENGINEERING
    if has_eng_handoff:
        return PipelineState.ENGINEERING_HANDOFF

    # Support-resolvable progression
    if not has_investigation:
        return PipelineState.UNTRIAGED
    elif not has_internal_notes:
        return PipelineState.INVESTIGATING
    elif not has_test_report:
        return PipelineState.ANALYZED
    else:
        return PipelineState.VALIDATED


def _test_report_confirms_fix(key: str) -> bool:
    """True when outputs/test-reports/<KEY>.md marks Fixed? affirmatively (Sandbox validation)."""
    path = OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    m = re.search(r"(?im)^##\s*Fixed\?\s*$", text)
    if not m:
        return False
    after = text[m.end() :]
    block_lines: list[str] = []
    for raw in after.splitlines():
        if re.match(r"^\s*##\s", raw) and block_lines:
            break
        s = raw.strip()
        if s:
            block_lines.append(s)
        if len(block_lines) > 24:
            break
    if not block_lines:
        return False
    blob = " ".join(block_lines).lower()
    if re.search(r"\b(no|not\s+fixed|false|fail(?:ed|ing)?|unfixed)\b", blob):
        return False
    if re.search(r"\b(yes|pass(?:ed)?|confirmed|resolved)\b", blob):
        return True
    first = block_lines[0].lower().lstrip("-*•").strip()
    return first in ("yes", "y", "true", "✓", "ok")


def _latest_issue_summary_path() -> Path | None:
    candidates = list(OUTPUTS.glob("issue-summary-*.md"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _claude_prompt(key: str, summary: str) -> str:
    return (
        f'Process {key} through the mounted jira-salesforce-fix-pipeline playbook files. Do not invoke a slash-skill.\n\n'
        f'Issue: {summary}'
    )


def _due_end_ms(due_str: str) -> int | None:
    """Jira `duedate` is YYYY-MM-DD. Return UTC end-of-day epoch milliseconds, or None."""
    if not due_str or not str(due_str).strip():
        return None
    s = str(due_str).strip()[:10]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        eod = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return int(eod.timestamp() * 1000)
    except ValueError:
        return None


def _sla_remaining_ms(due_str: str) -> int | None:
    """Milliseconds until end of due date (negative if overdue). None if no due date."""
    end = _due_end_ms(due_str)
    if end is None:
        return None
    return end - int(time.time() * 1000)


# -- routes ------------------------------------------------------------------

@app.get("/")
@app.get("/overview")
def index():
    issues = _read_manifest()
    has_manifest = _manifest_path().exists()

    # Count open issues (not closed/resolved/canceled/escalated)
    open_count = _count_open_issues(issues)

    return render_template(
        "index.html",
        issues=issues,
        has_manifest=has_manifest,
        open_count=open_count,
        workspace=app.config.get("WORKSPACE", "default"),
    )


@app.get("/api/issues")
def api_issues():
    issues = _read_manifest()
    result = []
    for row in issues:
        key = row.get("Key", "")
        status = row.get("Status", "")
        flags = _pipeline_file_flags(key, status)
        due = row.get("Due", "") or ""
        has_new_comments = row.get("HasNewComments", "false").lower() == "true"
        result.append({
            "key": key,
            "status": status,
            "assignee": row.get("Assignee", ""),
            "summary": row.get("Summary", ""),
            "disposition": _disposition(status),
            "updated": row.get("Updated", ""),
            "due": due,
            "priority_name": row.get("Priority", "") or "",
            "sla_remaining_ms": _sla_remaining_ms(due),
            "jira_url": f"{JIRA_BASE_URL}/browse/{key}" if JIRA_BASE_URL else "",
            "hasNewComments": has_new_comments,
            **flags,
        })
    return jsonify(result)


@app.get("/api/latest-issue-summary")
def api_latest_issue_summary():
    path = _latest_issue_summary_path()
    if not path:
        return jsonify({"label": None, "url": None})
    name = path.name
    return jsonify({"label": name, "url": f"/files/rollup/{name}"})


def _get_issue_reporter(key: str) -> str:
    """Extract reporter from raw JSON (synced by jira_sync.py)."""
    raw = _raw_json(key)
    # Raw JSON structure: { "issue": { "fields": { "reporter": {...} } } }
    reporter = raw.get("issue", {}).get("fields", {}).get("reporter", {})
    if isinstance(reporter, dict):
        name = reporter.get("displayName", "")
        if name:
            return name
    # If reporter not found, return empty string (don't use fallback)
    return ""


@app.get("/api/issue/<key>")
def api_issue(key: str):
    issues = _read_manifest()
    row = next((r for r in issues if r.get("Key") == key), None)
    if not row:
        return jsonify({"error": "not found"}), 404
    status = row.get("Status", "")
    due = row.get("Due", "") or ""
    flags = _pipeline_file_flags(key, status)
    tabs = _available_tabs(key)
    return jsonify({
        "key": key,
        "status": row.get("Status", ""),
        "assignee": row.get("Assignee", ""),
        "summary": row.get("Summary", ""),
        "disposition": _disposition(row.get("Status", "")),
        "updated": row.get("Updated", ""),
        "due": due,
        "priority_name": row.get("Priority", "") or "",
        "sla_remaining_ms": _sla_remaining_ms(due),
        "tabs": tabs,
        "claude_prompt": _claude_prompt(key, row.get("Summary", "")),
        "jira_url": f"{JIRA_BASE_URL}/browse/{key}" if JIRA_BASE_URL else "",
        "reporter": _get_issue_reporter(key),
        **flags,
    })


@app.get("/api/issue/<key>/file/<ftype>")
def api_file(key: str, ftype: str):
    rel = FILE_LOCATIONS.get(ftype)
    if not rel:
        return jsonify({"error": "unknown file type"}), 400

    # Phase 2: serve jira_summary from cache (check before disk I/O)
    cache_key = _instance_cache_key(key)
    if ftype == "jira_summary" and cache_key in jira_summary_cache:
        return jsonify(jira_summary_cache[cache_key])

    path = OUTPUTS / rel.format(key=key)
    if not path.exists():
        return jsonify({"html": "<p class='empty'>File not yet generated.</p>"})
    text = path.read_text(encoding="utf-8", errors="replace")
    result = {"html": render_md(text), "raw": text}

    # Add blocker reason if investigation file
    if ftype == "investigation":
        blocker = _extract_blocker_reason(key)
        if blocker:
            result["blocker_reason"] = blocker

    # Phase 2: populate jira_summary cache
    if ftype == "jira_summary":
        jira_summary_cache[cache_key] = result
        _cache_evict(jira_summary_cache)

    return jsonify(result)


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "full")
    key = data.get("key", "")

    is_global = action in ("sync", "full", "reprocess", "sync_new")
    run_key = _GLOBAL_KEY if is_global else key

    env_file = app.config.get("ENV_FILE_PATH", str(ROOT / ".env.jira"))
    use_claude_cli = False
    use_full_issue = False
    use_reprocess_issue = False
    use_global_skill = False

    if action == "sync":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file, "--out-dir", str(OUTPUTS / "jira")]
    elif action == "sync_new":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file, "--new-only", "--out-dir", str(OUTPUTS / "jira")]
    elif action == "sync_issue" and key:
        cmd = [
            sys.executable,
            "run_pipeline.py",
            "--env-file",
            env_file,
            "--jira-dir",
            str(OUTPUTS / "jira"),
            "--outputs-dir",
            str(OUTPUTS),
            "--issue",
            key,
            "--no-agents",
        ]
    elif action == "reprocess":
        use_global_skill = True
        instruction = "Run the full CaseOps fix pipeline: reprocess all active issues without re-syncing from Jira. Use the mounted jira-salesforce-fix-pipeline playbook files in reprocess mode; do not invoke a slash-skill."
    elif action == "full":
        use_global_skill = True
        instruction = "Run the full CaseOps fix pipeline: sync all issues from Jira and process all active issues through completion. Use the mounted jira-salesforce-fix-pipeline playbook files in full mode; do not invoke a slash-skill."
    elif action == "full_issue" and key:
        use_full_issue = True
    elif action == "reprocess_issue" and key:
        use_reprocess_issue = True
    elif action == "claude_instruction" and key:
        instruction = data.get("instruction", "").strip()
        if not instruction:
            return jsonify({"error": "No instruction provided."}), 400
        use_claude_cli = True
        prompt = _build_claude_prompt(key, instruction)
    else:
        return jsonify({"error": "unknown action"}), 400

    with _state_lock:
        if run_key in _active_keys:
            label = "A global run" if run_key == _GLOBAL_KEY else run_key
            return jsonify({"error": f"{label} is already running."}), 409
        if not is_global and _GLOBAL_KEY in _active_keys:
            return jsonify({"error": "A global sync is in progress — please wait."}), 409
        _active_keys.add(run_key)

    if use_full_issue:
        t = threading.Thread(target=_stream_full_issue, args=(key, run_key), daemon=True)
    elif use_reprocess_issue:
        t = threading.Thread(target=_stream_reprocess_issue, args=(key, run_key), daemon=True)
    elif use_global_skill:
        t = threading.Thread(target=_stream_global_skill, args=(instruction, run_key), daemon=True)
    elif use_claude_cli:
        t = threading.Thread(target=_stream_claude_proc, args=(prompt, run_key, key), daemon=True)
    else:
        t = threading.Thread(target=_stream_proc, args=(cmd, run_key), daemon=True)
    t.start()

    return jsonify({"started": True, "action": action, "key": key, "run_key": run_key})


@app.get("/api/stream")
def api_stream():
    def generate():
        while True:
            try:
                msg = _log_q.get(timeout=15)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            for line in msg.split("\n"):
                yield f"data: {line}\n"
            yield "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/issues-sse")
def api_issues_sse():
    """Stream manifest changes to update issue cards in real-time."""
    def generate():
        while True:
            try:
                msg = _manifest_q.get(timeout=20)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {msg}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/status")
def api_status():
    with _state_lock:
        return jsonify({
            "active_keys": list(_active_keys),
            "count": len(_active_keys),
            "caseops_llm_auth": (
                "api_key" if caseops_llm_auth_uses_anthropic_api_key() else "claude_code"
            ),
            "caseops_llm_backend": (
                "anthropic_messages_api"
                if caseops_llm_auth_uses_anthropic_api_key()
                else "claude_code_cli"
            ),
        })


@app.get("/api/pipeline-log/<key>")
def api_pipeline_log(key: str):
    """JSONL-backed history for global runs (__global__) or a Jira issue key.

    Query params:
      tail=N  Return only the last N entries (optional, default all).
    """
    entries = _read_pipeline_log_entries(key)
    tail = request.args.get("tail", type=int)
    if tail and tail > 0:
        entries = entries[-tail:]
    return jsonify({"entries": entries})


@app.post("/api/pipeline-log/clear")
def api_pipeline_log_clear():
    """Remove one pipeline log file (JSON body: {\"key\": \"HEAL-1\"} or __global__)."""
    data = request.get_json(silent=True) or {}
    run_key = (data.get("key") or data.get("run_key") or "").strip()
    if not run_key:
        return jsonify({"error": "key required"}), 400
    with _PIPELINE_LOG_LOCK:
        p = _pipeline_log_path(run_key)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                return jsonify({"error": "could not delete log file"}), 500
    return jsonify({"ok": True})


@app.get("/api/issue/<key>/attachments")
def api_attachments(key: str):
    raw = _raw_json(key)
    atts = raw.get("attachments", [])
    result = []
    for a in atts:
        att_id   = a.get("id", "")
        filename = a.get("filename", "")
        disk_name = f"{att_id}-{filename}"
        result.append({
            "id":       att_id,
            "filename": filename,
            "mimeType": a.get("mimeType", ""),
            "size":     a.get("size", 0),
            "created":  a.get("created", ""),
            "author":   a.get("author", {}).get("displayName", ""),
            "url":      f"/files/attachments/{key}/{disk_name}",
        })
    return jsonify(result)


@app.post("/api/issue/<key>/comment")
def api_post_comment(key: str):
    data = request.get_json(silent=True) or {}
    body = data.get("body", "").strip()
    is_public = data.get("public", True)
    if not body:
        return jsonify({"error": "No body provided."}), 400
    if not JIRA_BASE_URL:
        return jsonify({"error": "JIRA_BASE_URL not configured."}), 500

    # Append signature to public Jira messages
    if is_public:
        sig_file = ROOT / "jira-signature.txt"
        if sig_file.exists():
            signature = sig_file.read_text(encoding="utf-8").strip()
            body = f"{body}\n\n{signature}"

    try:
        auth = _jira_auth_header()
        payload = json.dumps({"body": body, "public": is_public}).encode("utf-8")
        req = urllib.request.Request(
            f"{JIRA_BASE_URL}/rest/servicedeskapi/request/{key}/comment",
            data=payload,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return jsonify({"ok": True, "id": result.get("id", "")})
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return jsonify({"error": f"Jira {exc.code}: {details[:300]}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/issue/<key>/transitions")
def api_issue_transitions(key: str):
    _load_jira_env(Path(app.config.get("ENV_FILE_PATH", ROOT / ".env.jira")))  # Use instance-specific .env.jira
    try:
        auth = _jira_auth_header()
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    if not JIRA_BASE_URL:
        return jsonify({"error": "JIRA_BASE_URL not configured"}), 500
    client = JiraClient(base_url=JIRA_BASE_URL, auth_header=auth)
    try:
        transitions = client.get_transitions(key)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502
    return jsonify(transitions)


@app.post("/api/issue/<key>/transition")
def api_issue_transition(key: str):
    data = request.get_json(silent=True) or {}
    transition_id = str(data.get("transition_id", "")).strip()
    new_status = str(data.get("new_status", "")).strip()
    if not transition_id:
        return jsonify({"error": "transition_id required"}), 400

    _load_jira_env(Path(app.config.get("ENV_FILE_PATH", ROOT / ".env.jira")))  # Use instance-specific .env.jira
    try:
        auth = _jira_auth_header()
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    if not JIRA_BASE_URL:
        return jsonify({"error": "JIRA_BASE_URL not configured"}), 500
    client = JiraClient(base_url=JIRA_BASE_URL, auth_header=auth)
    try:
        client.apply_transition(key, transition_id)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502

    # Update local manifest
    try:
        update_manifest_status(key, new_status, default_jira_dir())
    except Exception as e:
        sys.stderr.write(f"Warning: failed to update manifest for {key}: {e}\n")

    return jsonify({"ok": True, "new_status": new_status})


@app.post("/api/issue/<key>/mark-viewed")
def api_issue_mark_viewed(key: str):
    """Clear the HasNewComments flag for an issue."""
    manifest_path = _manifest_path()
    if not manifest_path.exists():
        return jsonify({"error": "manifest not found"}), 404

    fieldnames = ["Key", "Status", "Summary", "Updated", "Due", "Priority", "RawPath", "SummaryPath",
                  "AttachmentCount", "FormCount", "CommentCount", "HasNewComments", "EscalationReady"]
    rows: list[dict[str, str]] = []
    try:
        with manifest_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows.append({fn: row.get(fn, "") for fn in fieldnames})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500

    found = False
    for row in rows:
        if row.get("Key") == key:
            row["HasNewComments"] = "false"
            found = True
            break

    if not found:
        return jsonify({"error": f"issue {key} not found"}), 404

    _validate_instance_path(manifest_path, "write")  # HARD RULE: instance-routed writes only
    try:
        with manifest_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500

    return jsonify({"ok": True, "key": key})


@app.route("/api/canned-messages", methods=["GET"])
def api_canned_messages():
    messages_file, _ = _active_canned_messages_file()

    if not messages_file.exists():
        return jsonify([])
    try:
        messages = json.loads(messages_file.read_text(encoding="utf-8"))
        return jsonify(messages)
    except Exception:
        return jsonify([])


@app.route("/api/issue/<key>/send-canned-message", methods=["POST"])
def api_send_canned_message(key: str):
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id", "").strip()
    if not message_id:
        return jsonify({"error": "message_id required"}), 400

    messages_file, _ = _active_canned_messages_file()

    if not messages_file.exists():
        return jsonify({"error": "No canned messages configured"}), 400
    try:
        messages = json.loads(messages_file.read_text(encoding="utf-8"))
    except Exception:
        return jsonify({"error": "Failed to load canned messages"}), 500

    message = next((m for m in messages if m.get("id") == message_id), None)
    if not message:
        return jsonify({"error": "Message not found"}), 404

    template = message.get("template", "")
    reporter = _get_issue_reporter(key)

    body = template.replace("{{issueReporter}}", reporter).replace("{{issueKey}}", key)

    # Add signature: replace placeholder if present, otherwise append at end
    sig_file = ROOT / "jira-signature.txt"
    sig = sig_file.read_text(encoding="utf-8").strip() if sig_file.exists() else ""
    if sig:
        if "[insert signature]" in body:
            body = body.replace("[insert signature]", sig)
        else:
            body = body.rstrip() + "\n\n" + sig

    if not JIRA_BASE_URL:
        return jsonify({"error": "JIRA_BASE_URL not configured"}), 500

    try:
        auth = _jira_auth_header()
        payload = json.dumps({"body": body, "public": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{JIRA_BASE_URL}/rest/servicedeskapi/request/{key}/comment",
            data=payload,
            headers={
                "Authorization": auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Auto-transition to Resolved for closing-response message
        if message_id == "closing-response":
            try:
                from jira_sync import JiraClient
                client = JiraClient(JIRA_BASE_URL, auth)
                transitions = client.get_transitions(key)
                resolved_transition = next(
                    (t for t in transitions if t["to_status"].lower() == "resolved"),
                    None
                )
                if resolved_transition:
                    client.apply_transition(key, resolved_transition["id"])
            except Exception:
                pass  # Non-fatal — comment was posted successfully

        return jsonify({"ok": True, "id": result.get("id", "")})
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return jsonify({"error": f"Jira {exc.code}: {details[:300]}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)[:300]}), 500


@app.get("/api/issue/<key>/confidence-flag")
def api_confidence_flag(key: str):
    """Phase 4: Return confidence flag for a step8 investigation.

    Returns {"confidence": "high"|"low"|"none", "investigation_tokens": N}
    """
    flags_dir = OUTPUTS / "confidence-flags"
    for level in ("high", "low"):
        flag_file = flags_dir / f"{key}.{level}"
        if flag_file.exists():
            try:
                text = flag_file.read_text(encoding="utf-8")
                tokens = 0
                for line in text.splitlines():
                    if line.startswith("tokens="):
                        tokens = int(line.split("=", 1)[1])
            except Exception:
                tokens = 0
            return jsonify({"confidence": level, "investigation_tokens": tokens})
    return jsonify({"confidence": "none", "investigation_tokens": 0})


@app.get("/api/issue/<key>/deployment-status")
def api_deployment_status(key: str):
    """Return deployment validation status for an issue.

    Returns {"status": "validated"|"pending"|"failed"|"none"}
    """
    validation_dir = OUTPUTS / "deployment-validation"
    for status in ("validated", "pending", "failed"):
        flag_file = validation_dir / f"{key}.{status}"
        if flag_file.exists():
            return jsonify({"status": status})
    return jsonify({"status": "none"})


@app.post("/api/issue/<key>/deployment-status")
def set_deployment_status(key: str):
    """Set deployment validation status for an issue.

    Expects JSON: {"status": "validated"|"pending"|"failed"}
    """
    try:
        data = request.get_json() or {}
        status = data.get("status", "").lower()

        if status not in ("validated", "pending", "failed"):
            return jsonify({"error": f"Invalid status: {status}"}), 400

        validation_dir = OUTPUTS / "deployment-validation"
        validation_dir.mkdir(parents=True, exist_ok=True)

        for s in ("validated", "pending", "failed"):
            flag_file = validation_dir / f"{key}.{s}"
            flag_file.unlink(missing_ok=True)

        new_flag = validation_dir / f"{key}.{status}"
        new_flag.write_text("", encoding="utf-8")

        return jsonify({"status": status, "message": f"Deployment status updated to {status}"})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.get("/files/attachments/<key>/<path:filename>")
def serve_attachment(key: str, filename: str):
    att_dir = OUTPUTS / "jira" / "attachments" / key
    path = (att_dir / filename).resolve()
    if not str(path).startswith(str(att_dir.resolve())):
        return jsonify({"error": "forbidden"}), 403
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(path)


@app.get("/files/rollup/<path:filename>")
def serve_issue_rollup(filename: str):
    if not _ROLLUP_FILENAME.match(filename):
        return jsonify({"error": "invalid"}), 400
    path = (OUTPUTS / filename).resolve()
    out = OUTPUTS.resolve()
    try:
        path.relative_to(out)
    except ValueError:
        return jsonify({"error": "forbidden"}), 403
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path)


def _resolve_artifact_id(artifact_type: str, api_name: str, org_identifier: str) -> str | None:
    """Query Salesforce for artifact ID by type and API name. Returns ID or None if not found."""
    workspace = os.environ.get("CASEOPS_WORKSPACE", "default")
    cache_key = f"{workspace}:{artifact_type}:{api_name}:{org_identifier}"

    # Check cache
    if cache_key in artifact_metadata_cache:
        entry = artifact_metadata_cache[cache_key]
        if time.time() < entry.get("expires", 0):
            return entry.get("id")
        else:
            artifact_metadata_cache.pop(cache_key, None)

    artifact_type_key = artifact_type.replace("-", "").replace("_", "").lower()
    artifact_type_map = {
        "field": "Field",
        "permissionset": "PermissionSet",
        "profile": "Profile",
        "flow": "Flow",
        "validationrule": "ValidationRule",
        "customobject": "CustomObject",
        "apexclass": "ApexClass",
        "apextrigger": "ApexTrigger",
        "apexpage": "ApexPage",
        "customsetting": "CustomSetting",
    }
    artifact_type = artifact_type_map.get(artifact_type_key, artifact_type)

    # Map artifact type to Salesforce metadata query
    queries = {
        "Field": f"SELECT Id FROM FieldDefinition WHERE QualifiedApiName = '{api_name}'",
        "PermissionSet": f"SELECT Id FROM PermissionSet WHERE Name = '{api_name.split('.')[-1] if '.' in api_name else api_name}'",
        "Profile": f"SELECT Id FROM Profile WHERE Name = '{api_name}'",
        "Flow": f"SELECT Id FROM Flow WHERE DeveloperName = '{api_name}'",
        "ValidationRule": f"SELECT Id FROM ValidationRule WHERE ValidationName = '{api_name}'",
        "CustomObject": f"SELECT Id FROM CustomObject WHERE DeveloperName = '{api_name}'",
        "ApexClass": f"SELECT Id FROM ApexClass WHERE Name = '{api_name}'",
        "ApexTrigger": f"SELECT Id FROM ApexTrigger WHERE Name = '{api_name}'",
        "ApexPage": f"SELECT Id FROM ApexPage WHERE Name = '{api_name}'",
        "CustomSetting": f"SELECT Id FROM CustomSetting WHERE DeveloperName = '{api_name}'",
    }

    if artifact_type not in queries:
        return None

    tooling_types = {"Field", "Flow", "ValidationRule", "CustomObject", "ApexClass", "ApexTrigger", "ApexPage", "CustomSetting"}

    try:
        # Determine target org
        if org_identifier == "sandbox":
            target_org = os.environ.get("CASEOPS_SANDBOX_TARGET_ORG", "")
        else:
            target_org = os.environ.get("CASEOPS_PRODUCTION_READ_ORG", "")

        if not target_org:
            return None

        # Query via sf CLI
        cmd = [
            shutil.which("sf") or shutil.which("sf.cmd") or "sf",
            "data", "query",
            "--query", queries[artifact_type],
            "--target-org", target_org,
            "--json"
        ]
        if artifact_type in tooling_types:
            cmd.insert(3, "--use-tooling-api")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])

        if not records:
            return None

        artifact_id = records[0].get("Id")

        # Cache result
        if artifact_id:
            artifact_metadata_cache[cache_key] = {
                "id": artifact_id,
                "expires": time.time() + _ARTIFACT_CACHE_TTL_SECONDS
            }

        return artifact_id

    except Exception:
        return None


@app.post("/api/resolve-artifact")
def api_resolve_artifact():
    """Resolve Salesforce artifact ID from type and API name.

    POST /api/resolve-artifact
    Body: {"type": "Field", "apiName": "Product2.Calendly_Booking_Form_Name__c", "org": "sandbox"}

    Response: {"id": "00N...", "cached": false} or {"id": null} if not found
    """
    body = request.get_json() or {}
    artifact_type = body.get("type", "").strip()
    api_name = body.get("apiName", "").strip()
    org_identifier = body.get("org", "sandbox").strip()

    if not artifact_type or not api_name:
        return jsonify({"error": "missing type or apiName"}), 400

    # Check cache status before query
    cache_key = f"{artifact_type}:{api_name}:{org_identifier}"
    was_cached = cache_key in artifact_metadata_cache and time.time() < artifact_metadata_cache[cache_key].get("expires", 0)

    artifact_id = _resolve_artifact_id(artifact_type, api_name, org_identifier)

    return jsonify({
        "id": artifact_id,
        "cached": was_cached
    })


@app.get("/api/magic-links")
def api_magic_links():
    """Return Salesforce magic links for GUI artifact linkification."""
    return jsonify({
        "prod": os.environ.get("CASEOPS_PRODUCTION_MAGIC_LINK", ""),
        "sandbox": os.environ.get("CASEOPS_SANDBOX_MAGIC_LINK", ""),
    })


@app.route("/api/orgs", methods=["GET"])
def api_orgs():
    """Return Salesforce org identifiers from .env.jira for URL construction."""
    return jsonify({
        "prod": os.environ.get("CASEOPS_PRODUCTION_READ_ORG", ""),
        "sandbox": os.environ.get("CASEOPS_SANDBOX_TARGET_ORG", ""),
    })


@app.post("/api/manifest-changed")
def api_manifest_changed():
    """Signal that manifest.csv was updated (called by comments_poller)."""
    body = request.get_json(silent=True) or {}
    keys = body.get("keys")  # Optional list of changed issue keys
    manifest_changed(keys)
    return jsonify({"ok": True})


@app.route("/settings", methods=["GET"])
def settings_page():
    """Render settings.html."""
    return render_template("settings.html")


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return current settings from .env.jira with secrets masked."""
    env_file_path = app.config.get("ENV_FILE_PATH")
    settings = _read_env_file(Path(env_file_path) if env_file_path else None)

    # Settings to expose in UI
    exposed_keys = {
        "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
        "CASEOPS_LLM_AUTH", "CASEOPS_ANTHROPIC_MODEL",
        "CASEOPS_USE_CCI_FOR_AUTH",
        "CASEOPS_PRODUCTION_READ_ORG", "CASEOPS_SANDBOX_TARGET_ORG",
        "CASEOPS_PRODUCTION_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL",
    }

    response = {}
    for key in exposed_keys:
        value = settings.get(key, "")
        # Mask secrets (but not URLs, aliases, or boolean flags)
        if key in ("JIRA_API_TOKEN",):
            response[key] = _mask_secret(value)
        else:
            response[key] = value

    return jsonify(response)


@app.route("/api/settings", methods=["POST"])
def api_post_settings():
    """Save settings to .env.jira. Preserves masked values (doesn't overwrite)."""
    body = request.get_json(silent=True) or {}

    # Filter and validate (CASEOPS_LLM_AUTH is read-only, set via .env.jira only)
    updates = {}
    for key in ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
                "CASEOPS_ANTHROPIC_MODEL",
                "CASEOPS_USE_CCI_FOR_AUTH",
                "CASEOPS_PRODUCTION_READ_ORG", "CASEOPS_SANDBOX_TARGET_ORG",
                "CASEOPS_PRODUCTION_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL"]:
        value = body.get(key, "").strip()
        # Skip masked values (user didn't change them)
        if value.startswith("••••"):
            continue
        updates[key] = value

    try:
        env_file_path = app.config.get("ENV_FILE_PATH")
        _write_env_file(updates, Path(env_file_path) if env_file_path else None)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/test-jira", methods=["POST"])
def api_test_jira():
    """Test Jira connection with provided credentials."""
    body = request.get_json(silent=True) or {}
    base_url = body.get("JIRA_BASE_URL", "").strip()
    email = body.get("JIRA_EMAIL", "").strip()
    token = body.get("JIRA_API_TOKEN", "").strip()

    if not all([base_url, email, token]):
        return jsonify({"error": "Missing credentials"}), 400

    try:
        # Build auth header
        auth_header = f"Basic {base64.b64encode(f'{email}:{token}'.encode()).decode()}"

        # Try to fetch current user (minimal Jira call, works on v2 & v3)
        url = f"{base_url.rstrip('/')}/rest/api/3/myself"
        req = urllib.request.Request(url, headers={"Authorization": auth_header})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return jsonify({"ok": True})
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"Jira {e.code}: {e.reason}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"error": "Unknown error"}), 500


@app.route("/api/settings/canned-messages", methods=["GET"])
def api_settings_get_canned_messages():
    """Get current canned messages (instance-specific or default)."""
    messages_file, is_custom = _active_canned_messages_file()

    try:
        content = messages_file.read_text(encoding="utf-8")
        json.loads(content)  # Validate JSON
        try:
            path = str(messages_file.relative_to(ROOT))
        except ValueError:
            path = str(messages_file)
        return jsonify({
            "content": content,
            "is_custom": is_custom,
            "path": path
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/canned-messages", methods=["POST"])
def api_settings_set_canned_messages():
    """Update canned messages in persistent mounted storage."""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"error": "content required"}), 400

    # Validate JSON
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    messages_file = _persistent_canned_messages_file()

    try:
        messages_file.parent.mkdir(parents=True, exist_ok=True)
        messages_file.parent.chmod(0o775)
        messages_file.write_text(content, encoding="utf-8")
        messages_file.chmod(0o664)
        try:
            path = str(messages_file.relative_to(ROOT))
        except ValueError:
            path = str(messages_file)
        return jsonify({
            "ok": True,
            "path": path,
            "is_custom": True
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/canned-messages/reset", methods=["POST"])
def api_settings_reset_canned_messages():
    """Reset to default canned messages by deleting custom overrides."""
    messages_files = [_persistent_canned_messages_file()]
    legacy = _legacy_canned_messages_file()
    if legacy:
        messages_files.append(legacy)

    try:
        deleted = []
        for messages_file in messages_files:
            if messages_file.exists():
                messages_file.unlink()
                deleted.append(str(messages_file))
        if not (ROOT / "canned-messages.json").exists():
            return jsonify({"error": "Default canned-messages.json is missing"}), 500
        return jsonify({"ok": True, "message": "Reset to default messages", "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _settings_status_skeleton() -> dict[str, Any]:
    env_file_path = app.config.get("ENV_FILE_PATH")
    settings = _read_env_file(Path(env_file_path) if env_file_path else None)
    prod_alias = _env_first("CASEOPS_PRODUCTION_READ_ORG", settings=settings)
    sand_alias = _env_first("CASEOPS_SANDBOX_TARGET_ORG", settings=settings)

    return {
        "claude": {
            "installed": bool(shutil.which("claude")),
            "authenticated": False,
            "token_configured": bool((os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()),
        },
        "sf_installed": bool(shutil.which("sf")),
        "sf_prod": {"authenticated": False, "alias": prod_alias},
        "sf_sandbox": {"authenticated": False, "alias": sand_alias},
        "cci_installed": bool(shutil.which("cumulusci") or shutil.which("cci")),
        "cci_prod": {"authenticated": False},
        "cci_sandbox": {"authenticated": False},
    }


def _build_settings_status() -> dict[str, Any]:
    """Run the full Settings status probe. This may take several seconds."""
    status = _settings_status_skeleton()
    env_file_path = app.config.get("ENV_FILE_PATH")
    settings = _read_env_file(Path(env_file_path) if env_file_path else None)
    prod_alias = _env_first("CASEOPS_PRODUCTION_READ_ORG", settings=settings)
    sand_alias = _env_first("CASEOPS_SANDBOX_TARGET_ORG", settings=settings)

    use_cci = os.environ.get("CASEOPS_USE_CCI_FOR_AUTH", "false").lower() == "true"

    # Check Claude
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            status["claude"]["installed"] = True
            status["claude"]["version"] = result.stdout.strip()
            status["claude"]["token_configured"] = bool(
                (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
            )
            auth_result = subprocess.run(
                ["claude", "auth", "status"],
                env=_claude_process_env(),
                capture_output=True,
                text=True,
                timeout=10,
            )
            status["claude"]["authenticated"] = auth_result.returncode == 0
            if auth_result.stdout.strip().startswith("{"):
                try:
                    status["claude"]["auth_status"] = json.loads(auth_result.stdout)
                except json.JSONDecodeError:
                    pass
            if not status["claude"]["authenticated"]:
                status["claude"]["auth_error"] = (auth_result.stderr or auth_result.stdout).strip()[:500]
    except Exception:
        pass

    # Check sf CLI
    if shutil.which("sf"):
        status["sf_installed"] = True

        # Check prod org
        if prod_alias:
            try:
                result = subprocess.run(
                    ["sf", "org", "display", "--target-org", prod_alias, "--json"],
                    capture_output=True, text=True, timeout=20
                )
                if result.returncode == 0:
                    # Skip warning lines, find JSON start
                    json_str = result.stdout.strip()
                    if json_str.startswith('{'):
                        data = json.loads(json_str)
                        status["sf_prod"]["authenticated"] = True
                        status["sf_prod"]["username"] = data.get("result", {}).get("username", "")
                        status["sf_prod"]["orgId"] = data.get("result", {}).get("id", "")
                        status["sf_prod"]["instanceUrl"] = data.get("result", {}).get("instanceUrl", "")
                    else:
                        # Find first { and parse from there
                        idx = json_str.find('{')
                        if idx >= 0:
                            data = json.loads(json_str[idx:])
                            status["sf_prod"]["authenticated"] = True
                            status["sf_prod"]["username"] = data.get("result", {}).get("username", "")
                            status["sf_prod"]["orgId"] = data.get("result", {}).get("id", "")
                            status["sf_prod"]["instanceUrl"] = data.get("result", {}).get("instanceUrl", "")
            except Exception:
                pass

        # Check sandbox org
        if sand_alias:
            try:
                result = subprocess.run(
                    ["sf", "org", "display", "--target-org", sand_alias, "--json"],
                    capture_output=True, text=True, timeout=20
                )
                if result.returncode == 0:
                    # Skip warning lines, find JSON start
                    json_str = result.stdout.strip()
                    if json_str.startswith('{'):
                        data = json.loads(json_str)
                        status["sf_sandbox"]["authenticated"] = True
                        status["sf_sandbox"]["username"] = data.get("result", {}).get("username", "")
                        status["sf_sandbox"]["orgId"] = data.get("result", {}).get("id", "")
                        status["sf_sandbox"]["instanceUrl"] = data.get("result", {}).get("instanceUrl", "")
                    else:
                        # Find first { and parse from there
                        idx = json_str.find('{')
                        if idx >= 0:
                            data = json.loads(json_str[idx:])
                            status["sf_sandbox"]["authenticated"] = True
                            status["sf_sandbox"]["username"] = data.get("result", {}).get("username", "")
                            status["sf_sandbox"]["orgId"] = data.get("result", {}).get("id", "")
                            status["sf_sandbox"]["instanceUrl"] = data.get("result", {}).get("instanceUrl", "")
            except Exception as e:
                print(f"DEBUG: sandbox auth check failed: {type(e).__name__}: {str(e)}", flush=True)

    # Check CCI
    if shutil.which("cumulusci") or shutil.which("cci"):
        status["cci_installed"] = True

        # Check prod org
        if prod_alias and use_cci:
            try:
                result = subprocess.run(
                    ["cci", "org", "info", prod_alias],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    status["cci_prod"]["authenticated"] = True
            except Exception:
                pass

        # Check sandbox org
        if sand_alias and use_cci:
            try:
                result = subprocess.run(
                    ["cci", "org", "info", sand_alias],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    status["cci_sandbox"]["authenticated"] = True
            except Exception:
                pass

    try:
        status["runtime_preflight"] = _collect_runtime_preflight(run_soql=False)
    except Exception as e:
        status["runtime_preflight"] = {
            "ok": False,
            "issues": [f"Runtime preflight status failed: {type(e).__name__}: {e}"],
        }

    status["cache"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "refreshing": False,
        "source": "fresh",
    }
    return status


def _settings_status_cache_fresh(now: float | None = None) -> bool:
    now = now or time.time()
    return bool(_settings_status_cache and (now - _settings_status_cache_time) < _SETTINGS_STATUS_CACHE_TTL)


def _refresh_settings_status_cache() -> None:
    global _settings_status_cache, _settings_status_cache_time, _settings_status_refreshing
    try:
        status = _build_settings_status()
        with _SETTINGS_STATUS_LOCK:
            _settings_status_cache = status
            _settings_status_cache_time = time.time()
    finally:
        with _SETTINGS_STATUS_LOCK:
            _settings_status_refreshing = False


def _start_settings_status_refresh_if_needed(force: bool = False) -> None:
    global _settings_status_refreshing
    with _SETTINGS_STATUS_LOCK:
        if _settings_status_refreshing:
            return
        if not force and _settings_status_cache_fresh():
            return
        _settings_status_refreshing = True
    threading.Thread(target=_refresh_settings_status_cache, daemon=True).start()


@app.route("/api/settings/status", methods=["GET"])
def api_settings_status():
    """Return cached Settings status quickly; use ?refresh=1 for a blocking deep probe."""
    global _settings_status_cache, _settings_status_cache_time
    force_refresh = request.args.get("refresh") in {"1", "true", "yes"}

    if force_refresh:
        status = _build_settings_status()
        with _SETTINGS_STATUS_LOCK:
            _settings_status_cache = status
            _settings_status_cache_time = time.time()
        status["cache"] = {**status.get("cache", {}), "source": "forced"}
        return jsonify(status)

    now = time.time()
    with _SETTINGS_STATUS_LOCK:
        cached = _settings_status_cache
        cache_time = _settings_status_cache_time
        refreshing = _settings_status_refreshing
    if cached and (now - cache_time) < _SETTINGS_STATUS_CACHE_TTL:
        status = json.loads(json.dumps(cached))
        status["cache"] = {
            **status.get("cache", {}),
            "age_seconds": round(now - cache_time, 1),
            "refreshing": refreshing,
            "source": "cache",
        }
        return jsonify(status)

    _start_settings_status_refresh_if_needed()
    status = json.loads(json.dumps(cached)) if cached else _settings_status_skeleton()
    status["runtime_preflight"] = status.get("runtime_preflight") or {
        "ok": None,
        "issues": ["Runtime preflight refresh is running."],
        "refreshing": True,
    }
    status["cache"] = {
        **status.get("cache", {}),
        "age_seconds": round(now - cache_time, 1) if cached else None,
        "refreshing": True,
        "source": "stale-cache" if cached else "fast-skeleton",
    }
    return jsonify(status)


@app.get("/setup/claude-login")
def setup_claude_login():
    """Serve Claude Code token setup form."""
    return render_template("claude-token-setup.html")


@app.post("/api/setup/claude-credentials")
def api_setup_claude_credentials():
    """Save Claude Code OAuth token generated by `claude setup-token`."""
    try:
        body = request.get_json(silent=True) or {}
        token = (body.get("token") or body.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
        credentials = body.get("credentials")

        # Backward-compatible parsing for the previous UI, which posted either a
        # raw token string or {"token": "..."} under "credentials".
        if not token and credentials:
            if isinstance(credentials, str):
                raw = credentials.strip()
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    token = raw
                else:
                    if isinstance(parsed, dict):
                        token = (
                            parsed.get("CLAUDE_CODE_OAUTH_TOKEN")
                            or parsed.get("token")
                            or parsed.get("accessToken")
                            or ""
                        ).strip()
                    else:
                        return jsonify({"error": "Credentials JSON must be an object"}), 400
            elif isinstance(credentials, dict):
                token = (
                    credentials.get("CLAUDE_CODE_OAUTH_TOKEN")
                    or credentials.get("token")
                    or credentials.get("accessToken")
                    or ""
                ).strip()
            else:
                return jsonify({"error": "Credentials must be a token string or JSON object"}), 400

        if not token:
            return jsonify({"error": "Missing Claude Code OAuth token"}), 400
        if token.startswith("export "):
            token = token.removeprefix("export ").strip()
        if token.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
            token = token.partition("=")[2].strip().strip('"').strip("'")
        if not token:
            return jsonify({"error": "Missing Claude Code OAuth token"}), 400
        if "\n" in token or "\r" in token:
            return jsonify({"error": "Paste only the token printed by `claude setup-token`, not a shell export line or multi-line output"}), 400

        env_file_path = app.config.get("ENV_FILE_PATH")
        env_file = Path(env_file_path) if env_file_path else ROOT / ".env.jira"
        _write_env_file({"CLAUDE_CODE_OAUTH_TOKEN": token}, env_file)
        _remove_env_keys({"CLAUDE_CREDENTIALS_B64"}, env_file)
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token

        return jsonify({
            "ok": True,
            "message": "Claude Code OAuth token saved",
            "env_key": "CLAUDE_CODE_OAUTH_TOKEN"
        })

    except Exception as e:
        return jsonify({"error": f"Failed to save Claude Code token: {str(e)}"}), 500

@app.post("/api/setup/salesforce-auth")
def api_setup_salesforce_auth():
    """Authenticate Salesforce orgs and validate they're accessible."""
    try:
        env_file_path = app.config.get("ENV_FILE_PATH")
        settings = _read_env_file(Path(env_file_path) if env_file_path else None)
        prod_alias = _env_first("CASEOPS_PRODUCTION_READ_ORG", settings=settings)
        sandbox_alias = _env_first("CASEOPS_SANDBOX_TARGET_ORG", settings=settings)
        prod_token = _env_first("SF_PROD_ACCESS_TOKEN", settings=settings)
        prod_url = _env_first("SF_PROD_INSTANCE_URL", "CASEOPS_PRODUCTION_INSTANCE_URL", settings=settings)
        sandbox_token = _env_first("SF_SANDBOX_ACCESS_TOKEN", settings=settings)
        sandbox_url = _env_first("SF_SANDBOX_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL", settings=settings)

        if not any([prod_token, sandbox_token]):
            return jsonify({"error": "No SF tokens in environment (SF_PROD_ACCESS_TOKEN or SF_SANDBOX_ACCESS_TOKEN)"}), 400

        # Auth both orgs
        def auth_org(alias: str, token: str, url: str) -> tuple[bool, str]:
            """Authenticate one org. Returns (success, message)."""
            if not alias:
                return False, "missing org alias (CASEOPS_PRODUCTION_READ_ORG or CASEOPS_SANDBOX_TARGET_ORG)"
            if not token or not url:
                return False, "missing token or url"
            try:
                env = os.environ.copy()
                env["SF_ACCESS_TOKEN"] = token
                env["HOME"] = str(Path.home())
                proc = subprocess.run(
                    ["sf", "org", "login", "access-token", "--alias", alias, "--instance-url", url, "--no-prompt"],
                    capture_output=True,
                    timeout=30,
                    check=False,
                    text=True,
                    env=env,
                )
                if proc.returncode != 0:
                    return False, f"{proc.stderr or proc.stdout}"
                return True, "authenticated"
            except subprocess.TimeoutExpired:
                return False, "timeout"
            except Exception as e:
                return False, str(e)

        # Authenticate orgs
        prod_ok, prod_msg = auth_org(prod_alias, prod_token, prod_url) if prod_token else (None, "skipped")
        sandbox_ok, sandbox_msg = auth_org(sandbox_alias, sandbox_token, sandbox_url) if sandbox_token else (None, "skipped")

        # Validate: run sf org list to verify orgs actually exist (cached for 10 min)
        def verify_orgs() -> dict:
            """Run sf org list and return authenticated orgs. Use cache if available."""
            global _sf_orgs_cache, _sf_orgs_cache_time
            now = time.time()

            # Check cache validity
            if _sf_orgs_cache is not None and (now - _sf_orgs_cache_time) < _SF_ORGS_CACHE_TTL:
                return _sf_orgs_cache

            # Cache miss or expired: run sf org list auth.
            # This reads local CLI auth without querying every org and is fast enough for UI refresh.
            try:
                proc = subprocess.run(
                    ["sf", "org", "list", "auth", "--json"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                    text=True,
                    env={**os.environ, "HOME": str(Path.home())},
                )
                if proc.returncode == 0:
                    data = json.loads(proc.stdout)
                    orgs = {}
                    result = data.get("result", [])
                    if isinstance(result, dict):
                        result = result.get("nonScratchOrgs", []) or result.get("orgs", [])
                    for org in result:
                        aliases = org.get("aliases") or []
                        alias = org.get("alias") or (aliases[0] if aliases else "") or org.get("username")
                        orgs[alias] = {
                            "alias": alias,
                            "username": org.get("username"),
                            "orgId": org.get("orgId") or org.get("id"),
                            "instanceUrl": org.get("instanceUrl"),
                        }
                    # Update cache
                    _sf_orgs_cache = orgs
                    _sf_orgs_cache_time = now
                    return orgs
                return {}
            except Exception:
                return {}

        verified_orgs = verify_orgs()

        # Final status
        final_ok = all([v for v in [prod_ok, sandbox_ok] if v is not None])

        return jsonify({
            "ok": final_ok,
            "authenticated_orgs": verified_orgs,
            "aliases": {
                "production": prod_alias,
                "sandbox": sandbox_alias,
            },
            "status": {
                prod_alias or "production": "authenticated" if prod_ok else (prod_msg if prod_ok is not None else "skipped"),
                sandbox_alias or "sandbox": "authenticated" if sandbox_ok else (sandbox_msg if sandbox_ok is not None else "skipped"),
            }
        })

    except Exception as e:
        return jsonify({"error": f"SF auth failed: {str(e)}"}), 500


@app.get("/setup/refresh-salesforce-tokens")
def setup_refresh_sf_tokens():
    """Show instructions for refreshing Salesforce access tokens (8h TTL)."""
    return render_template("refresh-sf-tokens.html")


@app.post("/api/setup/refresh-salesforce-tokens")
def api_refresh_salesforce_tokens():
    """Update SF tokens (access + optional refresh) and set refresh timestamp in .env.jira."""
    try:
        body = request.get_json(silent=True) or {}
        prod_token = body.get("sf_prod_access_token")
        sandbox_token = body.get("sf_sandbox_access_token")
        prod_refresh_token = _extract_salesforce_refresh_token(body.get("sf_prod_refresh_token"))
        sandbox_refresh_token = _extract_salesforce_refresh_token(body.get("sf_sandbox_refresh_token"))

        if not any([prod_token, sandbox_token]):
            return jsonify({"error": "Missing sf_prod_access_token or sf_sandbox_access_token"}), 400

        env_file = os.environ.get("CASEOPS_JIRA_ENV_FILE") or app.config.get("ENV_FILE_PATH")
        if not env_file:
            return jsonify({"error": "CASEOPS_JIRA_ENV_FILE not set"}), 500

        env_path = Path(env_file)
        env_content = env_path.read_text(encoding="utf-8")

        # Remove old token lines, keep everything else
        lines = env_content.split("\n")
        new_lines = [l for l in lines if not l.startswith((
            "SF_PROD_ACCESS_TOKEN=", "SF_SANDBOX_ACCESS_TOKEN=", "SF_TOKENS_REFRESHED_AT=",
            "SF_PROD_REFRESH_TOKEN=", "SF_SANDBOX_REFRESH_TOKEN="
        ))]

        # Add new tokens and timestamp
        if prod_token:
            new_lines.append(f"SF_PROD_ACCESS_TOKEN={prod_token}")
        if sandbox_token:
            new_lines.append(f"SF_SANDBOX_ACCESS_TOKEN={sandbox_token}")
        if prod_refresh_token:
            new_lines.append(f"SF_PROD_REFRESH_TOKEN={prod_refresh_token}")
        if sandbox_refresh_token:
            new_lines.append(f"SF_SANDBOX_REFRESH_TOKEN={sandbox_refresh_token}")
        new_lines.append(f"SF_TOKENS_REFRESHED_AT={int(time.time())}")

        env_path.write_text("\n".join(new_lines), encoding="utf-8")
        _load_jira_env(env_path)

        auto_refresh_enabled = bool(prod_refresh_token or sandbox_refresh_token)
        return jsonify({
            "ok": True,
            "message": "Salesforce tokens refreshed and timestamp set",
            "auto_refresh_enabled": auto_refresh_enabled,
            "refreshed_at": int(time.time())
        })
    except Exception as e:
        return jsonify({"error": f"Failed to update tokens: {str(e)}"}), 500


@app.post("/api/restart")
def api_restart():
    """Restart the CaseOps service. Writes restart flag and exits."""
    import os
    restart_flag = Path("/tmp/caseops-restart.flag")
    restart_flag.write_text(str(int(time.time())))

    # Exit the current process. The entrypoint loop will restart it.
    # Use os._exit() to bypass any cleanup that might hang
    os._exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="CaseOps: Salesforce support case automation"
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("CASEOPS_WORKSPACE", "default"),
        help="Workspace name (for multi-org isolation). Reads from .env.jira.{workspace}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CASEOPS_PORT", "5000")),
        help="Flask port",
    )
    parser.add_argument(
        "--outputs-dir",
        default=None,
        help="Override outputs directory (default: outputs or outputs/{workspace})",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to .env.jira file (default: .env.jira.{workspace} or .env.jira)",
    )
    _args = parser.parse_args()

    WORKSPACE = _args.workspace
    if _args.outputs_dir:
        OUTPUTS = Path(_args.outputs_dir)
    elif os.environ.get("CASEOPS_OUTPUTS_DIR"):
        OUTPUTS = Path(os.environ["CASEOPS_OUTPUTS_DIR"])
    else:
        OUTPUTS = ROOT / "outputs" / WORKSPACE if WORKSPACE != "default" else ROOT / "outputs"
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    # Initialize instance-specific runtime and metadata workspaces.
    globals()["TEMP_ROOT"] = OUTPUTS.parent / ".temp"
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    _ensure_metadata_workspace_dirs()

    # Initialize instance-specific pipeline logs directory
    globals()["OUTPUTS_PIPELINE_LOGS"] = OUTPUTS / "pipeline-logs"

    # Pre-create all pipeline output subdirectories so Claude Code doesn't need write permissions to create them
    for subdir in [
        "jira", "investigations", "internal-notes", "jira-messages", "test-reports",
        "engineering-escalations", "step-4-hypothesis", "pipeline-logs", "pipeline-state",
        "org-knowledge"
    ]:
        (OUTPUTS / subdir).mkdir(parents=True, exist_ok=True)
    _ensure_org_knowledge_defaults()

    if _args.env_file:
        env_file_path = Path(_args.env_file)
        _load_jira_env(env_file_path)
    else:
        env_file_path = ROOT / f".env.jira.{WORKSPACE}" if WORKSPACE != "default" else ROOT / ".env.jira"
        _load_jira_env(env_file_path)
    JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    app.config["WORKSPACE"] = WORKSPACE
    app.config["ENV_FILE_PATH"] = str(env_file_path)

    # ─── STARTUP VALIDATION ───────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"CaseOps Startup Validation")
    print(f"{'='*70}")
    print(f"Workspace: {WORKSPACE}")
    print(f"Outputs directory: {OUTPUTS}")
    print(f"Env file: {env_file_path}")
    print()

    # Validate OUTPUTS directory exists and is writable
    if not OUTPUTS.exists():
        raise RuntimeError(f"OUTPUTS directory does not exist: {OUTPUTS}")
    if not OUTPUTS.is_dir():
        raise RuntimeError(f"OUTPUTS is not a directory: {OUTPUTS}")

    try:
        test_file = OUTPUTS / ".startup-test"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink()
        print(f"[OK] OUTPUTS directory is writable")
    except Exception as e:
        raise RuntimeError(f"OUTPUTS directory is not writable: {OUTPUTS}\nError: {e}") from e

    # Validate .env.jira file exists and is readable
    if not env_file_path.exists():
        raise RuntimeError(f".env.jira file does not exist: {env_file_path}")
    if not env_file_path.is_file():
        raise RuntimeError(f".env.jira is not a file: {env_file_path}")

    try:
        env_file_path.read_text(encoding="utf-8")
        print(f"[OK] .env.jira file is readable")
    except Exception as e:
        raise RuntimeError(f".env.jira file is not readable: {env_file_path}\nError: {e}") from e

    # Validate all required subdirectories exist
    required_subdirs = [
        "jira", "investigations", "internal-notes", "jira-messages", "test-reports",
        "engineering-escalations", "step-4-hypothesis", "pipeline-logs", "pipeline-state",
        "closed-resolved", "org-knowledge"
    ]
    for subdir in required_subdirs:
        subdir_path = OUTPUTS / subdir
        if not subdir_path.exists():
            raise RuntimeError(f"Required subdirectory missing: {subdir_path}")
        if not subdir_path.is_dir():
            raise RuntimeError(f"Subdirectory is not a directory: {subdir_path}")
    print(f"[OK] All required subdirectories exist ({len(required_subdirs)} dirs)")

    # Validate app config is set
    if not app.config.get("WORKSPACE"):
        raise RuntimeError("WORKSPACE not set in app.config")
    if not app.config.get("ENV_FILE_PATH"):
        raise RuntimeError("ENV_FILE_PATH not set in app.config")
    print(f"[OK] App config set (WORKSPACE={app.config['WORKSPACE']})")

    # Verify CASEOPS environment variables will be available to subprocesses
    print(f"[OK] Subprocess environment variables to be set:")
    print(f"  - CASEOPS_OUTPUTS_DIR={OUTPUTS}")
    print(f"  - CASEOPS_JIRA_OUT_DIR={OUTPUTS / 'jira'}")
    print(f"  - CASEOPS_JIRA_ENV_FILE={env_file_path}")
    print(f"  - CASEOPS_WORKSPACE={WORKSPACE}")
    metadata_dirs = _metadata_workspace_dirs()
    print(f"  - CASEOPS_TEMP_DIR={TEMP_ROOT}")
    print(f"  - CASEOPS_METADATA_ROOT={metadata_dirs['root']}")
    print(f"  - CASEOPS_METADATA_RAW_PROD_DIR={metadata_dirs['raw_prod']}")
    print(f"  - CASEOPS_METADATA_SANDBOX_WORK_DIR={metadata_dirs['sandbox_work']}")
    print(f"  - CASEOPS_METADATA_CONFIRMED_DIR={metadata_dirs['confirmed']}")

    # Validate no hardcoded ROOT paths are being used for instance operations
    print(f"[OK] Instance routing validation:")
    print(f"  - ROOT/outputs isolation: OUTPUTS={OUTPUTS.relative_to(ROOT) if OUTPUTS.is_relative_to(ROOT) else OUTPUTS}")
    print(f"  - Jira directory: {(OUTPUTS / 'jira').relative_to(ROOT) if (OUTPUTS / 'jira').is_relative_to(ROOT) else OUTPUTS / 'jira'}")
    print(f"  - Pipeline logs: {(OUTPUTS / 'pipeline-logs').relative_to(ROOT) if (OUTPUTS / 'pipeline-logs').is_relative_to(ROOT) else OUTPUTS / 'pipeline-logs'}")

    print(f"\n{'='*70}")
    print(f"[OK] Startup validation PASSED - instance isolation ready")
    print(f"{'='*70}\n")

    # Initialize skill registry (loads all skills once at startup)
    # Load order: .claude first (stubs), then skills/ (full versions with guides, wins on duplicate names)
    print(f"Initializing skill registry...")
    skill_registry.load_all_skills(
        ROOT / ".claude" / "skills",
        ROOT / "skills"
    )
    print(f"[OK] Skill registry loaded: {skill_registry.skill_count()} skills")
    print(f"     Skills: {', '.join(skill_registry.list_skills())}\n")

    # Register skill paths (pass to subprocesses via env vars)
    print(f"Registering skill paths for subprocess environment...")
    for skill_dir in [ROOT / "skills", ROOT / ".claude" / "skills"]:
        if not skill_dir.exists():
            continue
        for skill_path in skill_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                skill_name = skill_path.name
                SKILL_PATHS[skill_name] = str(skill_path.resolve())
    print(f"[OK] {len(SKILL_PATHS)} skill paths registered\n")

    # Claude Code auth for non-interactive runs. Single source of truth is
    # CLAUDE_CODE_OAUTH_TOKEN generated by `claude setup-token`.
    claude_oauth_token = (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()
    if claude_oauth_token:
        print("[OK] Claude Code OAuth token configured")
    else:
        print("[WARN] Claude Code OAuth token not configured - use /setup/claude-login")

    # Check Salesforce tokens and auto-refresh if needed (8h TTL, auto-refresh at 4h)
    _check_and_refresh_salesforce_tokens(env_file_path)

    print(f"[OK] Temp directory: {TEMP_ROOT}")
    print(f"[OK] Metadata workspace: {_metadata_workspace_dirs()['root']}")

    # use_reloader=False prevents the dev reloader from killing SSE streams
    app.run(debug=True, threaded=True, host="0.0.0.0", port=_args.port, use_reloader=False)
