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
import html
import json
import hashlib
import mimetypes
import os
import queue
import re
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from collections import Counter
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from caseops_paths import default_jira_dir
from issue_clusters import (
    build_delta_validation_plan,
    read_issue_cluster_context,
    rebuild_issue_clusters,
    write_cluster_safety_validation,
    write_delta_validation_plan,
    write_similarity_adjudication,
    write_similarity_correction,
)
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


PIPELINE_STATE_SCHEMA_VERSION = 2
PIPELINE_LOOP_LIMITS = {"metadata_rounds": 3, "deploy_rounds": 3}
PIPELINE_TOOL_PERMISSION_VERSION = 1
CASEOPS_VERSION = (os.environ.get("CASEOPS_VERSION") or "dev").strip() or "dev"
STEP_LOOP_MARKER_REASONS = {
    "metadata": "repeat_metadata",
    "deploy": "deploy_fail",
    "candidate": "no_candidate_delta",
    "stoppoint": "safe_stoppoint_hit",
}
PIPELINE_STEP_TOOL_ALLOWLIST = {
    3: {
        "role": "issue-diagnosis",
        "tools": [
            "agent",
            "workflow",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "jira-issue-analysis",
            "bash",
            "powershell",
            "shell",
        ],
    },
    4: {
        "role": "hypothesis-synthesis",
        "tools": [
            "agent",
            "workflow",
            "read",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
        ],
    },
    5: {
        "role": "metadata-investigation",
        "tools": [
            "agent",
            "salesforce-production-metadata-investigation",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
            "sf",
        ],
    },
    6: {
        "role": "problem-drilling",
        "tools": [
            "agent",
            "salesforce-production-metadata-investigation",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
            "sf",
        ],
    },
    7: {
        "role": "routing-assessment",
        "tools": [
            "agent",
            "workflow",
            "read",
            "glob",
            "grep",
        ],
    },
    8: {
        "role": "candidate-implementation",
        "tools": [
            "agent",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
            "sf",
        ],
    },
    9: {
        "role": "sandbox-deploy-tester",
        "tools": [
            "agent",
            "salesforce-sandbox-deploy-test",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
            "sf",
        ],
    },
    10: {
        "role": "final-message-composer",
        "tools": [
            "agent",
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
        ],
    },
    11: {
        "role": "summary-author",
        "tools": [
            "read",
            "write",
            "edit",
            "glob",
            "grep",
            "bash",
            "powershell",
            "shell",
        ],
    },
}
PIPELINE_INTERNAL_UNAVAILABLE_TOOLS = {
    "toolsearch",
    "tool-search",
    "tool-search-tool",
}
PIPELINE_TRANSITION_CONTRACTS = {
    "step4_to_step5": {
        "transition_from": 4,
        "transition_to": 5,
        "restart_step": 4,
        "required_fields": (
            "hypothesis_h2",
            "problem_focus",
        ),
    },
    "step5_to_step6": {
        "transition_from": 6,
        "transition_to": 6,
        "restart_step": 6,
        "required_fields": (
            "problem_location",
            "failure_point",
            "artifact_reference",
        ),
    },
    "step8_to_step9": {
        "transition_from": 8,
        "transition_to": 9,
        "restart_step": 8,
        "required_fields": (
            "candidate_manifest",
            "candidate_scope",
        ),
    },
    "step9_to_step10": {
        "transition_from": 9,
        "transition_to": 10,
        "restart_step": 10,
        "required_fields": (
            "messages_separated",
            "internal_notes_audience",
            "customer_message_audience",
        ),
    },
}
PIPELINE_CONTEXT_LIMITS = {
    "org_knowledge_total_chars": 12_000,
    "org_knowledge_max_file_chars": 1_200,
    "org_knowledge_summary_chars": 900,
    "artifact_summary_chars": 800,
    "max_context_files": 8,
    "context_packet_summary_chars": 2_000,
    "long_run_seconds": 1_800,
    "step_long_seconds": 900,
    "repeated_output_lines": 3_000,
    "output_chars_per_run": 40_000,
}
PIPELINE_CONTEXT_POLICY_VERSION = 1


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


def _safe_runtime_home() -> Path:
    """Return a stable, container-safe HOME path for CLI subprocesses."""
    candidates = [
        os.environ.get("HOME"),
        os.environ.get("CASEOPS_HOME"),
        "/home/caseops",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate).expanduser()
        posix_path = candidate_path.as_posix()
        if not candidate_path.is_absolute():
            continue
        if posix_path in {"//", "/"}:
            continue
        # Skip accidental Windows-style HOME values that appear in Synology/NAS env.
        if ":" in posix_path and not posix_path.startswith("/"):
            continue
        return candidate_path

    # Last-resort writable fallback for container runtime.
    fallback = Path("/tmp/caseops-home")
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path("/tmp")
    return fallback


_RUNTIME_HOME = _safe_runtime_home()
if os.environ.get("HOME") != _RUNTIME_HOME.as_posix():
    os.environ["HOME"] = _RUNTIME_HOME.as_posix()

    # Set in `.env`: how CaseOps passes auth to the `claude` subprocess (see caseops_llm_auth_uses_anthropic_api_key).
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
# Stores: {"production-read": {...}, "sandbox-target": {...}}
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
    "CASEOPS_GLOBAL_MAX_PARALLEL",
    "CASEOPS_GLOBAL_MAX_QUEUE_PASSES",
    "CASEOPS_ENABLE_PARALLEL_PRECHECKS",
    "CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES",
    "CASEOPS_CLAUDE_IDLE_TIMEOUT_SECONDS",
    "CASEOPS_CLAUDE_TOTAL_TIMEOUT_SECONDS",
    "CASEOPS_SIMILAR_ISSUES_ENABLED",
    "CASEOPS_SIMILAR_ISSUES_INCLUDE_CLOSED",
    "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY",
    "CASEOPS_SIMILAR_ISSUES_AUTO_CLUSTER",
    "CASEOPS_SIMILAR_ISSUES_PUBLIC_SAFE_SUMMARIES",
    "CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT",
    "CASEOPS_SIMILAR_ISSUES_MODEL_ADJUDICATION",
    "CASEOPS_SIMILAR_ISSUES_DELTA_MODE",
    "CASEOPS_SIMILAR_ISSUES_CANDIDATE_LIMIT",
    "CASEOPS_SIMILAR_ISSUES_LOOKBACK_DAYS",
    "CASEOPS_SIMILAR_ISSUES_CURRENT_USER",
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
                "salesforce-gotchas/fields-and-picklists.md",
                "query-patterns/custom-field.md",
                "query-patterns/picklist-values.md",
                "deploy-patterns/custom-field-mdapi.md",
            ],
        },
        {
            "id": "layouts",
            "title": "Layouts and field placement",
            "keywords": ["layout", "page layout", "section", "field placement", "lightning page"],
            "files": [
                "helper-scripts.md",
                "salesforce-gotchas/layouts-and-record-types.md",
                "query-patterns/layouts.md",
            ],
        },
        {
            "id": "permission-sets",
            "title": "Permission sets and FLS",
            "keywords": [
                "permission set", "permissionset", "fls", "fieldpermissions", "field permission",
                "read edit", "read/write", "access", "profile", "sharing", "share object",
                "usershare", "accountshare", "opportunityshare", "rowcause", "userorgroupid"
            ],
            "files": [
                "helper-scripts.md",
                "salesforce-gotchas/access-and-visibility.md",
                "query-patterns/share-objects.md",
                "query-patterns/permission-sets.md",
            ],
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
                "salesforce-gotchas/deploy-and-sandbox.md",
                "deploy-patterns/custom-field-mdapi.md",
                "deploy-patterns/source-tracking.md",
            ],
        },
        {
            "id": "flows",
            "title": "Flow investigation",
            "keywords": ["flow", "flowdefinition", "flow version", "triggered flow", "record-triggered"],
            "files": ["salesforce-gotchas/automation-order.md", "query-patterns/flows.md"],
        },
        {
            "id": "apex",
            "title": "Apex investigation",
            "keywords": ["apex", "class", "trigger", "test class", "debug log"],
            "files": ["salesforce-gotchas/automation-order.md", "query-patterns/apex.md"],
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
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject OpportunityShare --contains "AccessLevel" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py deploy-mdapi --sandbox-org "$SANDBOX_ORG" --candidate "$CANDIDATE" --attempt "$ATTEMPT"
```

Rules:

- Run helpers first for custom field, picklist, layout, FLS, and custom-field MDAPI deploy work.
- Before querying setup/share objects with unfamiliar fields, run `sobject-fields` and use only fields returned by describe.
- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands.
- Do not use `package.xml` or `--manifest` for routine CaseOps retrieve/deploy. Use `--metadata`, `--source-dir`, or `--metadata-dir`.
- Helpers write compact JSON summaries into the issue-scoped directory and avoid raw access-token output.
- If a helper fails, inspect the helper summary/error and replan. Do not try many ad hoc variants of the same query.
""",
    "salesforce-gotchas/fields-and-picklists.md": """# Salesforce Gotchas: Fields And Picklists

Use these checks before concluding a field or picklist is missing or wrong.

- Custom field API names use `Object.Field__c`, but Tooling `CustomField.DeveloperName` usually omits `__c`.
- Picklist labels and API values can differ. Compare both label and value, and normalize trailing spaces and non-breaking spaces before reporting mismatch.
- A value can exist in metadata but be inactive, unavailable for a record type, hidden by field-level security, or absent from a dependent picklist controlling matrix.
- Record type picklist availability can make a field look wrong even when the field's global value set or valueSet is correct.
- Dependent picklists require checking controlling field values, not just the dependent field's value list.
- Custom field visibility can be blocked by FLS even when the field exists and is on the page layout.
- Formula fields, rollups, and calculated fields may show stale-looking values if dependent records or async recalculation have not completed.
- Standard fields often cannot be changed the same way custom fields can. Verify metadata type and mutability before proposing a deploy.
- Before creating a new field, query Production for existing API name, label, and semantically similar fields. Extend existing metadata when possible.
- For CaseOps, retrieve/deploy with modern `sf` CLI only. Prefer `--metadata`, `--source-dir`, or helper summaries; do not use `package.xml` or legacy `sfdx force:*`.
""",
    "salesforce-gotchas/layouts-and-record-types.md": """# Salesforce Gotchas: Layouts And Record Types

Use these checks before concluding a page layout or field placement is wrong.

- A field being present on one layout does not mean it appears for every profile, app, record type, or Lightning page.
- Page layout assignment depends on profile and record type. Lightning App Builder visibility rules can further hide or show components.
- A Lightning record page can display Dynamic Forms fields that are not visible in the classic page layout metadata shape.
- A section label can be confused with a nearby field label. Confirm the field's actual `layoutSections[].layoutColumns[].layoutItems[].field` placement.
- Record type picklist settings can make values unavailable even when the field and layout are correct.
- Compact layouts, highlights panels, related lists, and Lightning components are separate surfaces. Do not treat one as evidence for the others.
- Field-level security overrides layout visibility. If a user cannot see a field, check FLS and page layout/Lightning visibility.
- Profiles are not valid Support-owned targets for CaseOps edits. Prefer permission sets or document admin steps.
- For visual-only uncertainty, browser/frontdoor inspection is allowed, but API/SOQL/retrieve/deploy work must use `sf` CLI.
""",
    "salesforce-gotchas/access-and-visibility.md": """# Salesforce Gotchas: Access And Visibility

Use these checks before concluding an access issue is fixed or escalated.

- Object CRUD, field-level security, record sharing, app visibility, tab visibility, page layout, and Lightning component visibility are separate gates.
- Permission sets and permission set groups can combine access. Missing access may be caused by absent assignment, muted permission, or group-level behavior.
- FieldPermissions rows can include profile-owned permission sets. CaseOps should not modify Profile metadata; use permission sets or document admin steps.
- Permission Set Groups can mute permissions. Granting access in an underlying permission set may not be enough if the group mutes it.
- A user can have object access but still fail record access because sharing, ownership, role hierarchy, criteria sharing, teams, territories, or restriction rules block the record.
- Share objects do not all expose the same fields. Do not assume `Name`, `Description`, or `SharingType` exist on `UserShare`, `AccountShare`, `OpportunityShare`, or `Object__Share`; use `sf sobject describe` or query only documented fields such as `Id`, `UserOrGroupId`, `<Object>AccessLevel`, `RowCause`, and parent relationship fields valid for that share object.
- For share-object investigation, run the `query-patterns/share-objects.md` describe pattern first. Never query `UserShare.Name`; `UserShare` is not a user record and does not expose that field.
- A field can be editable in metadata but effectively read-only because the page uses a formula, validation rule, automation overwrite, approval lock, or record type process.
- Login as / UI inspection can prove visibility symptoms, but `sf data query`, `sf org`, and metadata retrieve are the source for API-level investigation.
- Always map the affected user/persona to exact PermissionSetAssignment, PermissionSetGroup, Profile, UserRole, and record ownership facts before proposing access changes.
""",
    "salesforce-gotchas/deploy-and-sandbox.md": """# Salesforce Gotchas: Deploy And Sandbox

Use these checks before trying repeated deploy variants.

- CaseOps deploys only to the allowlisted Sandbox from `CASEOPS_SANDBOX_TARGET_ORG`; Production is read-only.
- Use modern `sf project deploy start --source-dir` or `--metadata-dir`. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps work.
- Sandbox source tracking can produce `NothingToDeploy` even when candidate metadata exists. Prefer deterministic metadata-dir deploy via the CaseOps helper before inspecting `.sf` internals.
- Always retrieve a Sandbox baseline for every component before deploying a candidate. The baseline is the rollback anchor.
- Failed or abandoned attempts must be reverted before a new attempt starts. Verify revert by retrieve/diff, not by assumption.
- Some metadata deploys merge partial XML, while others replace larger structures. Confirm metadata type behavior before deploying partial files.
- Permission set field permissions can be deployed as narrow partial entries. Profile metadata must not be modified by the Support-owned pipeline.
- Record type, picklist, layout, and FLS changes often need to be tested together because each can block the same user-visible outcome.
- A successful deploy is not proof of a fixed issue. Validate the Jira acceptance criteria and record actual evidence.
""",
    "salesforce-gotchas/automation-order.md": """# Salesforce Gotchas: Automation Order

Use these checks before blaming the first automation artifact found.

- Salesforce save behavior can involve validation rules, before-save flows, Apex before triggers, duplicate rules, assignment rules, after-save flows, Apex after triggers, workflow/process leftovers, rollups, sharing recalculation, and async jobs.
- A field value can be set correctly, then overwritten later by automation. Compare before/after behavior and inspect downstream flows/triggers before declaring root cause.
- Record-triggered flows can have multiple entry conditions, order values, and active versions. Verify `FlowDefinition.ActiveVersionId` and the active version metadata.
- Flow labels and API names can differ. Use Tooling queries to resolve active versions before retrieving or referencing a flow.
- Apex triggers may delegate to handler classes. Query triggers first, then inspect only implicated classes instead of reading all Apex.
- Validation rules can block automation updates even when UI updates work, or vice versa, depending on user context and bypass logic.
- Assignment rules, auto-response rules, escalation rules, and email alerts can change Case behavior without changing the record fields the customer mentions.
- Scheduled paths, queueable Apex, platform events, and integrations can make failures appear delayed. Check timing evidence before narrowing scope.
- If the fix requires Apex, flow modification, validation rule change, approval process change, or business-critical automation ownership, route to Engineering with evidence and a Sandbox-validated proposal when possible.
""",
    "run-rules.md": """# CaseOps Org Knowledge Run Rules

These rules are always safe to include in Salesforce pipeline runs.

- Read this file plus only the topic files selected by `index.json`; do not bulk-read the entire org-knowledge directory.
- Use org knowledge to avoid relearning Salesforce CLI behavior. Prefer the known pattern first, then investigate only if the known pattern fails.
- Use `python scripts/sf_caseops_helper.py ...` helpers first for known Salesforce mechanics before writing ad hoc SOQL/curl/Python snippets.
- Use `sf` CLI and SOQL for Salesforce API work. Do not use frontdoor links, magic links, or browser session IDs for API, SOQL, retrieve, deploy, or tests.
- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands. Do not use `package.xml` or `--manifest` unless the operator explicitly approves a metadata-type exception.
- Never print, export, or embed raw Salesforce access tokens. Do not run `SF_TEMP_SHOW_SECRETS=true sf org display`. If a REST call is unavoidable, use an internal helper that does not log the token.
- Stay inside the current issue workspace. Do not inspect other issue metadata or output directories unless the operator explicitly asks for cross-issue comparison.
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
    "query-patterns/share-objects.md": """# Share Object Query Pattern

Use this pattern before querying `UserShare`, `AccountShare`, `OpportunityShare`, or custom `Object__Share` rows.

## Describe first

Share-object fields vary by object. Do not assume fields such as `Name`, `Description`, or `SharingType`.

```bash
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject OpportunityShare --contains "AccessLevel" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject UserShare --out-dir "$RAW_DIR"
```

Use only fields returned in the helper output or by `sf sobject describe`.

## Safe common patterns

Opportunity share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserOrGroupId, UserOrGroup.Name, OpportunityId, OpportunityAccessLevel, RowCause FROM OpportunityShare WHERE UserOrGroup.Name = 'Tier 1 Tech Support' LIMIT 20"
```

Account share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserOrGroupId, UserOrGroup.Name, AccountId, AccountAccessLevel, RowCause FROM AccountShare WHERE UserOrGroup.Name = 'Tier 1 Tech Support' LIMIT 20"
```

User share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserId, UserOrGroupId, RowCause, UserAccessLevel FROM UserShare WHERE UserId = '005...' LIMIT 20"
```

Rules:

- `UserShare` does not have a `Name` field. Query `User` separately for the user's name, or use a relationship field only if describe confirms it.
- For standard object share rows, the object-specific access field is usually `<Object>AccessLevel`, such as `OpportunityAccessLevel` or `AccountAccessLevel`.
- `UserOrGroup.Name` is useful for groups/users when the relationship is present, but it is not the same as a top-level `Name` field on the share row.
- If a share query fails once with `No such column`, stop and describe the sObject before trying another variant.
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
        'python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject OpportunityShare --contains "AccessLevel" --out-dir "$RAW_DIR"',
        "- Before querying setup/share objects with unfamiliar fields, run `sobject-fields` and use only fields returned by describe.",
        "- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands.",
        "- Do not use `package.xml` or `--manifest` for routine CaseOps retrieve/deploy. Use `--metadata`, `--source-dir`, or `--metadata-dir`.",
    ],
    "salesforce-gotchas/access-and-visibility.md": [
        "- Share objects do not all expose the same fields. Do not assume `Name`, `Description`, or `SharingType` exist on `UserShare`, `AccountShare`, `OpportunityShare`, or `Object__Share`; use `sf sobject describe` or query only documented fields such as `Id`, `UserOrGroupId`, `<Object>AccessLevel`, `RowCause`, and parent relationship fields valid for that share object.",
        "- For share-object investigation, run the `query-patterns/share-objects.md` describe pattern first. Never query `UserShare.Name`; `UserShare` is not a user record and does not expose that field.",
    ],
    "deploy-patterns/custom-field-mdapi.md": [
        "2. Do not create or use `package.xml` for routine CaseOps deploys. Prefer explicit `--source-dir`, `--metadata`, or `--metadata-dir`.",
    ],
}


def _safe_path_component(value: str, default: str) -> str:
    """Return a conservative path component for metadata cache/workspace paths."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned or default


def _metadata_workspace_dirs() -> dict[str, Path]:
    """Return persistent Salesforce metadata cache/workspace directories.

    Env var names stay stable for skills, but the backing paths now live under
    OUTPUTS so rollback evidence and confirmed packages survive as appdata.
    """
    prod_org = _safe_path_component(
        os.environ.get("CASEOPS_PRODUCTION_READ_ORG") or "production",
        "production",
    )
    api_version_raw = (
        os.environ.get("CASEOPS_SALESFORCE_API_VERSION")
        or os.environ.get("SF_API_VERSION")
        or "v66.0"
    )
    api_version = _safe_path_component(
        api_version_raw if str(api_version_raw).startswith("v") else f"v{api_version_raw}",
        "v66.0",
    )
    cache_root = OUTPUTS / "metadata-cache"
    workspace_root = OUTPUTS / "metadata-workspaces"
    raw_prod = cache_root / "production" / prod_org / api_version / "raw"
    return {
        "root": workspace_root,
        "cache_root": cache_root,
        "raw_prod": raw_prod,
        "raw_prod_summaries": cache_root / "production" / prod_org / api_version / "summaries",
        "sandbox_work": workspace_root,
        "confirmed": workspace_root,
    }


def _ensure_metadata_workspace_dirs() -> None:
    """Create the shared directory contract used by Salesforce pipeline agents."""
    for path in _metadata_workspace_dirs().values():
        path.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_metadata_workspace()


def _legacy_metadata_workspace_dirs() -> dict[str, Path]:
    """Return the old `.temp/metadata` workspace directories for migration only."""
    base_temp = TEMP_ROOT if TEMP_ROOT is not None else OUTPUTS.parent / ".temp"
    root = base_temp / "metadata"
    return {
        "root": root,
        "raw_prod": root / "raw-production",
        "sandbox_work": root / "sandbox-work",
        "confirmed": root / "confirmed",
    }


def _copy_tree_missing(src: Path, dst: Path) -> int:
    """Copy files from src to dst without overwriting existing files."""
    copied = 0
    if not src.is_dir():
        return copied
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return copied


def _migrate_legacy_metadata_workspace() -> None:
    """Copy old `.temp/metadata` evidence into the persistent outputs layout.

    The old tree is left untouched. This is deliberately non-destructive and
    missing-file only so reruns cannot overwrite newer workspace artifacts.
    """
    legacy = _legacy_metadata_workspace_dirs()
    current = _metadata_workspace_dirs()
    legacy_root = legacy["root"]
    if not legacy_root.is_dir():
        return
    marker = current["root"] / ".legacy-migration.json"
    copied: dict[str, int] = {}

    copied["raw-production"] = _copy_tree_missing(legacy["raw_prod"], current["raw_prod"])
    copied["sandbox-work"] = _copy_tree_missing(legacy["sandbox_work"], current["sandbox_work"])

    confirmed_count = 0
    if legacy["confirmed"].is_dir():
        for issue_dir in legacy["confirmed"].iterdir():
            if issue_dir.is_dir():
                confirmed_count += _copy_tree_missing(
                    issue_dir,
                    current["confirmed"] / issue_dir.name / "confirmed",
                )
    copied["confirmed"] = confirmed_count

    if any(copied.values()) or not marker.exists():
        marker.write_text(
            json.dumps(
                {
                    "legacyRoot": str(legacy_root),
                    "persistentRoot": str(current["root"]),
                    "copied": copied,
                    "migratedAt": datetime.now(timezone.utc).isoformat(),
                    "note": "Legacy files were copied missing-file-only; legacy tree was not deleted.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


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
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"WARNING: unable to create org-knowledge directory {root}: {exc}", file=sys.stderr)
        return
    index_path = root / "index.json"
    if not index_path.exists():
        try:
            index_path.write_text(
                json.dumps(_ORG_KNOWLEDGE_DEFAULT_INDEX, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"WARNING: unable to seed org-knowledge index {index_path}: {exc}", file=sys.stderr)
    for rel, content in _ORG_KNOWLEDGE_DEFAULT_FILES.items():
        path = root / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"WARNING: unable to seed org-knowledge file {path}: {exc}", file=sys.stderr)
    for rel, lines in _ORG_KNOWLEDGE_REQUIRED_LINES.items():
        path = root / rel
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        missing = [line for line in lines if line not in existing]
        if missing:
            suffix = "\n" if existing and not existing.endswith("\n") else ""
            try:
                path.write_text(existing + suffix + "\n".join(missing) + "\n", encoding="utf-8")
            except OSError as exc:
                print(f"WARNING: unable to update org-knowledge file {path}: {exc}", file=sys.stderr)
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    merged, changed = _merge_org_knowledge_index(data if isinstance(data, dict) else {})
    if changed:
        try:
            index_path.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"WARNING: unable to update org-knowledge index {index_path}: {exc}", file=sys.stderr)


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


def _estimate_token_count(text: str) -> int:
    """Simple token estimate used for planning context budgets."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _compact_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."


def _find_manifest_row(key: str) -> dict[str, str]:
    for row in _read_manifest():
        if row.get("Key") == key:
            return row
    return {}


def _build_context_packet_for_issue(key: str) -> tuple[dict[str, Any], int]:
    """Build a compact context packet for planner/state and prompt injection."""
    row = _find_manifest_row(key)
    index = _read_org_knowledge_index()
    selected_paths = _select_org_knowledge_files(key, row or {})
    total_chars_budget = int(index.get("max_context_chars") or PIPELINE_CONTEXT_LIMITS["org_knowledge_total_chars"])
    if total_chars_budget <= 0:
        total_chars_budget = PIPELINE_CONTEXT_LIMITS["org_knowledge_total_chars"]
    per_file_chars = int(index.get("max_context_chars_per_file", PIPELINE_CONTEXT_LIMITS["org_knowledge_max_file_chars"]) or PIPELINE_CONTEXT_LIMITS["org_knowledge_max_file_chars"])
    if per_file_chars <= 0:
        per_file_chars = PIPELINE_CONTEXT_LIMITS["org_knowledge_max_file_chars"]

    selected_cap = max(1, int(index.get("max_topic_files") or PIPELINE_CONTEXT_LIMITS["max_context_files"]))
    org_entries: list[dict[str, Any]] = []
    used = 0
    remaining = total_chars_budget
    for path in selected_paths[:selected_cap]:
        rel = str(path.relative_to(_org_knowledge_dir()))
        signature = _file_signature(path)
        evidence_id = f"org-knowledge:{rel}:{signature[:8] if signature else '?'}"
        snippet = _compact_text(_read_small_text(path, per_file_chars), PIPELINE_CONTEXT_LIMITS["org_knowledge_summary_chars"])
        char_estimate = len(snippet)
        if remaining <= 0:
            break
        if char_estimate > remaining:
            snippet = snippet[:max(1, remaining - 3)].rstrip() + "..."
            char_estimate = len(snippet)
            remaining = 0
        else:
            remaining -= char_estimate
        org_entries.append({
            "path": rel,
            "evidence_id": evidence_id,
            "signature": signature,
            "signature_type": "sha256",
            "size": path.stat().st_size if path.exists() else 0,
            "snippet": snippet,
            "summary_chars": char_estimate,
        })
        used += char_estimate
        if used >= total_chars_budget:
            break

    artifact_fields = {
        "jira_summary": "jira_summary",
        "investigation": "investigation",
        "hypothesis": "hypothesis",
        "test_report": "test_report",
        "internal_notes": "internal_notes",
        "jira_message": "jira_message",
    }
    artifact_summaries: list[dict[str, Any]] = []
    for label, key_name in artifact_fields.items():
        rel = FILE_LOCATIONS[key_name].format(key=key)
        path = OUTPUTS / rel
        signature = _file_signature(path)
        snippet = _compact_text(
            _read_small_text(path, PIPELINE_CONTEXT_LIMITS["artifact_summary_chars"]),
            PIPELINE_CONTEXT_LIMITS["artifact_summary_chars"],
        )
        if not signature and not snippet:
            continue
        artifact_summaries.append({
            "name": label,
            "path": rel,
            "signature": signature,
            "signature_type": "sha256",
            "snippet": snippet,
            "signature_chars": len(snippet),
        })

    total_context_chars = used + sum(item.get("signature_chars", 0) for item in artifact_summaries)
    return {
        "version": PIPELINE_CONTEXT_POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_allowed_chars": total_chars_budget,
        "org_knowledge": {
            "selected_files": org_entries,
            "file_budget": {
                "total_chars": total_chars_budget,
                "per_file_chars": per_file_chars,
                "max_files": selected_cap,
            },
        },
        "artifacts": artifact_summaries,
        "estimated_tokens": _estimate_token_count(_compact_text(" ".join(item.get("snippet", "") for item in org_entries), PIPELINE_CONTEXT_LIMITS["context_packet_summary_chars"])),
        "artifact_count": len(artifact_summaries),
        "evidence_ids": [item.get("signature") for item in org_entries if item.get("signature")] + [item.get("signature") for item in artifact_summaries if item.get("signature")],
        "notes": "Compact summaries and evidence IDs only; raw evidence remains in output files.",
    }, total_context_chars


def _issue_org_knowledge_search_text(key: str, row: dict[str, str]) -> str:
    parts = [
        key,
        row.get("Summary", ""),
        row.get("Status", ""),
        _read_small_text(OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key), 12000),
        _read_small_text(OUTPUTS / FILE_LOCATIONS["hypothesis"].format(key=key), 8000),
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


def _legacy_canned_messages_candidates() -> list[Path]:
    """Return previous custom canned-message locations that should be migrated."""
    legacy_files: list[Path] = [OUTPUTS.parent / "canned-messages.json"]

    workspace = app.config.get("WORKSPACE") or os.environ.get("CASEOPS_WORKSPACE", "default")
    if workspace and workspace != "default":
        workspace_legacy = ROOT / workspace / "canned-messages.json"
        if workspace_legacy.exists():
            legacy_files.append(workspace_legacy)

    return [path for path in legacy_files if path.exists() and path.is_file()]


def _migrate_legacy_canned_messages_file(target: Path) -> bool:
    """Copy the first available legacy canned-messages file into the canonical path."""
    if target.exists():
        return True
    for legacy in _legacy_canned_messages_candidates():
        if not legacy.exists() or not legacy.is_file():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)
            return True
        except OSError:
            return False
    return False


def _legacy_canned_messages_file() -> Path | None:
    """Return the first legacy path if available (compatibility fallback)."""
    candidates = _legacy_canned_messages_candidates()
    return candidates[0] if candidates else None


def _active_canned_messages_file() -> tuple[Path, bool]:
    """Return the file to read and whether it is a custom/persistent override."""
    persistent = _persistent_canned_messages_file()
    if persistent.exists():
        return persistent, True

    legacy = _legacy_canned_messages_file()
    if legacy:
        if _migrate_legacy_canned_messages_file(persistent):
            return persistent, True
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


def _salesforce_json_payload(value: str | None) -> dict[str, Any]:
    raw = (value or "").strip()
    if not raw.startswith("{"):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _salesforce_json_result(value: str | None) -> dict[str, Any]:
    parsed = _salesforce_json_payload(value)
    if not parsed:
        return {}
    result = parsed.get("result")
    return result if isinstance(result, dict) else parsed


def _salesforce_json_result_string(value: str | None) -> str:
    parsed = _salesforce_json_payload(value)
    if not parsed:
        return ""
    result = parsed.get("result")
    return result.strip() if isinstance(result, str) else ""


def _normalize_salesforce_access_token(value: str | None) -> str:
    """Accept raw or `sf org auth show-access-token --json` output.

    `sf org login access-token` requires `<org id>!<access token>`. Some
    Salesforce CLI JSON outputs expose the access token without the org id, so
    combine both fields when needed.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("SF_ACCESS_TOKEN="):
        raw = raw.split("=", 1)[1].strip()

    result_string = _salesforce_json_result_string(raw)
    if result_string:
        return result_string

    payload = _salesforce_json_result(raw)
    if payload:
        token = str(
            payload.get("accessToken")
            or payload.get("access_token")
            or payload.get("token")
            or ""
        ).strip()
        org_id = str(
            payload.get("orgId")
            or payload.get("organizationId")
            or payload.get("org_id")
            or payload.get("id")
            or ""
        ).strip()
        if token and "!" not in token and org_id:
            return f"{org_id}!{token}"
        return token or raw
    return raw


def _extract_salesforce_sfdx_auth_url(value: str | None) -> str:
    """Accept a raw force:// URL or `sf org auth show-sfdx-auth-url --json` output."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("SF_SFDX_AUTH_URL="):
        raw = raw.split("=", 1)[1].strip()
    if raw.startswith("force://"):
        return raw

    result_string = _salesforce_json_result_string(raw)
    if result_string.startswith("force://"):
        return result_string

    payload = _salesforce_json_result(raw)
    if payload:
        auth_url = str(
            payload.get("sfdxAuthUrl")
            or payload.get("sfdxAuthURL")
            or payload.get("authUrl")
            or payload.get("sfdx_auth_url")
            or ""
        ).strip()
        return auth_url if auth_url.startswith("force://") else ""
    return ""


def _extract_salesforce_refresh_token(value: str | None) -> str:
    """Accept a raw refresh token, SFDX auth URL, or CLI JSON output."""
    raw = (value or "").strip()
    if not raw:
        return ""
    sfdx_auth_url = _extract_salesforce_sfdx_auth_url(raw)
    if sfdx_auth_url:
        raw = sfdx_auth_url
    else:
        result_string = _salesforce_json_result_string(raw)
        if result_string:
            raw = result_string
    payload = _salesforce_json_result(raw)
    if payload:
        raw = str(
            payload.get("sfdxAuthUrl")
            or payload.get("sfdxAuthURL")
            or payload.get("authUrl")
            or payload.get("refreshToken")
            or payload.get("refresh_token")
            or ""
        ).strip()
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
            print("[WARN] SF_TOKENS_REFRESHED_AT not in .env. Initializing...")
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
        # Update .env with new tokens and timestamp
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

    Prefixes key with current WORKSPACE so separate runs don't share cache entries.
    """
    workspace = os.environ.get("CASEOPS_WORKSPACE", "default")
    return f"{workspace}:{key}"


def _invalidate_jira_summary_cache(key: str) -> None:
    jira_summary_cache.pop(key, None)
    jira_summary_cache.pop(_instance_cache_key(key), None)


def _validate_instance_path(path: Path, operation: str = "write") -> None:
    """Hard rule: Prevent writes/operations to shared directories.

    CRITICAL for Docker data isolation. Raises RuntimeError if path violates
    configured data-directory rules.

    Allowed patterns:
    - OUTPUTS / ... (configured outputs directory)
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

    # For write operations, enforce path must be under OUTPUTS.
    if operation in ("write", "mkdir", "create"):
        outputs_resolved = OUTPUTS.resolve()
        try:
            path_resolved.relative_to(outputs_resolved)
            # Path IS under OUTPUTS, allowed
            return
        except ValueError:
            # Path is NOT under OUTPUTS.
            pass

        # Path not under OUTPUTS - this is risky for writes
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
    """Load the active .env file into os.environ.

    By default does not overwrite existing non-empty values.
    Exceptions:
    - Runtime settings and secrets listed in `_ENV_KEYS_RELOAD_FROM_FILE` are always
      set from the file when the line has a non-empty value. This lets the Settings
      and token-refresh pages update the running Flask process without a restart.
    - Any key: if currently unset or empty/whitespace, the file value is applied.
    """
    if env_file is None:
        env_file = ROOT / ".env"
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

_PREFLIGHT_ENV_LOCK = threading.Lock()


def _env_flag(key: str, default: bool = False) -> bool:
    """Parse common truthy env values to a boolean."""
    value = (os.environ.get(key) or "").strip().lower()
    if not value:
        return bool(default)
    return value in {"1", "true", "yes", "on", "enabled"}


def _env_int(key: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = (os.environ.get(key) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _env_flag_from_map(
    key: str,
    default: bool = False,
    settings: dict[str, str] | None = None,
) -> bool:
    raw = ""
    if settings is not None and key in settings:
        raw = (settings.get(key) or "").strip()
    if not raw:
        raw = (os.environ.get(key) or "").strip()
    if not raw:
        return bool(default)
    return raw.lower() in {"1", "true", "yes", "on", "enabled"}


def _env_int_from_map(
    key: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
    settings: dict[str, str] | None = None,
) -> int:
    raw = ""
    if settings is not None and key in settings:
        raw = (settings.get(key) or "").strip()
    if not raw:
        raw = (os.environ.get(key) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


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
    raise RuntimeError("No Jira auth found in .env")


def _mask_secret(value: str) -> str:
    """Mask secret by showing only last 4 chars: 'secret123' → '••••••••3'."""
    if not value or len(value) < 4:
        return ""
    return "••••••••" + value[-4:]


def _read_env_file(env_file: Path | None = None) -> dict[str, str]:
    """Read .env and return dict of all keys/values (including empty lines, comments stripped)."""
    if env_file is None:
        env_file = ROOT / ".env"
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
    """Update .env with new values, preserving comments and structure.

    If a key already exists in the file, update its value. If not, append it.
    Then reload the environment.
    """
    if env_file is None:
        env_file = ROOT / ".env"

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
    """Remove keys from .env and the running process environment."""
    if env_file is None:
        env_file = ROOT / ".env"
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
    "hypothesis":         "hypothesis/{key}.md",
    "internal_notes":     "internal-notes/{key}.md",
    "jira_message":       "jira-messages/{key}.md",
    "test_report":        "test-reports/{key}.md",
    "eng_handoff":        "engineering-escalations/{key}.md",
    "closed_resolved":    "closed-resolved/{key}.md",
}

FILE_LABELS: dict[str, str] = {
    "jira_summary":    "Jira Summary",
    "investigation":   "Investigation",
    "hypothesis":      "Hypothesis",
    "internal_notes":  "Internal Notes",
    "jira_message":    "Jira Message",
    "test_report":     "Test Report",
    "eng_handoff":     "Eng Handoff",
    "closed_resolved": "Closed / Resolved / Canceled",
    "attachments":     "Attachments",
    "generated_files": "Generated Files",
}

# Daily summary directory structure:
# outputs/summaries/<YYYY-MM-DD>/issue-summary-<YYYY-MM-DD>.md
_SUMMARY_DIR = "summaries"

_DAILY_SUMMARY_FILENAME_RE = re.compile(r"^issue-summary-(\d{4}-\d{2}-\d{2})\.md$")


# Global actions (sync, triage, full) use this sentinel key.
_GLOBAL_KEY = "__global__"

# Set in __main__ after OUTPUTS is determined; declared here for type checking
OUTPUTS_PIPELINE_LOGS: Path = None  # type: ignore # Initialized in __main__ block
_PIPELINE_LOG_LOCK = threading.Lock()
_PIPELINE_LOG_TAIL_BYTES = 3 * 1024 * 1024
_PIPELINE_LOG_TAIL_LINES = 12_000
_PIPELINE_LOG_GOVERNANCE: dict[str, dict[str, Any]] = {}
_PIPELINE_LOG_GOVERNANCE_LOCK = threading.Lock()
_ANSI_CONTROL_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
)
_BROKEN_ANSI_CONTROL_RE = re.compile(r"\uFFFD\[[0-?]*[ -/]*[@-~]")
_SALESFORCE_ACCESS_TOKEN_RE = re.compile(r"\b00D[A-Za-z0-9]{12,18}![A-Za-z0-9._~=-]{20,}\b")
_SALESFORCE_FRONTDOOR_SID_RE = re.compile(r"(?i)([?&]sid=)[^\s&\"'<>]+")
_SFDX_AUTH_URL_RE = re.compile(r"force://[^\s\"'<>]+")


def _pipeline_log_path(run_key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", run_key) or "unknown"
    return OUTPUTS_PIPELINE_LOGS / f"{safe}.jsonl"


def _init_pipeline_log_governance(run_key: str) -> None:
    """Reset output-governance counters for a run key."""
    with _PIPELINE_LOG_GOVERNANCE_LOCK:
        _PIPELINE_LOG_GOVERNANCE[run_key] = {
            "non_critical_lines": 0,
            "non_critical_chars": 0,
            "critical_lines": 0,
            "line_duplicates": Counter(),
            "line_cap_logged": False,
            "char_cap_logged": False,
            "duplicate_logged": set(),
            "active": True,
        }


def _finalize_pipeline_log_governance(run_key: str) -> None:
    """Drop ephemeral output governance state for a completed run."""
    with _PIPELINE_LOG_GOVERNANCE_LOCK:
        _PIPELINE_LOG_GOVERNANCE.pop(run_key, None)


def _is_log_line_critical(text: str) -> bool:
    if _PIPELINE_STEP_MARKER_RE.search(text):
        return True
    if text.startswith("ERROR:") or text.startswith("WARNING:") or text.startswith("Run summary ["):
        return True
    if text.startswith("Done:") or text.startswith("Run started:"):
        return True
    if text.startswith("-- ") or "Token usage:" in text:
        return True
    return False


def _governed_log_line(run_key: str, text: str) -> str | None:
    """Apply context-governance caps and return the line to emit, or None to skip."""
    try:
        max_lines = int(PIPELINE_CONTEXT_LIMITS.get("repeated_output_lines", 0))
    except (TypeError, ValueError):
        max_lines = 3_000
    if max_lines <= 0:
        max_lines = 3_000
    try:
        max_chars = int(PIPELINE_CONTEXT_LIMITS.get("output_chars_per_run", 0))
    except (TypeError, ValueError):
        max_chars = 40_000
    if max_chars <= 0:
        max_chars = 40_000

    with _PIPELINE_LOG_GOVERNANCE_LOCK:
        state = _PIPELINE_LOG_GOVERNANCE.setdefault(
            run_key,
            {
                "non_critical_lines": 0,
                "non_critical_chars": 0,
                "critical_lines": 0,
                "line_duplicates": Counter(),
                "line_cap_logged": False,
                "char_cap_logged": False,
                "duplicate_logged": set(),
                "active": True,
            },
        )

        if not state.get("active", False):
            return text

        if not _is_log_line_critical(text):
            duplicate = int(state["line_duplicates"].get(text, 0)) + 1
            state["line_duplicates"][text] = duplicate
            if duplicate > max_lines:
                if text not in state["duplicate_logged"]:
                    state["duplicate_logged"].add(text)
                    return (
                        "Context governance: duplicate output suppressed for "
                        f"{text[:80]!r}; further repeats suppressed."
                    )
                return None

            if state["non_critical_lines"] >= max_lines:
                if not bool(state.get("line_cap_logged")):
                    state["line_cap_logged"] = True
                    return "Context governance: non-critical line cap reached; further non-critical lines suppressed."
                return None
            state["non_critical_lines"] += 1

            projected_chars = int(state["non_critical_chars"]) + len(text)
            if projected_chars > max_chars:
                if not bool(state.get("char_cap_logged")):
                    state["char_cap_logged"] = True
                    return "Context governance: run output cap reached; further non-critical lines suppressed."
                return None
            state["non_critical_chars"] = projected_chars
        else:
            state["critical_lines"] = int(state.get("critical_lines", 0)) + 1

        return text


def _ensure_directory_writable(path: Path, label: str) -> None:
    """Ensure a directory exists and is writable by the running process."""
    path.mkdir(parents=True, exist_ok=True)
    marker = path / ".caseops-write-check"
    try:
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return
    except OSError as exc:
        backup = path.with_name(f"{path.name}.readonly-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        print(f"[WARN] {label} is not writable: {path}\n       using backup recovery: {backup}")
        if backup.exists():
            try:
                shutil.rmtree(backup, ignore_errors=True)
            except OSError:
                pass
        if path.exists():
            try:
                shutil.move(str(path), str(backup))
                print(f"[OK] Moved unwritable {label} directory out of the way: {path} -> {backup}")
            except OSError as rm_exc:
                try:
                    shutil.rmtree(path, ignore_errors=True)
                    print(f"[WARN] Could not move unwritable {label}; removed it for recovery: {path}")
                except OSError as rm_second_exc:
                    raise RuntimeError(f"{label} path is not writable and could not be repaired: {path}\nError: {rm_second_exc}") from exc
        try:
            path.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok", encoding="utf-8")
            marker.unlink(missing_ok=True)
            print(f"[OK] Recreated {label} directory with current user write access: {path}")
        except OSError as rebuild_exc:
            raise RuntimeError(f"{label} directory is not writable and could not be recreated: {path}\nError: {rebuild_exc}") from exc


def _sanitize_pipeline_log_text(text: str) -> str:
    """Remove terminal redraw/color controls before logs are stored or shown."""
    cleaned = _ANSI_CONTROL_RE.sub("", str(text))
    cleaned = _BROKEN_ANSI_CONTROL_RE.sub("", cleaned)
    cleaned = _SALESFORCE_ACCESS_TOKEN_RE.sub("[REDACTED_SF_ACCESS_TOKEN]", cleaned)
    cleaned = _SALESFORCE_FRONTDOOR_SID_RE.sub(r"\1[REDACTED_SF_FRONTDOOR_SID]", cleaned)
    cleaned = _SFDX_AUTH_URL_RE.sub("[REDACTED_SFDX_AUTH_URL]", cleaned)
    cleaned = cleaned.replace("\r", "\n").replace("\b", "")
    return cleaned.rstrip()


def _ensure_file_writable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(f".{path.name}.unwritable-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if path.exists():
        try:
            path.rename(backup)
        except OSError as rename_exc:
            try:
                path.unlink()
            except OSError:
                raise RuntimeError(f"Pipeline log file is not writable and could not be recovered: {path}") from rename_exc
    try:
        path.touch(exist_ok=True)
        with path.open("a", encoding="utf-8"):
            pass
    except OSError as exc:
        raise RuntimeError(f"Pipeline log file is not writable and could not be recovered: {path}") from exc


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
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            # Recover from legacy run artifacts with immutable/ro bits or stale permissions.
            if log_path.is_file() and not os.access(log_path, os.W_OK):
                _ensure_file_writable(log_path)
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            else:
                raise RuntimeError(f"Unable to append pipeline log for run '{run_key}': {log_path}") from exc


def _format_run_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _log_emit_run_start(run_key: str, label: str | None = None) -> None:
    target = label or run_key
    _init_pipeline_log_governance(run_key)
    _log_emit_line(run_key, f"Run started: {target} at {_format_run_timestamp()}")


def _log_emit_line(run_key: str, text: str) -> None:
    """Notify SSE clients and append to per-key pipeline history on disk."""
    text = _sanitize_pipeline_log_text(text)
    governed = _governed_log_line(run_key, text)
    if governed is None:
        return
    text = governed
    _log_q.put(f"{run_key}|{text}")
    _persist_pipeline_record(run_key, text, kind="line")


def _log_emit_done(run_key: str) -> None:
    _log_q.put(f"__done__|{run_key}")
    _persist_pipeline_record(run_key, "", kind="done")
    _finalize_pipeline_log_governance(run_key)


def _path_relative_for_prompt(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text_for_resume(path: Path, max_chars: int = 80_000) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= max_chars else text[:max_chars]


_RECENT_EVIDENCE_RE = re.compile(
    r"(?is)"
    r"(?:root cause confirmed|confirmed root cause|classification complete|fix confirmed|"
    r"support-resolvable|no-deploy|no deploy|no apex changes needed|sandbox deploy skipped|"
    r"production deploy|engineering escalation|engineering-required|missing .*access|"
    r"missing .*permission|permission set|ready for production|artifacts written)"
)


def _recent_pipeline_evidence(key: str, max_lines: int = 10) -> list[str]:
    """Return compact decision evidence from recent runs for resume prompts."""
    try:
        log_path = _pipeline_log_path(key)
    except Exception:
        log_path = OUTPUTS / "pipeline-logs" / f"{re.sub(r'[^A-Za-z0-9._-]', '_', key) or 'unknown'}.jsonl"
    if not log_path.is_file():
        return []
    try:
        raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    evidence: list[str] = []
    seen: set[str] = set()
    for raw in raw_lines[-250:]:
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if rec.get("kind") == "done":
            continue
        text = _sanitize_pipeline_log_text(str(rec.get("text") or "")).strip()
        if not text or text.startswith("[Bash]") or text.startswith("[Read]") or text.startswith("[Edit]") or text.startswith("[Write]"):
            continue
        if not _RECENT_EVIDENCE_RE.search(text):
            continue
        compact = re.sub(r"\s+", " ", text)
        if len(compact) > 500:
            compact = compact[:497].rstrip() + "..."
        key_norm = compact.lower()
        if key_norm in seen:
            continue
        seen.add(key_norm)
        evidence.append(compact)

    return evidence[-max_lines:]


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


def _pipeline_state_path(key: str) -> Path:
    return OUTPUTS / "pipeline-state" / f"{key}.json"


def _pipeline_state_evidence_dir(key: str) -> Path:
    safe_key = re.sub(r"[^A-Za-z0-9._-]", "_", str(key) or "issue")
    return OUTPUTS / "pipeline-state" / f"{safe_key}.evidence"


def _read_pipeline_state(key: str) -> dict[str, Any]:
    """Load persisted state for a key, including legacy fallback."""
    path = _pipeline_state_path(key)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _sha256_signature(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _file_signature(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        return _sha256_signature(path.read_bytes())
    except OSError:
        return ""


def _dir_signature(path: Path | None) -> str:
    if not path or not path.is_dir():
        return ""
    h = hashlib.sha256()
    for child in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        try:
            h.update(child.relative_to(path).as_posix().encode("utf-8"))
            h.update(b"|")
            h.update(str(child.stat().st_size).encode("utf-8"))
            h.update(b"|")
            h.update(str(int(child.stat().st_mtime)).encode("utf-8"))
            h.update(b"|")
        except OSError:
            continue
    return _sha256_signature(h.digest())


def _build_jira_signature(key: str, source_mtime: float | None) -> str:
    parts = [
        _file_signature(OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key)),
        _file_signature(OUTPUTS / "jira" / "raw" / f"{key}.json"),
    ]
    if source_mtime:
        parts.append(f"source-mtime:{source_mtime}")
    return _sha256_signature("|".join(part for part in parts if part))


def _infer_routing_state(
    state: dict[str, Any],
    *,
    has_eng_handoff: bool = False,
    has_test_report: bool = False,
) -> dict[str, Any]:
    raw = state.get("routing") if isinstance(state.get("routing"), dict) else {}
    path = (str(raw.get("path") or "") or "").strip().lower()
    confidence = str(raw.get("confidence") or "low").strip().lower()
    if path not in {"support_resolvable", "engineering_required", "on_hold", "unknown"}:
        if has_eng_handoff and has_test_report:
            path = "engineering_required"
            confidence = "medium"
        elif has_eng_handoff:
            path = "engineering_required"
            confidence = "low"
        elif has_test_report:
            path = "support_resolvable"
            confidence = "low"
        else:
            path = "unknown"
    return {
        "path": path,
        "confidence": confidence if confidence in {"low", "medium", "high"} else "low",
        "reason": str(raw.get("reason") or "Routing not yet persisted.").strip(),
    }


def _infer_deliverable_state(
    state: dict[str, Any],
    *,
    is_data_only_legacy: bool = False,
) -> dict[str, Any]:
    raw = state.get("deliverable") if isinstance(state.get("deliverable"), dict) else {}
    deploy_required = (str(raw.get("production_deploy_required") or "").strip().lower() or "unknown")
    if deploy_required == "na":
        deploy_required = "n/a"
    if deploy_required not in {"yes", "no", "n/a", "unknown"}:
        deploy_required = "unknown"
    return {
        "type": str(raw.get("type") or "unknown").strip(),
        "production_deploy_required": deploy_required,
        "production_deploy_method": str(raw.get("production_deploy_method") or "").strip(),
        "no_deploy_reason": str(raw.get("no_deploy_reason") or "").strip(),
        "legacy_detected": bool(is_data_only_legacy),
    }


def _deliverable_is_data_only(deliverable: dict[str, Any], *, legacy_detected: bool = False) -> bool:
    """Return true when durable state or legacy artifacts identify a no-deploy data/admin fix."""
    deploy_required = str(deliverable.get("production_deploy_required") or "unknown").strip().lower()
    if deploy_required in {"no", "n/a"}:
        return True
    if deploy_required == "yes":
        return False
    return bool(legacy_detected)


def _normalize_tool_name(tool_name: str) -> str:
    """Normalize a tool name for policy checks."""
    return (tool_name or "").strip().lower().replace("_", "-")


def _is_pipeline_internal_unavailable_tool(tool_name: str) -> bool:
    return _normalize_tool_name(tool_name) in PIPELINE_INTERNAL_UNAVAILABLE_TOOLS


def _build_step_tool_permissions(next_step: int | None = None) -> dict[str, Any]:
    steps: dict[str, Any] = {}
    for step_no, policy in PIPELINE_STEP_TOOL_ALLOWLIST.items():
        steps[str(step_no)] = {
            "role": policy["role"],
            "allowlist": policy["tools"],
        }

    return {
        "version": PIPELINE_TOOL_PERMISSION_VERSION,
        "steps": steps,
        "active_step": next_step,
        "active_step_tools": steps.get(str(next_step or ""), {}).get("allowlist", []),
    }


def _contract_status_from_missing(missing: list[str]) -> str:
    if not missing:
        return "pass"
    return "needs_rework"


def _messages_are_separated(internal_notes: str, jira_message: str) -> bool:
    if not internal_notes or not jira_message:
        return False
    if internal_notes.strip() == jira_message.strip():
        return False
    return True


def _evaluate_transition_contract_step4_to_step5(hypothesis_text: str) -> dict[str, Any]:
    missing: list[str] = []
    evidence: dict[str, bool] = {}
    text = hypothesis_text or ""
    hypothesis_h2 = bool(re.search(r"(?im)^\s*#+\s*(root cause hypothesis|hypothesis)", text))
    evidence["hypothesis_h2"] = hypothesis_h2
    if not hypothesis_h2:
        if not re.search(r"(?is)\broot cause\b", text):
            missing.append("hypothesis_h2")
        else:
            evidence["hypothesis_h2"] = True

    problem_focus = bool(
        re.search(
            r"(?is)problem\s*(?:focus|location|scope|type)|root cause|problem statement|issue statement|specific artifact|target component",
            text,
        )
    )
    evidence["problem_focus"] = problem_focus
    if not problem_focus:
        if not re.search(r"(?is)\b(summary|analysis|findings|candidate|proposed|scope)\b", text):
            missing.append("problem_focus")
        else:
            evidence["problem_focus"] = True

    return {
        "status": _contract_status_from_missing(missing),
        "missing": missing,
        "observed": evidence,
        "reason": "Missing required Step 4 artifact fields." if missing else "Step 4 → Step 5 contract satisfied.",
        "required_fields": PIPELINE_TRANSITION_CONTRACTS["step4_to_step5"]["required_fields"],
        "evidence": {
            "hypothesis_chars": len(text),
        },
    }


def _evaluate_transition_contract_step5_to_step6(investigation_text: str) -> dict[str, Any]:
    missing: list[str] = []
    text = investigation_text or ""
    evidence = {
        "problem_location": bool(re.search(r"(?im)^\s*#{1,6}\s*problem\s+location", text)),
        "failure_point": bool(re.search(r"(?im)(failure\s+point|failure[:\-])", text)),
        "artifact_reference": bool(re.search(r"(?im)(specific\s+artifact|artifact\s+name|api\s+name|file\s+name)", text)),
        "investigation_chars": len(text),
    }
    if not evidence["problem_location"]:
        if not re.search(r"(?is)problem location|problem area|affected component", text):
            missing.append("problem_location")
        else:
            evidence["problem_location"] = True
    if not evidence["failure_point"]:
        if not re.search(r"(?is)problem\s*location|failure|failing|fails|breaks|error|blocked by|root cause|reproduc|symptom|not\s+working|unable to", text):
            missing.append("failure_point")
        else:
            evidence["failure_point"] = True
    if not evidence["artifact_reference"]:
        if not re.search(r"(?is)object|field|flow|class|trigger|permission|profile|layout|metadata|component|candidate|method|record|query|deployment", text):
            missing.append("artifact_reference")
        else:
            evidence["artifact_reference"] = True

    return {
        "status": _contract_status_from_missing(missing),
        "missing": missing,
        "observed": evidence,
        "reason": "Missing required Step 5→6 handoff fields." if missing else "Step 5 → Step 6 contract satisfied.",
        "required_fields": PIPELINE_TRANSITION_CONTRACTS["step5_to_step6"]["required_fields"],
    }


def _evaluate_transition_contract_step8_to_step9(metadata_manifest_text: str) -> dict[str, Any]:
    missing: list[str] = []
    evidence = {
        "candidate_manifest": bool(metadata_manifest_text),
        "candidate_scope": False,
        "attempt_id_present": False,
        "workspace_has_file": False,
        "manifest_chars": len(metadata_manifest_text or ""),
    }
    if not metadata_manifest_text:
        return {
            "status": "needs_rework",
            "missing": ["candidate_manifest"],
            "observed": evidence,
            "reason": "metadata-workspace.json is missing for Step 8 → Step 9 validation.",
            "required_fields": PIPELINE_TRANSITION_CONTRACTS["step8_to_step9"]["required_fields"],
        }

    evidence["workspace_has_file"] = True
    manifest_parsed: dict[str, Any] | None = None
    parsed = {}
    try:
        parsed = json.loads(metadata_manifest_text)
    except Exception:
        parsed = {}
    if isinstance(parsed, dict):
        manifest_parsed = parsed
    elif isinstance(parsed, list):
        manifest_parsed = {"components": parsed}

    if not manifest_parsed:
        evidence["candidate_scope"] = False
        missing.append("candidate_scope")
    else:
        candidates = []
        for key in ("files", "components", "candidate_components", "changed_components", "artifacts", "file_candidates"):
            value = manifest_parsed.get(key) if isinstance(manifest_parsed, dict) else None
            if isinstance(value, list) and value:
                candidates.extend(value)
        evidence["candidate_scope"] = bool(candidates)
        if not evidence["candidate_scope"]:
            if any(term in metadata_manifest_text.lower() for term in ("attempt", "attempts", "candidate", "component", "package")):
                evidence["candidate_scope"] = True
            else:
                missing.append("candidate_scope")

        attempt = manifest_parsed.get("attempt") if isinstance(manifest_parsed, dict) else None
        if attempt is None:
            attempt = manifest_parsed.get("attempt_number") if isinstance(manifest_parsed, dict) else None
        if attempt:
            try:
                evidence["attempt_id_present"] = int(str(attempt)) > 0
            except (TypeError, ValueError):
                evidence["attempt_id_present"] = bool(str(attempt).strip())
        elif re.search(r"(?im)\battempt\b", metadata_manifest_text):
            evidence["attempt_id_present"] = True
        else:
            evidence["attempt_id_present"] = True

        if not evidence["attempt_id_present"]:
            missing.append("attempt_id")

    return {
        "status": _contract_status_from_missing(missing),
        "missing": missing,
        "observed": evidence,
        "reason": "Missing required Step 8 → Step 9 candidate constraints." if missing else "Step 8 → Step 9 contract satisfied.",
        "required_fields": PIPELINE_TRANSITION_CONTRACTS["step8_to_step9"]["required_fields"],
    }


def _evaluate_transition_contract_step9_to_step10(
    internal_notes: str,
    jira_message: str,
    messages_separated: bool,
) -> dict[str, Any]:
    missing: list[str] = []
    evidence = {
        "messages_separated": bool(messages_separated),
        "internal_notes_audience": False,
        "customer_message_audience": True,
        "internal_chars": len(internal_notes or ""),
        "jira_chars": len(jira_message or ""),
    }
    if not internal_notes:
        missing.append("internal_notes")
    if not jira_message:
        missing.append("jira_message")

    if not internal_notes:
        evidence["internal_notes_audience"] = False
    else:
        evidence["internal_notes_audience"] = not bool(re.search(r"(?im)^agent|support\s*only|jira-only", internal_notes[:80]))

    if not jira_message:
        evidence["customer_message_audience"] = False
    else:
        evidence["customer_message_audience"] = not bool(re.search(r"(?im)internal only|for\s+engineer|engineering\s+details", jira_message[:120]))

    if not messages_separated:
        missing.append("messages_separated")
    if not evidence["internal_notes_audience"]:
        missing.append("internal_notes_audience")
    if not evidence["customer_message_audience"]:
        missing.append("customer_message_audience")
    return {
        "status": _contract_status_from_missing(missing),
        "missing": missing,
        "observed": evidence,
        "reason": "Missing required Step 9 → Step 10 file separation/audience checks." if missing else "Step 9 → Step 10 contract satisfied.",
        "required_fields": PIPELINE_TRANSITION_CONTRACTS["step9_to_step10"]["required_fields"],
    }


def _evaluate_transition_contracts(
    *,
    hypothesis: str,
    investigation: str,
    metadata_manifest_text: str,
    internal_notes: str,
    jira_message: str,
    messages_separated: bool,
) -> dict[str, Any]:
    contracts = {
        "step4_to_step5": _evaluate_transition_contract_step4_to_step5(hypothesis),
        "step5_to_step6": _evaluate_transition_contract_step5_to_step6(investigation),
        "step8_to_step9": _evaluate_transition_contract_step8_to_step9(metadata_manifest_text),
        "step9_to_step10": _evaluate_transition_contract_step9_to_step10(internal_notes, jira_message, messages_separated),
    }
    return contracts


def _apply_transition_contracts_to_plan(plan: dict[str, Any], contracts: dict[str, Any]) -> None:
    by_step = {str(step.get("step")): step for step in plan.get("steps", []) if isinstance(step, dict)}
    for key, contract in contracts.items():
        if not isinstance(contract, dict):
            continue
        status = str(contract.get("status") or "").strip()
        if status != "needs_rework":
            continue
        step_no = None
        if key == "step4_to_step5":
            step_no = 5
        elif key == "step5_to_step6":
            step_no = 6
        elif key == "step8_to_step9":
            step_no = 9
        elif key == "step9_to_step10":
            step_no = 10
        if step_no is None:
            continue
        step = by_step.get(str(step_no))
        if not step:
            continue
        if step.get("status") == "complete":
            step["status"] = "stale"
        elif step.get("status") not in {"blocked", "stale"}:
            step["status"] = "stale"
        step["reason"] = f"{step.get('reason', '').strip()} Contract failed ({key}): {contract.get('reason', 'inspect required fields')}"
        step["action"] = (
            f"Force corrective re-run of Step {step_no} to satisfy transition contract before Step {step_no + 1}."
        )


def _is_tool_allowlisted(step_no: int | None, tool_name: str) -> bool:
    allowlist = PIPELINE_STEP_TOOL_ALLOWLIST.get(step_no or 0, {})
    if not allowlist:
        return True
    normalized = _normalize_tool_name(tool_name)
    return not normalized or normalized in [_normalize_tool_name(item) for item in allowlist.get("tools", [])]


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    if num < 0:
        return default
    return num


def _load_loop_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("loop_state", {}) if isinstance(state.get("loop_state"), dict) else {}
    return {
        "metadata_rounds": _coerce_non_negative_int(raw.get("metadata_rounds"), 0),
        "deploy_rounds": _coerce_non_negative_int(raw.get("deploy_rounds"), 0),
        "no_candidate_delta_count": _coerce_non_negative_int(raw.get("no_candidate_delta_count"), 0),
        "last_stoppoint_code": str(raw.get("last_stoppoint_code") or "").strip().lower(),
        "last_reason": str(raw.get("last_reason") or "").strip(),
        "last_seen": str(raw.get("last_seen") or "").strip(),
        "latest_stop_code": str(raw.get("latest_stop_code") or "").strip(),
    }


def _default_loop_state() -> dict[str, Any]:
    return {
        "metadata_rounds": 0,
        "deploy_rounds": 0,
        "no_candidate_delta_count": 0,
        "last_stoppoint_code": "",
        "last_reason": "",
        "last_seen": "",
        "latest_stop_code": "",
    }


def _apply_signature_invalidation(
    prior_loop_state: dict[str, Any],
    *,
    jira_source_stable: bool,
    investigation_stable: bool,
    step4_stable: bool,
    metadata_stable: bool,
    test_report_stable: bool,
) -> dict[str, Any]:
    """Reset narrow loop counters when source and contract inputs change."""
    loop_state = dict(_default_loop_state(), **prior_loop_state)
    if not jira_source_stable:
        return _default_loop_state()
    if not investigation_stable or not step4_stable:
        loop_state["metadata_rounds"] = 0
        loop_state["deploy_rounds"] = 0
        loop_state["no_candidate_delta_count"] = 0
        return loop_state
    if not metadata_stable and test_report_stable:
        # Candidate workspace changed; allow another deploy/test pass.
        loop_state["deploy_rounds"] = 0
    return loop_state


def _loop_state_for_resume(
    prior_loop_state: dict[str, Any],
    *,
    has_schema: bool,
    has_stored_signatures: bool,
    jira_signature_stable: bool,
    inv_signature_stable: bool,
    step4_signature_stable: bool,
    metadata_signature_stable: bool,
    test_signature_stable: bool,
) -> dict[str, Any]:
    if not has_schema or not has_stored_signatures:
        return _default_loop_state()
    loop_state = _load_loop_state(prior_loop_state)
    return _apply_signature_invalidation(
        loop_state,
        jira_source_stable=jira_signature_stable,
        investigation_stable=inv_signature_stable,
        step4_stable=step4_signature_stable,
        metadata_stable=metadata_signature_stable,
        test_report_stable=test_signature_stable,
    )


def _loop_stop_reason(loop_state: dict[str, Any]) -> str:
    metadata_limit_hit = loop_state.get("metadata_rounds", 0) >= PIPELINE_LOOP_LIMITS["metadata_rounds"]
    deploy_limit_hit = loop_state.get("deploy_rounds", 0) >= PIPELINE_LOOP_LIMITS["deploy_rounds"]
    if metadata_limit_hit:
        return STEP_LOOP_MARKER_REASONS["metadata"]
    if deploy_limit_hit:
        return STEP_LOOP_MARKER_REASONS["deploy"]
    if loop_state.get("no_candidate_delta_count", 0) > 0:
        return STEP_LOOP_MARKER_REASONS["candidate"]
    if loop_state.get("latest_stop_code") in {"safe_stoppoint", "safe_stoppoint_hit"}:
        return STEP_LOOP_MARKER_REASONS["stoppoint"]
    return ""


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


def _normalized_signature(value: Any) -> str:
    if not value:
        return ""
    return str(value).strip()


def _signatures_match(current: str, prior: Any) -> bool:
    """Return True only when both signatures are non-empty and equal."""
    prior_sig = _normalized_signature(prior)
    return bool(current and prior_sig and current == prior_sig)


def _state_has_schema(state: dict[str, Any]) -> bool:
    try:
        version = int(_normalized_signature(state.get("schema_version")) or "0")
    except (TypeError, ValueError):
        return False
    return version == PIPELINE_STATE_SCHEMA_VERSION


def _resume_step(step: int, name: str, status: str, reason: str, action: str, artifacts: list[str] | None = None) -> dict[str, Any]:
    return {
        "step": step,
        "name": name,
        "status": status,
        "reason": reason,
        "action": action,
        "artifacts": artifacts or [],
    }


def _build_pipeline_resume_plan(
    key: str,
    status: str = "",
    jira_updated: str | None = None,
    *,
    force_active: bool = False,
    rebuild_from_artifacts: bool = False,
) -> dict[str, Any]:
    """Build a resume plan based on persisted state signatures and fallback signals."""
    source_mtime = _issue_source_mtime(key, jira_updated)
    paths = {
        "jira_summary": OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key),
        "investigation": OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key),
        "hypothesis": OUTPUTS / FILE_LOCATIONS["hypothesis"].format(key=key),
        "test_report": OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key),
        "internal_notes": OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key),
        "jira_message": OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key),
        "eng_handoff": OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key),
        "closed_resolved": OUTPUTS / FILE_LOCATIONS["closed_resolved"].format(key=key),
    }
    artifacts = {name: _artifact_snapshot(path, source_mtime) for name, path in paths.items()}

    investigation = _read_text_for_resume(paths["investigation"])
    hypothesis = _read_text_for_resume(paths["hypothesis"])
    test_report = _read_text_for_resume(paths["test_report"])
    internal_notes = _read_text_for_resume(paths["internal_notes"])
    jira_message = _read_text_for_resume(paths["jira_message"])
    eng_handoff = _read_text_for_resume(paths["eng_handoff"])
    recent_evidence = _recent_pipeline_evidence(key)
    diagnosis_text = "\n".join([investigation, hypothesis, internal_notes, eng_handoff])
    recent_evidence_text = "\n".join(recent_evidence)
    diagnosis_and_recent_text = "\n".join([diagnosis_text, recent_evidence_text])

    metadata_dirs = _metadata_workspace_dirs()
    raw_metadata_dir = metadata_dirs["raw_prod"] / key
    sandbox_work_dir = metadata_dirs["sandbox_work"] / key
    confirmed_dir = metadata_dirs["confirmed"] / key / "confirmed"
    metadata_manifest = sandbox_work_dir / "metadata-workspace.json"
    metadata = {
        "raw_production_dir": {"path": _path_relative_for_prompt(raw_metadata_dir), "has_files": _directory_has_files(raw_metadata_dir)},
        "sandbox_work_dir": {"path": _path_relative_for_prompt(sandbox_work_dir), "has_files": _directory_has_files(sandbox_work_dir)},
        "confirmed_dir": {"path": _path_relative_for_prompt(confirmed_dir), "has_files": _directory_has_files(confirmed_dir)},
        "workspace_manifest": _artifact_snapshot(metadata_manifest, None),
    }

    state = {} if rebuild_from_artifacts else _read_pipeline_state(key)
    has_schema = _state_has_schema(state)
    evidence_prechecks = state.get("evidence_prechecks") if isinstance(state.get("evidence_prechecks"), dict) else None
    stored_signatures = state.get("signatures", {}) if isinstance(state.get("signatures", {}), dict) else {}
    has_stored_signatures = has_schema and bool(stored_signatures)
    signatures = {
        "jira_source": _build_jira_signature(key, source_mtime),
        "investigation": _file_signature(paths["investigation"]),
        "hypothesis": _file_signature(paths["hypothesis"]),
        "test_report": _file_signature(paths["test_report"]),
        "metadata_workspace": _file_signature(metadata_manifest),
    }
    has_data_only_legacy = _test_report_is_data_only(key)
    routing = _infer_routing_state(
        state,
        has_eng_handoff=artifacts["eng_handoff"]["exists"] and artifacts["eng_handoff"]["size"] > 0,
        has_test_report=artifacts["test_report"]["exists"] and artifacts["test_report"]["size"] > 0,
    )
    deliverable = _infer_deliverable_state(state, is_data_only_legacy=has_data_only_legacy)
    has_no_deploy = _deliverable_is_data_only(deliverable, legacy_detected=has_data_only_legacy)

    def sig_complete(field: str) -> bool:
        return _signatures_match(signatures.get(field, ""), stored_signatures.get(field))

    # Signature drift for each step.
    jira_signature_stable = not has_schema or sig_complete("jira_source")
    inv_signature_stable = sig_complete("investigation")
    hypothesis_signature_stable = sig_complete("hypothesis")
    test_signature_stable = sig_complete("test_report")
    metadata_signature_stable = sig_complete("metadata_workspace")

    routing_on_hold = routing["path"] == "on_hold"

    candidate_exists = bool(
        metadata["sandbox_work_dir"]["has_files"]
        or metadata["confirmed_dir"]["has_files"]
        or re.search(r"(?is)proposed solution|candidate|changed files|components changed|deploy|permission set assignment|assigning .*permission set|no-deploy", "\n".join([investigation, test_report, recent_evidence_text]))
    )

    # Problem / gate signals.
    problem_location = bool(
        artifacts["investigation"]["exists"]
        and re.search(r"(?is)problem location|specific artifact|failure point|confirmed root cause|root cause", investigation)
    )
    route_known = routing["path"] in {"support_resolvable", "engineering_required"} or bool(
        re.search(
            r"(?is)support-resolvable|engineering[- ]required|engineering escalation|escalate to engineering|classification complete|no-deploy|no deploy|sandbox deploy skipped",
            diagnosis_and_recent_text,
        )
    )

    test_current = artifacts["test_report"]["exists"] and artifacts["test_report"]["size"] > 80
    test_passed = _test_report_confirms_fix(key)
    test_failed = bool(test_current and not test_passed and re.search(r"(?is)\bfail(?:ed|ing)?\b|not fixed|revert|required: yes|blocked", test_report))
    test_needs_rerun = not test_passed and test_current
    context_packet, context_packet_chars = _build_context_packet_for_issue(key)
    metadata_manifest_text = _read_text_for_resume(metadata_manifest)

    messages_separated = _messages_are_separated(internal_notes, jira_message)
    step_transition_contracts = _evaluate_transition_contracts(
        hypothesis=hypothesis,
        investigation=investigation,
        metadata_manifest_text=metadata_manifest_text,
        internal_notes=internal_notes,
        jira_message=jira_message,
        messages_separated=messages_separated,
    )
    step10_artifacts_current = bool(
        artifacts["internal_notes"]["exists"]
        and artifacts["internal_notes"]["size"] > 80
        and artifacts["jira_message"]["exists"]
        and artifacts["jira_message"]["size"] > 80
    )

    if has_schema and has_stored_signatures:
        step3_complete = bool(
            jira_signature_stable and inv_signature_stable and artifacts["investigation"]["exists"] and artifacts["investigation"]["size"] > 80
        )
        step4_complete = bool(step3_complete and hypothesis_signature_stable)
    else:
        step3_complete = artifacts["investigation"]["exists"] and artifacts["investigation"]["size"] > 80
        step4_complete = bool(
            step3_complete and (
                (artifacts["hypothesis"]["exists"] and artifacts["hypothesis"]["size"] > 80)
                or re.search(r"(?is)root cause hypothesis|smallest viable fix|sandbox validation plan|solution plan", investigation)
            )
        )

    if has_schema and has_stored_signatures and not jira_signature_stable:
        step3_complete = False
        step4_complete = False

    step5_complete = bool(step4_complete and not routing_on_hold and metadata["raw_production_dir"]["has_files"])
    step6_complete = bool(step5_complete and not routing_on_hold and problem_location)
    step7_complete = bool(step6_complete and route_known)
    step8_complete = bool(step7_complete and not routing_on_hold and (candidate_exists or has_no_deploy))
    step9_required = routing["path"] in {"support_resolvable", "engineering_required"} or (route_known and not has_no_deploy)
    if step9_required:
        step9_complete = bool(
            step8_complete
            and test_current
            and test_passed
            and (has_no_deploy or (test_signature_stable and metadata_signature_stable) if has_schema else True)
        )
    else:
        step9_complete = bool(has_no_deploy and step8_complete and test_current and test_passed)

    step10_complete = bool(step9_complete and step10_artifacts_current and messages_separated)

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
    summary_current = bool(summary_mtime and newest_issue_mtime and summary_mtime + 1 >= newest_issue_mtime and step10_complete)

    steps: list[dict[str, Any]] = []
    original_disposition = _disposition(status or "")
    disposition = "active" if force_active and original_disposition == "escalated" else original_disposition
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
        steps.extend([
            _resume_step(
                3,
                "Analyze issue",
                "complete" if step3_complete else ("stale" if has_schema and not jira_signature_stable else "pending"),
                "Current investigation artifact is current and tied to this Jira source." if step3_complete else "Run Step 3 and write investigation record." if not has_schema else "Run Step 3 if Step 3 signature/Jira source mismatch.",
                "Emit STEP_3 resume-skip;" if step3_complete else "Run Step 3 and write investigation record.",
                [artifacts["investigation"]["path"]],
            ),
            _resume_step(
                4,
                "Synthesize problem hypothesis",
                "complete" if step4_complete else ("stale" if step3_complete else "pending"),
                "Hypothesis artifact matches persisted signature." if step4_complete else "Create/update Hypothesis from Step 3 summary." ,
                "Emit STEP_4 resume-skip; preserve hypothesis until it becomes stale." if step4_complete else "Create/update Hypothesis from Step 3 summary.",
                [artifacts["hypothesis"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                5,
                "Retrieve relevant Production metadata",
                "blocked" if routing_on_hold else ("complete" if step5_complete else "pending"),
                "Production metadata evidence is current." if step5_complete else "Run targeted Step 5 metadata retrieval using sf CLI." ,
                "Emit STEP_5 resume-skip; keep current raw metadata unless Step 4 evidence changes." if step5_complete else "Run targeted Step 5 metadata retrieval using sf CLI.",
                [metadata["raw_production_dir"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                6,
                "Identify exact problem location",
                "blocked" if routing_on_hold else ("complete" if step6_complete else "pending"),
                "Problem location is current." if step6_complete else "Run Step 6 drilling to identify exact artifact, location, and failure point." ,
                "Emit STEP_6 resume-skip; preserve current problem location data." if step6_complete else "Run Step 6 drilling and update investigation with exact artifact and failure point.",
                [artifacts["investigation"]["path"]],
            ),
            _resume_step(
                7,
                "Engineering escalation gate",
                "complete" if step7_complete else ("stale" if step6_complete and not route_known else "pending"),
                "Routing state is recorded in durable state." if step7_complete else "Classify Support-resolvable vs Engineering-required and record it in state." ,
                "Emit STEP_7 resume-skip; reuse durable routing." if step7_complete else "Classify Support-resolvable vs Engineering-required and record it in durable state.",
                [artifacts["eng_handoff"]["path"], artifacts["investigation"]["path"]],
            ),
            _resume_step(
                8,
                "Prepare candidate solution",
                "complete" if step8_complete else ("blocked" if routing_on_hold else ("stale" if step7_complete and not candidate_exists else "pending")),
                "Candidate/proposed solution workspace is current." if step8_complete else "Prepare or revise candidate solution in the metadata workspace." ,
                "Emit STEP_8 resume-skip; reuse existing workspace." if step8_complete else "Prepare or revise candidate solution in the metadata workspace.",
                [metadata["sandbox_work_dir"]["path"], metadata["confirmed_dir"]["path"]],
            ),
            _resume_step(
                9,
                "Deploy and test in Sandbox",
                "complete" if step9_complete else (
                    "stale" if test_needs_rerun or (step8_complete and test_signature_stable is False and has_schema) else
                    ("blocked" if routing_on_hold else "pending")
                ),
                "Current test report is passing and aligned with metadata signature." if step9_complete else (
                    "Test report indicates a failed validation; rerun Step 8/9 with updated candidate." if test_needs_rerun else
                    "Deploy + test run needed." if step8_complete else "Step 8 completion required before testing."
                ),
                "Emit STEP_9 resume-skip if validation is still current." if step9_complete else "Run Step 9 deploy/test against the allowlisted Sandbox.",
                [artifacts["test_report"]["path"], metadata["workspace_manifest"]["path"]],
            ),
            _resume_step(
                10,
                "Draft internal notes and Jira message",
                "complete" if step10_complete else ("stale" if step9_complete and step10_artifacts_current else ("pending" if not step9_complete else "blocked")),
                "Draft artifacts are current and separated." if step10_complete else "Draft/update internal notes, Jira message, and engineering handoff if required.",
                "Emit STEP_10 resume-skip; avoid rewriting drafts if Step 9 is still current." if step10_complete else "Draft/update internal notes and Jira message from latest Step 9 result." ,
                [artifacts["internal_notes"]["path"], artifacts["jira_message"]["path"], artifacts["eng_handoff"]["path"]],
            ),
        ])

        steps.append(_resume_step(
            11,
            "Update dated summary",
            "complete" if summary_current and step10_complete else ("blocked" if not step10_complete else "pending"),
            "Latest dated summary is newer than issue artifacts." if summary_current and step10_complete else "Requires Step 10 first." if not step10_complete else "Latest dated summary is missing or older than issue artifacts.",
            "Emit STEP_11 __summary__ resume-skip unless the run changed artifacts." if summary_current and step10_complete else "Update today's issue summary once issue artifacts are complete.",
            [_path_relative_for_prompt(summary_path) if summary_path else _path_relative_for_prompt(_today_issue_summary_path())],
        ))
        steps.append(_resume_step(
            12,
            "Inform operator",
            "pending",
            "Always report the result of this run.",
            "Emit STEP_12 __complete__ and summarize only what changed or what remains blocked.",
            [],
        ))

    plan_for_contracts = {"steps": steps}
    _apply_transition_contracts_to_plan(plan_for_contracts, step_transition_contracts)
    steps = plan_for_contracts["steps"]
    next_step = next((s for s in steps if s["step"] != 12 and s["status"] not in {"complete", "skipped"}), steps[-1] if steps else None)
    quality_gates = {
        "step_6_problem_location": "pass" if step6_complete else "needs_rework" if step5_complete else "pending",
        "step_9_test_report": "pass" if step9_complete else ("failed" if test_needs_rerun else "pending"),
        "step_10_message_separation": "pass" if step10_complete else ("needs_rework" if step10_artifacts_current else "pending"),
        "step_4_to_5_transition": step_transition_contracts.get("step4_to_step5", {}).get("status", "pending"),
        "step_5_to_6_transition": step_transition_contracts.get("step5_to_step6", {}).get("status", "pending"),
        "step_8_to_9_transition": step_transition_contracts.get("step8_to_step9", {}).get("status", "pending"),
        "step_9_to_10_transition": step_transition_contracts.get("step9_to_step10", {}).get("status", "pending"),
    }
    return {
        "key": key,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": PIPELINE_STATE_SCHEMA_VERSION,
        "context_packet": context_packet,
        "context_packet_chars": context_packet_chars,
        "context_packet_tokens": context_packet.get("estimated_tokens", 0),
        "source_mtime": datetime.fromtimestamp(source_mtime, timezone.utc).isoformat() if source_mtime else "",
        "routing": routing,
        "deliverable": deliverable,
        "evidence_prechecks": evidence_prechecks,
        "signatures": signatures,
        "transition_contracts": step_transition_contracts,
        "tool_permissions": _build_step_tool_permissions(next((step.get("step") for step in steps if step.get("step") != 12 and step.get("status") not in {"complete", "skipped"}), 3)),
        "quality_gates": quality_gates,
        "mode": disposition,
        "original_mode": original_disposition,
        "force_active": force_active,
        "next_step": next_step,
        "why_next_step": (next_step or {}).get("reason"),
        "artifacts": artifacts,
        "metadata": metadata,
        "recent_evidence": recent_evidence,
        "steps": steps,
    }


def _build_step(plan: dict[str, Any], step_no: int) -> dict[str, Any] | None:
    for step in plan.get("steps") or []:
        if step.get("step") == step_no:
            return step
    return None


def _apply_loop_state_to_plan(
    plan: dict[str, Any],
    key: str,
    status: str = "",
    *,
    rebuild_from_artifacts: bool = False,
) -> dict[str, Any]:
    state = {} if rebuild_from_artifacts else _read_pipeline_state(key)
    has_schema = _state_has_schema(state)
    stored_signatures = state.get("signatures", {}) if isinstance(state.get("signatures", {}), dict) else {}
    signatures = {
        "jira_source": _build_jira_signature(key, _issue_source_mtime(key)),
        "investigation": _file_signature(OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)),
        "hypothesis": _file_signature(OUTPUTS / FILE_LOCATIONS["hypothesis"].format(key=key)),
        "test_report": _file_signature(OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)),
        "metadata_workspace": _file_signature(_metadata_workspace_dirs()["sandbox_work"] / key / "metadata-workspace.json"),
    }

    has_stored_signatures = has_schema and bool(stored_signatures)

    def sig_complete(field: str) -> bool:
        return _signatures_match(signatures.get(field, ""), stored_signatures.get(field))

    loop_state = _loop_state_for_resume(
        state,
        has_schema=has_schema,
        has_stored_signatures=has_stored_signatures,
        jira_signature_stable=(not has_schema or sig_complete("jira_source")),
        inv_signature_stable=sig_complete("investigation"),
        step4_signature_stable=sig_complete("hypothesis"),
        metadata_signature_stable=sig_complete("metadata_workspace"),
        test_signature_stable=sig_complete("test_report"),
    )
    loop_reason = _loop_stop_reason(loop_state)

    routing = dict(plan.get("routing") or {})
    if loop_reason:
        routing["path"] = "on_hold"
        routing["confidence"] = "high"
        routing["reason"] = f"Loop control hold: {loop_reason}"
        plan["routing"] = routing

    metadata_rounds_exceeded = loop_state["metadata_rounds"] >= PIPELINE_LOOP_LIMITS["metadata_rounds"]
    deploy_rounds_exceeded = loop_state["deploy_rounds"] >= PIPELINE_LOOP_LIMITS["deploy_rounds"]
    no_candidate_delta = loop_state.get("no_candidate_delta_count", 0) > 0
    candidate_changed = has_schema and has_stored_signatures and not sig_complete("metadata_workspace")
    candidate_step = _build_step(plan, 9)
    note_step = _build_step(plan, 10)

    if candidate_changed and candidate_step:
        if candidate_step["status"] == "complete":
            candidate_step["status"] = "stale"
        candidate_step["reason"] = "Candidate workspace signature changed; rerun Step 9/10."
        candidate_step["action"] = "Run Step 9 deploy/test against the allowlisted Sandbox after candidate updates."
    if note_step:
        if candidate_changed and note_step["status"] == "complete":
            note_step["status"] = "stale"
        if no_candidate_delta:
            note_step["status"] = "blocked"
        if loop_reason in {STEP_LOOP_MARKER_REASONS["deploy"], STEP_LOOP_MARKER_REASONS["candidate"], STEP_LOOP_MARKER_REASONS["stoppoint"]}:
            note_step["status"] = "blocked"
            note_step["reason"] = "Loop control hold pending manual review."

    for step_no in (5, 6, 8):
        step = _build_step(plan, step_no)
        if not step:
            continue
        if metadata_rounds_exceeded or loop_reason in {STEP_LOOP_MARKER_REASONS["metadata"], STEP_LOOP_MARKER_REASONS["stoppoint"]}:
            if step["status"] != "complete":
                step["status"] = "blocked"
                step["reason"] = "Loop metadata budget hit; manual review or source/input refresh required."
            step["action"] = f"Resolve '{loop_reason}' before continuing."

    step9 = _build_step(plan, 9)
    if step9 and (deploy_rounds_exceeded or loop_reason in {STEP_LOOP_MARKER_REASONS["deploy"], STEP_LOOP_MARKER_REASONS["candidate"], STEP_LOOP_MARKER_REASONS["stoppoint"]} or no_candidate_delta):
        step9["status"] = "blocked" if step9["status"] != "complete" else step9["status"]
        if step9["status"] != "complete":
            step9["reason"] = "Loop control hold; rerun is capped or candidate delta stalled."

    step4 = _build_step(plan, 4)
    step6 = _build_step(plan, 6)
    step10 = _build_step(plan, 10)
    status6 = step6.get("status") if step6 else "pending"
    status9 = step9.get("status") if step9 else "pending"

    quality_gates = {
        "step_6_problem_location": "pass" if status6 == "complete" else ("blocked" if status6 == "blocked" else "needs_rework" if status6 in {"stale", "pending"} else "pending"),
        "step_9_test_report": (
            "blocked" if status9 in {"blocked"} else
            "pass" if status9 == "complete" else
            "needs_rework" if status9 == "stale" else "pending"
        ),
        "step_10_message_separation": "pass" if (step10 and step10.get("status") == "complete") else (
            "blocked" if step10 and step10.get("status") == "blocked" else "pending"
        ),
        "loop_limit": "blocked" if loop_reason else ("pass" if not (metadata_rounds_exceeded or deploy_rounds_exceeded) else "needs_rework"),
    }
    if plan.get("quality_gates") and isinstance(plan.get("quality_gates"), dict):
        plan["quality_gates"].update(quality_gates)
    else:
        plan["quality_gates"] = quality_gates

    steps = plan.get("steps") or []
    if len(steps) > 0:
        for step in steps:
            if step.get("status") == "complete":
                continue
            if step.get("step") == 12:
                continue
            if plan.get("next_step") and plan["next_step"].get("step") == step.get("step"):
                break
            plan["next_step"] = step
            plan["why_next_step"] = step.get("reason")
            break
    plan["loop_state"] = loop_state
    plan["loop_reason"] = loop_reason
    plan["source"] = "v2-loop-aware"
    return plan


_build_pipeline_resume_plan_legacy = _build_pipeline_resume_plan


def _build_pipeline_resume_plan(
    key: str,
    status: str = "",
    jira_updated: str | None = None,
    *,
    force_active: bool = False,
    rebuild_from_artifacts: bool = False,
) -> dict[str, Any]:
    plan = _build_pipeline_resume_plan_legacy(
        key,
        status,
        jira_updated,
        force_active=force_active,
        rebuild_from_artifacts=rebuild_from_artifacts,
    )
    similarity_lookup = _build_similarity_lookup_for_plan(key, status=status)
    plan["similar_issues"] = similarity_lookup
    plan["similar_issues_context_available"] = bool(similarity_lookup.get("cluster_id") or similarity_lookup.get("cluster_state"))
    plan["similarity_context_enabled"] = bool(similarity_lookup.get("enabled"))
    plan["pipeline_similarity_mode"] = str(
        similarity_lookup.get("selected_mode") or "full_investigation"
    )
    plan["pipeline_similarity_mode_reason"] = str(similarity_lookup.get("selected_mode_reason") or "No similarity context selected.")
    return _apply_loop_state_to_plan(
        plan,
        key,
        status=status,
        rebuild_from_artifacts=rebuild_from_artifacts,
    )


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
        f"- Why next step: {plan.get('why_next_step', '').strip() or 'No explicit reason recorded.'}",
        "- Rule: completed steps are not work items. Emit one concise `STEP_N <KEY> resume-skip` line if needed for progress, then continue.",
        "- Rule: do not reread or rewrite completed artifacts unless a pending/stale downstream step needs exact details.",
        "- Rule: if Jira source changed after an artifact, treat that artifact and downstream artifacts as stale.",
        "- Rule: recent evidence below is run history, not a prompt. Use it to avoid rediscovering confirmed facts; if it proves a route, update the durable artifact and continue.",
        "",
    ]
    if plan.get("force_active"):
        lines.extend([
            "## Operator Force-Run Override",
            "- The Jira status is already Escalated to Engineering, but the operator explicitly requested a full CaseOps pipeline run anyway.",
            "- Ignore the normal pre-escalated skip rule for this run only. Process the issue through investigation, Salesforce diagnosis, sandbox-safe validation/proposal, notes, Jira message draft, and summary as applicable.",
            "- This override does not relax safety rules: Production remains read-only, Jira writes are not allowed unless separately approved, and Sandbox writes/deploys must use the allowlisted Sandbox only.",
            "",
        ])
    recent_evidence = plan.get("recent_evidence") or []
    if recent_evidence:
        lines.extend([
            "## Recent Pipeline Evidence",
            "These concise lines are from prior/current run logs and should prevent repeated investigation:",
        ])
        lines.extend(f"- {line}" for line in recent_evidence[:10])
        lines.append("")

    similarity = plan.get("similar_issues") or {}
    if similarity.get("enabled") or similarity.get("lookup_performed"):
        lines.extend([
            "## STEP_2B Similar Issue Lookup",
            f"- Enabled: {similarity.get('enabled', False)}",
            f"- Lookup performed: {similarity.get('lookup_performed', False)}",
            f"- Selected mode: {similarity.get('selected_mode', 'full_investigation')} — {similarity.get('selected_mode_reason', 'No similarity-based reason available.')}",
        ])
        if similarity.get("lookup_error"):
            lines.append(f"- Status: lookup_failed ({similarity.get('lookup_error')})")
        if similarity.get("cluster_id"):
            lines.append(f"- Cluster ID: {similarity.get('cluster_id')}")
            lines.append(f"- Canonical issue: {similarity.get('canonical_issue') or '(not set)'}")
            lines.append(f"- Classification for this issue: {similarity.get('classification') or similarity.get('cluster_type') or 'unrelated'}")
            lines.append(
                f"- Candidate counts: total={similarity.get('candidate_count', 0)}, open={similarity.get('open_count', 0)}, "
                f"closed={similarity.get('closed_count', 0)}"
            )
            lines.append(
                f"- Closed/resolved context included: {'yes' if similarity.get('cluster_state', '').lower() == 'active' or not similarity.get('cluster_state') else 'n/a'}"
            )
            if similarity.get("summary_url"):
                lines.append(f"- Public-safe summary: {similarity['summary_url']}")
            if similarity.get("summary_preview"):
                lines.append("- Summary preview:")
                lines.append(f"  {similarity.get('summary_preview')}")
            lines.append(f"- Similarity safety: requires_delta_validation={bool(similarity.get('safety', {}).get('requires_delta_validation', False))}, "
                         f"reuse_allowed={bool(similarity.get('safety', {}).get('reuse_allowed', False))}, "
                         f"reuse_reason={similarity.get('safety', {}).get('reuse_reason', 'n/a')}")
            lines.append(f"- Model adjudication: enabled={bool(similarity.get('model_adjudication_enabled'))}, status={similarity.get('adjudication_status', 'not_available')}")
            if similarity.get("model_adjudication_fallback"):
                lines.append(f"- Model adjudication fallback: {similarity.get('model_adjudication_fallback')}")

            delta_plan = similarity.get("delta_validation") if isinstance(similarity.get("delta_validation"), dict) else {}
            if delta_plan:
                lines.extend([
                    "",
                    "### Delta Validation Gate",
                    f"- Enabled: {bool(delta_plan.get('enabled'))}",
                    f"- Gate result: {delta_plan.get('gate_result', 'unknown')}",
                    f"- Allowed mode: {delta_plan.get('selected_mode_if_allowed', 'delta_validation')}",
                    f"- Fallback mode: {delta_plan.get('fallback_mode', 'full_investigation')}",
                    f"- Reason: {delta_plan.get('reason', '')}",
                    "- Required Salesforce checks:",
                ])
                for check in (delta_plan.get("salesforce_validation_checks") or [])[:8]:
                    lines.append(f"  - {check}")
                lines.append("- Drafting guardrails:")
                for guardrail in (delta_plan.get("drafting_guardrails") or [])[:8]:
                    lines.append(f"  - {guardrail}")

            for section in ("Open matches", "Closed matches"):
                matches = similarity.get("open_matches" if section == "Open matches" else "closed_matches") or []
                if not matches:
                    continue
                lines.append("")
                lines.append(f"### {section}")
                for match in matches[:10]:
                    if not isinstance(match, dict):
                        continue
                    key = match.get("key", "")
                    if not key:
                        continue
                    status = match.get("status", "")
                    stale = "stale" if bool(match.get("is_stale")) else "current"
                    classification = match.get("classification", "")
                    confidence = match.get("confidence")
                    reasons = match.get("reasons", [])
                    evidence_terms = match.get("evidence_terms", [])
                    evidence = ", ".join(evidence_terms[:4])
                    reason = ", ".join(str(r) for r in reasons[:3])
                    lines.append(
                        f"- {key} ({status}, {stale}, {classification})"
                        + (f"; confidence: {confidence}" if confidence is not None else "")
                        + (f"; reasons: {reason}" if reason else "")
                        + (f"; evidence: {evidence}" if evidence else "")
                    )
                    adjudication = match.get("adjudication") if isinstance(match.get("adjudication"), dict) else {}
                    if adjudication:
                        validation = ", ".join((adjudication.get("required_validation") or [])[:3])
                        against = ", ".join((adjudication.get("evidence_against") or [])[:3])
                        if against:
                            lines.append(f"  - Evidence against / difference warnings: {against}")
                        if validation:
                            lines.append(f"  - Required validation: {validation}")
        else:
            lines.append(f"- Reason: {similarity.get('selected_mode_reason', 'No cluster context for this issue.')}")
        lines.append("")

    lines.extend([
        "| Step | Status | Action |",
        "| --- | --- | --- |",
    ])
    for step in plan.get("steps", []):
        lines.append(f"| {step.get('step')} {step.get('name')} | {step.get('status')} | {step.get('action')} |")

    context_packet = plan.get("context_packet") or {}
    if context_packet:
        org_knowledge = context_packet.get("org_knowledge", {})
        org_file_count = len(org_knowledge.get("selected_files", []))
        artifact_count = len(context_packet.get("artifacts", []))
        estimated_tokens = context_packet.get("estimated_tokens", 0)
        max_context_chars = context_packet.get("max_allowed_chars", 0)
        lines.extend([
            "",
            "## Context Packet",
            f"Policy version: {context_packet.get('version', 'n/a')}, tokens: {estimated_tokens}, max context chars: {max_context_chars}, "
            f"selected org files: {org_file_count}, selected artifact summaries: {artifact_count}.",
        ])
        if org_file_count:
            lines.append("Selected org-knowledge files:")
            for item in org_knowledge.get("selected_files", []):
                rel = item.get("path", "")
                sig = item.get("signature", "")
                chars = item.get("summary_chars", 0)
                lines.append(f"- {rel} ({chars} chars, sig={sig})")
            if artifact_count:
                lines.append("Selected artifact summaries:")
                for item in context_packet.get("artifacts", [])[:8]:
                    path = item.get("path", "")
                    sig = item.get("signature", "")
                    chars = item.get("signature_chars", 0)
                    lines.append(f"- {path} ({chars} chars, sig={sig})")
                lines.append(f"Total artifact summaries: {artifact_count}.")

    evidence_prechecks = plan.get("evidence_prechecks") or {}
    if evidence_prechecks:
        enabled = bool(evidence_prechecks.get("enabled", False))
        lines.extend([
            "",
            "## Evidence Prechecks",
            f"- Enabled: {enabled}",
        ])
        if enabled:
            lines.append(f"- Result: {'pass' if evidence_prechecks.get('all_ok') else 'blockers detected'}")
            if evidence_prechecks.get("blocking_branches"):
                lines.append(f"- Blocking branches: {', '.join(evidence_prechecks.get('blocking_branches', []))}")
            if evidence_prechecks.get("failed_branches"):
                lines.append(f"- Failed branches: {', '.join(evidence_prechecks.get('failed_branches', []))}")
            evidence_files = evidence_prechecks.get("evidence_files", [])
            if evidence_files:
                lines.append("Evidence files:")
                for item in evidence_files:
                    lines.append(f"- {item}")
            branches = evidence_prechecks.get("branches") or {}
            if branches:
                lines.extend([
                    "",
                    "| Branch | Status | Blocking | Summary |",
                    "| --- | --- | --- | --- |",
                ])
                for name, payload in branches.items():
                    if not isinstance(payload, dict):
                        continue
                    summary = payload.get("summary")
                    if isinstance(summary, dict):
                        summary = ", ".join(
                            f"{k}={json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v}"
                            for k, v in list(summary.items())[:2]
                        ) if summary else ""
                    else:
                        summary = ""
                    lines.append(f"| {name} | {payload.get('status', 'unknown')} | {payload.get('blocking', False)} | {summary} |")

    transition_contracts = plan.get("transition_contracts") or {}
    if transition_contracts:
        lines.extend([
            "",
            "## Transition Contracts",
            "| Transition | Result | Missing Fields |",
            "| --- | --- | --- |",
        ])
        for contract_name, payload in transition_contracts.items():
            if not isinstance(payload, dict):
                continue
            missing = ",".join(payload.get("missing", []))
            lines.append(f"| {contract_name} | {payload.get('status', 'pending')} | {missing or 'n/a'} |")

    tool_permissions = plan.get("tool_permissions") or {}
    if tool_permissions:
        active_step = tool_permissions.get("active_step", "unknown")
        active_tools = tool_permissions.get("active_step_tools", [])
        lines.extend([
            "",
            "## Tool Permissions",
            f"- Active step: {active_step}",
            f"- Allowed tools: {', '.join(active_tools) if isinstance(active_tools, list) else 'unknown'}",
        ])
        step_rules = tool_permissions.get("steps", {})
        if isinstance(step_rules, dict) and step_rules:
            lines.append("Per-step rules:")
            for step_key in sorted(step_rules.keys(), key=lambda raw: int(raw) if str(raw).isdigit() else 10**9):
                step_rule = step_rules[step_key]
                if not isinstance(step_rule, dict):
                    continue
                role = step_rule.get("role", "unknown")
                allowlist = step_rule.get("allowlist", [])
                if isinstance(allowlist, list):
                    lines.append(f"  - STEP_{step_key}: {role} -> {', '.join(allowlist)}")
                else:
                    lines.append(f"  - STEP_{step_key}: {role}")

    quality_gates = plan.get("quality_gates", {})
    if quality_gates:
        lines.extend([
            "",
            "## Quality Gates",
            "| Gate | Result |",
            "| --- | --- |",
        ])
        for key, value in quality_gates.items():
            lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def _prepare_resume_plan(
    key: str,
    status: str = "",
    jira_updated: str | None = None,
    *,
    force_active: bool = False,
) -> tuple[dict[str, Any], Path, str]:
    plan = _build_pipeline_resume_plan(key, status, jira_updated, force_active=force_active)
    plan_path = _write_pipeline_resume_plan(plan)
    return plan, plan_path, _format_resume_plan_for_prompt(plan, plan_path)


def _repair_pipeline_state_from_artifacts_after_run(
    key: str,
    run_key: str,
    *,
    reason: str,
    status: str = "",
    jira_updated: str | None = None,
    force_active: bool = False,
) -> None:
    """Rebuild durable resume state after an interrupted run so the next run does not trust stale state."""
    try:
        plan = _build_pipeline_resume_plan(
            key,
            status,
            jira_updated,
            force_active=force_active,
            rebuild_from_artifacts=True,
        )
        plan["repair"] = {
            "rebuilt_from_artifacts": True,
            "rebuilt_at": datetime.now(timezone.utc).isoformat(),
            "previous_state_ignored": True,
            "reason": reason,
        }
        plan_path = _write_pipeline_resume_plan(plan)
        next_step = plan.get("next_step") or {}
        if next_step:
            _log_emit_line(
                run_key,
                f"Pipeline state rebuilt from current artifacts after {reason}; next STEP_{next_step.get('step')} ({next_step.get('name')}, {next_step.get('status')}). Plan: {_path_relative_for_prompt(plan_path)}",
            )
        else:
            _log_emit_line(
                run_key,
                f"Pipeline state rebuilt from current artifacts after {reason}. Plan: {_path_relative_for_prompt(plan_path)}",
            )
        manifest_changed([key])
    except Exception as exc:
        _log_emit_line(run_key, f"WARNING: failed to rebuild pipeline state after {reason}: {exc}")


def _log_resume_plan_summary(run_key: str, plan: dict[str, Any], plan_path: Path) -> None:
    next_step = plan.get("next_step") or {}
    steps = plan.get("steps") or []
    completed = sum(1 for step in steps if step.get("status") == "complete")
    total = len(steps)
    step_num = next_step.get("step", "?")
    name = next_step.get("name", "Unknown")
    status = next_step.get("status", "unknown")
    similarity = plan.get("similar_issues") or {}
    similarity_cluster_id = _safe_cluster_text(similarity.get("cluster_id"))
    selected_mode = str(similarity.get("selected_mode", "full_investigation"))
    selected_mode_reason = _safe_cluster_text(similarity.get("selected_mode_reason") or "normal pipeline controls")
    classification = _safe_cluster_text(similarity.get("classification") or similarity.get("cluster_type"))
    candidate_count = similarity.get("candidate_count", 0)
    open_count = similarity.get("open_count", 0)
    closed_count = similarity.get("closed_count", 0)
    adjudication_status = similarity.get("adjudication_status", "not_available")
    delta_plan = similarity.get("delta_validation") if isinstance(similarity.get("delta_validation"), dict) else {}
    if similarity.get("enabled") or similarity.get("lookup_performed"):
        if similarity_cluster_id:
            _log_emit_line(
                run_key,
                f"Similarity lookup: cluster_id={similarity_cluster_id}, candidates={candidate_count} "
                f"(open={open_count}, closed={closed_count}), classification={classification or 'unrelated'}, "
                f"mode={selected_mode}, reason={selected_mode_reason}"
            )
            _log_emit_line(
                run_key,
                f"Similarity adjudication: enabled={bool(similarity.get('model_adjudication_enabled'))}, "
                f"status={adjudication_status}, fallback={_safe_cluster_text(similarity.get('model_adjudication_fallback')) or 'n/a'}"
            )
            if delta_plan:
                _log_emit_line(
                    run_key,
                    f"Delta validation gate: enabled={bool(delta_plan.get('enabled'))}, "
                    f"result={delta_plan.get('gate_result', 'unknown')}, reason={delta_plan.get('reason', '')}"
                )
        else:
            _log_emit_line(
                run_key,
                f"Similarity lookup: no cluster assigned; mode={selected_mode}, reason={selected_mode_reason}"
            )
    elif similarity.get("lookup_error"):
        _log_emit_line(
            run_key,
            f"Similarity lookup failed: {similarity.get('lookup_error')}"
        )
    _log_emit_line(
        run_key,
        f"Resume planner: next STEP_{step_num} ({name}, {status}); {completed}/{total} step checkpoints complete. Plan: {_path_relative_for_prompt(plan_path)}",
    )


def _resume_plan_short_circuit(run_key: str, plan: dict[str, Any]) -> bool:
    """Return True after logging completion when no Claude work remains."""
    steps = plan.get("steps") or []
    pending_work = [
        step for step in steps
        if step.get("step") != 12 and step.get("status") not in {"complete", "skipped"}
    ]
    if pending_work:
        return False

    mode = str(plan.get("mode") or "")
    key = str(plan.get("key") or run_key)
    if mode == "closed":
        _log_emit_line(run_key, f"STEP_2 {key} resume-skip — closed/resolved archive is already current.")
    elif mode == "escalated":
        _log_emit_line(run_key, f"STEP_2 {key} resume-skip — pre-escalated handoff is already current.")
    else:
        _log_emit_line(run_key, f"Resume planner: no actionable pipeline steps remain for {key}.")
    _log_emit_line(run_key, "STEP_12 __complete__")
    _log_emit_line(run_key, "No Claude run needed; existing artifacts are current.")
    return True


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


def _parse_iso_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _estimate_step_timings(step_markers: list[tuple[int, datetime]], *, run_end: datetime) -> dict[str, Any]:
    if not step_markers:
        return {}
    timings: dict[str, Any] = {}
    markers = sorted(step_markers, key=lambda item: item[1])
    for idx, (step_no, started_at) in enumerate(markers):
        ended_at = markers[idx + 1][1] if idx + 1 < len(markers) else run_end
        timings[str(step_no)] = {
            "start": started_at.isoformat(),
            "end": ended_at.isoformat(),
            "duration_seconds": max(0.0, (ended_at - started_at).total_seconds()),
            "status": "complete",
        }
    return timings


def _parse_run_metrics_from_logs(run_key: str, run_started: datetime, run_ended: datetime, status: str = "unknown") -> dict[str, Any]:
    entries = _read_pipeline_log_entries(run_key)
    filtered = []
    for row in entries:
        try:
            ts = _parse_iso_ts(str(row.get("ts") or ""))
        except Exception:
            ts = None
        if ts is None:
            continue
        if ts < run_started or ts > run_ended:
            continue
        filtered.append((ts, str(row.get("text") or "")))

    step_markers: list[tuple[int, datetime]] = []
    step_token_usage: dict[str, dict[str, int]] = {}
    step_subagent_calls: dict[str, int] = {}
    step_tool_calls: dict[str, int] = {}
    current_step: int | None = None
    token_available = False
    run_tokens = {field: 0 for field in _TOKEN_USAGE_FIELDS}
    cost_usd: float | None = None
    last_stop_code = ""
    loop_events = {
        "repeat_metadata": 0,
        "deploy_fail": 0,
        "no_candidate_delta": 0,
        "safe_stoppoint_hit": 0,
    }
    for ts, text in filtered:
        marker = _PIPELINE_STEP_MARKER_RE.search(text)
        if marker:
            try:
                step_no = int(marker.group(1))
            except ValueError:
                step_no = None
            if step_no is not None:
                step_markers.append((step_no, ts))
                current_step = step_no

                if str(step_no) not in step_token_usage:
                    step_token_usage[str(step_no)] = {field: 0 for field in _TOKEN_USAGE_FIELDS}
                if str(step_no) not in step_subagent_calls:
                    step_subagent_calls[str(step_no)] = 0
                if str(step_no) not in step_tool_calls:
                    step_tool_calls[str(step_no)] = 0
        if _PIPELINE_LOOP_REASON_REASONS["repeat_metadata"].search(text):
            last_stop_code = STEP_LOOP_MARKER_REASONS["metadata"]
            loop_events["repeat_metadata"] += 1
        elif _PIPELINE_LOOP_REASON_REASONS["deploy_fail"].search(text):
            last_stop_code = STEP_LOOP_MARKER_REASONS["deploy"]
            loop_events["deploy_fail"] += 1
        elif _PIPELINE_LOOP_REASON_REASONS["no_candidate_delta"].search(text):
            last_stop_code = STEP_LOOP_MARKER_REASONS["candidate"]
            loop_events["no_candidate_delta"] += 1
        elif _PIPELINE_LOOP_REASON_REASONS["safe_stoppoint_hit"].search(text):
            last_stop_code = STEP_LOOP_MARKER_REASONS["stoppoint"]
            loop_events["safe_stoppoint_hit"] += 1

        match = _TOKEN_USAGE_LOG_RE.search(text)
        if match:
            token_available = True
            step_key = str(current_step) if current_step is not None else "unassigned"
            step_token_usage.setdefault(step_key, {field: 0 for field in _TOKEN_USAGE_FIELDS})
            run_tokens["input_tokens"] += int((match.group(2) or "0").replace(",", ""))
            run_tokens["output_tokens"] += int((match.group(3) or "0").replace(",", ""))
            run_tokens["cache_creation_input_tokens"] += int((match.group(4) or "0").replace(",", ""))
            run_tokens["cache_read_input_tokens"] += int((match.group(5) or "0").replace(",", ""))
            step_token_usage[step_key]["input_tokens"] += int((match.group(2) or "0").replace(",", ""))
            step_token_usage[step_key]["output_tokens"] += int((match.group(3) or "0").replace(",", ""))
            step_token_usage[step_key]["cache_creation_input_tokens"] += int((match.group(4) or "0").replace(",", ""))
            step_token_usage[step_key]["cache_read_input_tokens"] += int((match.group(5) or "0").replace(",", ""))
            if "cost=" in text.lower():
                for raw in re.findall(r"\$([0-9]+\.[0-9]+)", text):
                    try:
                        cost_usd = float(raw)
                    except (TypeError, ValueError):
                        pass
                continue
        if "cost=" in text.lower() and "Token usage:" not in text:
            for raw in re.findall(r"\$([0-9]+\.[0-9]+)", text):
                try:
                    cost_usd = float(raw)
                except (TypeError, ValueError):
                    pass

        if text.startswith("[") and "]" in text:
            tool_match = _PIPELINE_TOOL_CALL_RE.match(text)
            if tool_match:
                step_key = str(current_step) if current_step is not None else "unassigned"
                tool_name = tool_match.group("tool") or ""
                step_tool_calls[step_key] = step_tool_calls.get(step_key, 0) + 1
                if _normalize_tool_name(tool_name) == "agent":
                    step_subagent_calls[step_key] = step_subagent_calls.get(step_key, 0) + 1

    for key in set(step_token_usage) | set(step_tool_calls):
        for field in _TOKEN_USAGE_FIELDS:
            step_token_usage.setdefault(key, {}).setdefault(field, 0)

    step_timings = _estimate_step_timings(step_markers, run_end=run_ended)
    for step_no, timing in step_timings.items():
        if step_no in step_token_usage:
            timing["token_usage"] = step_token_usage[step_no]
        if step_no in step_subagent_calls:
            timing["subagent_calls"] = step_subagent_calls[step_no]
            timing["subagent_calls_by_tool"] = {
                "agent": step_subagent_calls[step_no],
            }
        else:
            timing["subagent_calls"] = 0
            timing["subagent_calls_by_tool"] = {"agent": 0}
        timing["tool_calls"] = step_tool_calls.get(step_no, 0)
        if timing["status"] == "failed" or timing.get("status") == "blocked":
            continue
        timing["status"] = "complete"

    total_subagent_calls = sum(step_subagent_calls.values())
    total_tool_calls = sum(step_tool_calls.values())
    token_usage = run_tokens if token_available else {field: None for field in _TOKEN_USAGE_FIELDS}

    duration = (run_ended - run_started).total_seconds()
    if duration < 0:
        duration = 0.0
    return {
        "start": run_started.isoformat(),
        "end": run_ended.isoformat(),
        "duration_seconds": duration,
        "status": status,
        "step_timings": step_timings,
        "token_usage": token_usage,
        "step_token_usage": step_token_usage,
        "subagent_calls": total_subagent_calls,
        "subagent_calls_by_step": step_subagent_calls,
        "tool_calls_by_step": step_tool_calls,
        "tool_calls": total_tool_calls,
        "cost_usd": cost_usd,
        "last_stop_code": last_stop_code,
        "loop_events": loop_events,
    }


def _format_run_metrics_summary(issue_key: str, metrics: dict[str, Any]) -> str:
    step_timings = metrics.get("step_timings", {})
    step_list = ",".join(sorted(step_timings.keys(), key=lambda raw: int(raw) if str(raw).isdigit() else 10**9))
    token_usage = metrics.get("token_usage", {})
    input_tokens = token_usage.get("input_tokens") if isinstance(token_usage, dict) else None
    output_tokens = token_usage.get("output_tokens") if isinstance(token_usage, dict) else None
    cache_create = token_usage.get("cache_creation_input_tokens") if isinstance(token_usage, dict) else None
    cache_read = token_usage.get("cache_read_input_tokens") if isinstance(token_usage, dict) else None
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = int(input_tokens) + int(output_tokens)
        if isinstance(cache_create, int):
            total_tokens += int(cache_create)
        if isinstance(cache_read, int):
            total_tokens += int(cache_read)
        cache_tokens = (int(cache_create) if isinstance(cache_create, int) else 0) + (int(cache_read) if isinstance(cache_read, int) else 0)
        tokens_text = f"{total_tokens} (cache={cache_tokens})"
    else:
        tokens_text = "unavailable"
    cost = metrics.get("cost_usd")
    if cost is None and isinstance(input_tokens, int) and isinstance(output_tokens, int) and (input_tokens + output_tokens) > 0:
        cost_text = "cost=unavailable"
    else:
        cost_text = f"cost=${cost:.4f}" if cost is not None else "cost=unavailable"

    return (
        f"Run summary [{issue_key}]: steps=[{step_list or 'none'}], total_time={float(metrics.get('duration_seconds', 0.0)):.1f}s, "
        f"tokens={tokens_text}, {cost_text}, status={metrics.get('status', 'unknown')}"
    )


def _update_loop_state_from_run(state: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    if not _state_has_schema(state):
        return _default_loop_state()

    loop_state = _load_loop_state(state)
    events = metrics.get("loop_events", {})
    loop_state["metadata_rounds"] = _coerce_non_negative_int(loop_state.get("metadata_rounds"), 0) + _coerce_non_negative_int(
        events.get("repeat_metadata"),
        0,
    )
    loop_state["deploy_rounds"] = _coerce_non_negative_int(loop_state.get("deploy_rounds"), 0) + _coerce_non_negative_int(
        events.get("deploy_fail"),
        0,
    )
    loop_state["no_candidate_delta_count"] = _coerce_non_negative_int(
        loop_state.get("no_candidate_delta_count"),
        0,
    ) + _coerce_non_negative_int(events.get("no_candidate_delta"), 0)

    last_stop_code = str(metrics.get("last_stop_code") or "").strip()
    if last_stop_code:
        loop_state["latest_stop_code"] = last_stop_code
        loop_state["last_stoppoint_code"] = last_stop_code
    loop_state["last_seen"] = str(metrics.get("end") or "")
    loop_state["last_reason"] = "; ".join(
        f"{key}:{value}" for key, value in events.items() if int(value or 0) > 0
    )
    return {
        "metadata_rounds": _coerce_non_negative_int(loop_state.get("metadata_rounds")),
        "deploy_rounds": _coerce_non_negative_int(loop_state.get("deploy_rounds")),
        "no_candidate_delta_count": _coerce_non_negative_int(loop_state.get("no_candidate_delta_count")),
        "last_stoppoint_code": str(loop_state.get("last_stoppoint_code") or ""),
        "last_reason": str(loop_state.get("last_reason") or ""),
        "last_seen": str(loop_state.get("last_seen") or ""),
        "latest_stop_code": str(loop_state.get("latest_stop_code") or ""),
    }


def _update_pipeline_run_metrics(
    key: str,
    run_key: str,
    run_started: datetime,
    run_ended: datetime,
    *,
    status: str,
) -> dict[str, Any]:
    state = _read_pipeline_state(key)
    run_metrics = state.get("run_metrics") if isinstance(state.get("run_metrics"), dict) else {}
    if not isinstance(run_metrics, dict):
        run_metrics = {}
    latest = _parse_run_metrics_from_logs(run_key, run_started, run_ended, status=status)
    history = run_metrics.get("history")
    if not isinstance(history, list):
        history = []

    history.append(latest)
    if len(history) > 25:
        history = history[-25:]

    state["run_metrics"] = {
        "latest": latest,
        "history": history,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    if _state_has_schema(state):
        state["loop_state"] = _update_loop_state_from_run(state, latest)
    state["run_metrics_state_version"] = 1
    _write_pipeline_resume_plan({**state, "schema_version": state.get("schema_version", PIPELINE_STATE_SCHEMA_VERSION), "key": key})
    return latest

# -- run state ---------------------------------------------------------------
# Multiple issue-specific runs are allowed in parallel.
# Global actions block each other and block new issue runs.
# Issue runs are blocked only while a global action is active.

_state_lock = threading.Lock()
_active_keys: set[str] = set()          # currently running run keys
_active_run_controls: dict[str, dict[str, Any]] = {}
_log_q: queue.Queue[str] = queue.Queue()  # tagged messages: "key|line" or "__done__|key"
_manifest_q: queue.Queue[str] = queue.Queue()  # manifest change notifications
_PIPELINE_STEP_MARKER_RE = re.compile(r"\bSTEP_(\d+)(?:\s+[^\n\r]*)?", re.IGNORECASE)
_PIPELINE_TOOL_CALL_RE = re.compile(r"^\[(?P<tool>[^]\s]+)")
_PIPELINE_LOOP_REASON_REASONS = {
    "repeat_metadata": re.compile(r"(?i)repeat_metadata"),
    "deploy_fail": re.compile(r"(?i)deploy_fail"),
    "no_candidate_delta": re.compile(r"(?i)no_candidate_delta"),
    "safe_stoppoint_hit": re.compile(r"(?i)safe_stoppoint(_hit)?"),
}
_TOKEN_USAGE_LOG_RE = re.compile(
    r"Token usage:\s*total=([\d,]+),\s*input=([\d,]+),\s*output=([\d,]+)(?:,\s*cache_create=([\d,]+))?(?:,\s*cache_read=([\d,]+))?",
    re.IGNORECASE,
)


def _popen_process_group_kwargs() -> dict[str, Any]:
    if os.name == "posix":
        return {"start_new_session": True}
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": creationflags} if creationflags else {}


def _register_run_process(run_key: str, proc: subprocess.Popen[Any], label: str) -> None:
    with _state_lock:
        control = _active_run_controls.setdefault(run_key, {"processes": [], "stop_requested": False})
        control.setdefault("processes", []).append({"pid": proc.pid, "process": proc, "label": label})


def _unregister_run_process(run_key: str, proc: subprocess.Popen[Any]) -> None:
    with _state_lock:
        control = _active_run_controls.get(run_key)
        if not control:
            return
        processes = control.get("processes")
        if isinstance(processes, list):
            control["processes"] = [item for item in processes if item.get("process") is not proc]
        if not control.get("processes") and not control.get("stop_requested"):
            _active_run_controls.pop(run_key, None)


def _run_stop_requested(run_key: str) -> bool:
    with _state_lock:
        return bool((_active_run_controls.get(run_key) or {}).get("stop_requested"))


def _terminate_process_group(proc: subprocess.Popen[Any], *, grace_seconds: float = 5.0) -> bool:
    if proc.poll() is not None:
        return False
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(timeout=grace_seconds)
        return True
    except (LookupError, ProcessLookupError):
        return False
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


def _request_stop_for_run(run_key: str) -> dict[str, Any]:
    with _state_lock:
        control = _active_run_controls.setdefault(run_key, {"processes": [], "stop_requested": False})
        control["stop_requested"] = True
        process_items = list(control.get("processes") or [])
        was_active = run_key in _active_keys

    stopped: list[dict[str, Any]] = []
    for item in process_items:
        proc = item.get("process")
        if not isinstance(proc, subprocess.Popen):
            continue
        stopped.append({
            "pid": proc.pid,
            "label": item.get("label") or "process",
            "terminated": _terminate_process_group(proc),
        })

    if was_active:
        _log_emit_line(run_key, "Operator requested stop; terminating active subprocesses.")
        if not stopped:
            _log_emit_line(run_key, "Stop requested; no active subprocess was registered.")
    elif not stopped:
        _finish_run_control(run_key)
    return {"run_key": run_key, "was_active": was_active, "processes": stopped}


def _finish_run_control(run_key: str) -> None:
    with _state_lock:
        _active_run_controls.pop(run_key, None)


def _apply_caseops_env_aliases(env: dict[str, str]) -> None:
    """Expose stable alias names for Claude/subprocess prompts without changing canonical settings."""
    prod_alias = (env.get("CASEOPS_PRODUCTION_READ_ORG") or "").strip()
    sandbox_alias = (env.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
    if prod_alias and not (env.get("CASEOPS_PRODUCTION_ORG") or "").strip():
        env["CASEOPS_PRODUCTION_ORG"] = prod_alias
    if sandbox_alias and not (env.get("CASEOPS_SANDBOX_ORG") or "").strip():
        env["CASEOPS_SANDBOX_ORG"] = sandbox_alias


def _apply_caseops_sf_guard_env(env: dict[str, str]) -> None:
    """Route Claude/subprocess sf calls through the CaseOps Production write guard."""
    if os.name == "nt":
        return
    guard_dir = ROOT / "scripts" / "sf-guard"
    guard = guard_dir / "sf"
    if not guard.exists():
        return
    env.setdefault("CASEOPS_REAL_SF", "/usr/local/bin/sf")
    path = env.get("PATH") or os.environ.get("PATH") or ""
    env["PATH"] = f"{guard_dir}{os.pathsep}{path}" if path else str(guard_dir)


def _claude_process_env() -> dict[str, str]:
    """Environment for Claude Code CLI subprocess.

    For claude_code mode: omit ANTHROPIC_API_KEY. Claude Code CLI uses the
    long-lived token generated by `claude setup-token` in CLAUDE_CODE_OAUTH_TOKEN.
    For api_key mode: pass ANTHROPIC_API_KEY (API billing auth).
    Instance-specific output directories so Skill writes to correct location.
    """
    env = os.environ.copy()
    runtime_home = _safe_runtime_home()
    env["HOME"] = runtime_home.as_posix()
    try:
        runtime_home.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Keep a deterministic fallback; command runs will fail fast only if unwritable.
        env["HOME"] = "/tmp/caseops-home"
    env.setdefault("SF_DATA_DIR", str(Path(env["HOME"]) / ".sf"))
    env.setdefault("SFDX_DIR", str(Path(env["HOME"]) / ".sfdx"))
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
    _apply_caseops_env_aliases(env)
    _apply_caseops_sf_guard_env(env)
    # Pass instance-specific directories to Claude Skill
    env["CASEOPS_OUTPUTS_DIR"] = str(OUTPUTS)
    env["CASEOPS_JIRA_OUT_DIR"] = str(OUTPUTS / "jira")
    env["CASEOPS_ENV_FILE"] = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
    # 2026-06-06 compatibility alias; remove after deployments have moved to CASEOPS_ENV_FILE.
    env["CASEOPS_JIRA_ENV_FILE"] = env["CASEOPS_ENV_FILE"]
    if TEMP_ROOT:
        temp_root = Path(TEMP_ROOT)
        claude_tmp = temp_root / "claude-code"
        try:
            claude_tmp.mkdir(parents=True, exist_ok=True)
        except OSError:
            claude_tmp = temp_root
        env["CASEOPS_TEMP_DIR"] = str(temp_root)
        env["CLAUDE_CODE_TMPDIR"] = str(claude_tmp)
        env["TMPDIR"] = str(claude_tmp)
        env["TEMP"] = str(claude_tmp)
        env["TMP"] = str(claude_tmp)
    metadata_dirs = _metadata_workspace_dirs()
    env["CASEOPS_METADATA_ROOT"] = str(metadata_dirs["root"])
    env["CASEOPS_METADATA_CACHE_DIR"] = str(metadata_dirs["cache_root"])
    env["CASEOPS_METADATA_WORKSPACES_DIR"] = str(metadata_dirs["root"])
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


def _sf_auth_from_access_token(
    *,
    sf_bin: str,
    alias: str,
    token: str,
    instance_url: str,
    env: dict[str, str],
    timeout: int = 35,
) -> subprocess.CompletedProcess[str]:
    """Authenticate one Salesforce CLI alias from an env-held access token."""
    auth_env = env.copy()
    auth_env["SF_ACCESS_TOKEN"] = token
    auth_env.setdefault("HOME", _safe_runtime_home().as_posix())
    return _run_cli_command(
        [
            sf_bin,
            "org",
            "login",
            "access-token",
            "--alias",
            alias,
            "--instance-url",
            instance_url,
            "--no-prompt",
            "--json",
        ],
        env=auth_env,
        timeout=timeout,
        retries=1,
    )


def _sf_auth_from_sfdx_auth_url(
    *,
    sf_bin: str,
    alias: str,
    sfdx_auth_url: str,
    env: dict[str, str],
    timeout: int = 35,
) -> subprocess.CompletedProcess[str]:
    """Authenticate one Salesforce CLI alias from an SFDX auth URL."""
    auth_env = env.copy()
    auth_env.setdefault("HOME", _safe_runtime_home().as_posix())
    tmp_dir = Path(auth_env.get("CASEOPS_TEMP_DIR") or tempfile.gettempdir())
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        tmp_dir = Path(tempfile.gettempdir())

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            prefix="caseops-sfdx-auth-",
            dir=str(tmp_dir),
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            json.dump({"sfdxAuthUrl": sfdx_auth_url}, handle)
        return _run_cli_command(
            [
                sf_bin,
                "org",
                "login",
                "sfdx-url",
                "--sfdx-url-file",
                str(tmp_path),
                "--alias",
                alias,
                "--json",
            ],
            env=auth_env,
            timeout=timeout,
            retries=1,
        )
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass


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


_TOKEN_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _usage_value(usage: Any, key: str) -> int:
    if isinstance(usage, dict):
        raw = usage.get(key, 0)
    else:
        raw = getattr(usage, key, 0)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _merge_token_usage(total: dict[str, int], usage: Any) -> None:
    """Add Claude token usage into an accumulator."""
    if not usage:
        return
    for field in _TOKEN_USAGE_FIELDS:
        total[field] = total.get(field, 0) + _usage_value(usage, field)


def _extract_token_usage_payloads(event: dict[str, Any]) -> list[Any]:
    """Find usage payloads in Claude stream/API events without assuming one shape."""
    payloads: list[Any] = []
    if not isinstance(event, dict):
        return payloads
    if isinstance(event.get("usage"), dict):
        payloads.append(event["usage"])
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        payloads.append(message["usage"])
    result = event.get("result")
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        payloads.append(result["usage"])
    if any(event.get(field) is not None for field in _TOKEN_USAGE_FIELDS):
        payloads.append(event)
    return payloads


def _format_token_usage(usage: dict[str, int], cost_usd: float | None = None) -> str:
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    total = input_tokens + output_tokens + cache_create + cache_read
    if total == 0 and cost_usd is not None:
        return f"Token usage: unavailable, cost=${cost_usd:.4f}"
    parts = [
        f"total={total:,}",
        f"input={input_tokens:,}",
        f"output={output_tokens:,}",
    ]
    if cache_create or cache_read:
        parts.extend([
            f"cache_create={cache_create:,}",
            f"cache_read={cache_read:,}",
        ])
    if cost_usd is not None:
        parts.append(f"cost=${cost_usd:.4f}")
    return "Token usage: " + ", ".join(parts)


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


def _is_suppressed_tool_result(tool: str, detail: str) -> bool:
    """Hide tool results that are prompts/transcripts rather than useful operator progress."""
    tool_name = (tool or "").lower()
    if _is_pipeline_internal_unavailable_tool(tool):
        return True
    if tool_name in {"agent", "workflow"}:
        return True
    return _is_file_read_tool(tool, detail)


def _emit_tool_result_text(run_key: str, text: str, *, suppress: bool, max_lines: int = 12) -> None:
    if suppress:
        return
    noisy_json_keys = ('"stack":', '"cause":')
    raw_lines = [line for line in text.splitlines() if line.strip()]
    lines: list[str] = []
    skipped_traceback = False
    emitted_tool_warning = False

    for line in raw_lines:
        if any(key in line for key in noisy_json_keys):
            continue
        stripped = line.strip()
        exit_match = re.match(r"^Exit code\s+([1-9]\d*)\b", stripped, re.IGNORECASE)
        if exit_match:
            exception_line = next(
                (
                    candidate.strip()
                    for candidate in reversed(raw_lines)
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):\s+", candidate.strip())
                ),
                "",
            )
            suffix = f" ({exception_line})" if exception_line else ""
            lines.append(
                f"Tool warning: command returned exit code {exit_match.group(1)}{suffix}. Non-terminal; Claude may retry or adjust."
            )
            emitted_tool_warning = True
            continue
        if stripped.startswith("Traceback (most recent call last):"):
            skipped_traceback = True
            continue
        if skipped_traceback:
            if re.match(r'^\s*File "[^"]+", line \d+', line) or stripped.startswith(("^", "File ")):
                continue
            if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):\s+", stripped):
                if not emitted_tool_warning:
                    lines.append(
                        f"Tool warning: command raised {stripped}. Non-terminal; Claude may retry or adjust."
                    )
                    emitted_tool_warning = True
                continue
            skipped_traceback = False
        lines.append(line)
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
        "home": env.get("HOME") or _safe_runtime_home().as_posix(),
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
        with _PREFLIGHT_ENV_LOCK:
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

    env_file_path = Path(app.config["ENV_FILE_PATH"]) if app.config.get("ENV_FILE_PATH") else ROOT / ".env"

    def check_org(role: str, alias: str) -> None:
        global _sf_orgs_cache, _sf_orgs_cache_time
        role_status = result["sf"][role]
        if not alias:
            fail(f"Missing {role} Salesforce org alias in .env.")
            return

        token_key = "SF_PROD_ACCESS_TOKEN" if role == "prod" else "SF_SANDBOX_ACCESS_TOKEN"
        sfdx_auth_url_keys = (
            ("SF_PROD_SFDX_AUTH_URL", "CASEOPS_PRODUCTION_SFDX_AUTH_URL")
            if role == "prod"
            else ("SF_SANDBOX_SFDX_AUTH_URL", "CASEOPS_SANDBOX_SFDX_AUTH_URL")
        )
        url_keys = (
            ("SF_PROD_INSTANCE_URL", "CASEOPS_PRODUCTION_INSTANCE_URL")
            if role == "prod"
            else ("SF_SANDBOX_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL")
        )
        access_token = _normalize_salesforce_access_token(_env_first(token_key, settings=settings))
        sfdx_auth_url = _extract_salesforce_sfdx_auth_url(_env_first(*sfdx_auth_url_keys, settings=settings))
        instance_url = _env_first(*url_keys, settings=settings)

        def refresh_and_auth(reason: str) -> bool:
            nonlocal access_token
            refresh_key = "SF_PROD_REFRESH_TOKEN" if role == "prod" else "SF_SANDBOX_REFRESH_TOKEN"
            refresh_token = _extract_salesforce_refresh_token(_env_first(refresh_key, settings=settings))
            if not refresh_token or not instance_url:
                role_status["refresh_error"] = "missing refresh token or instance URL"
                return False

            role_status["refresh_attempted"] = True
            role_status["refresh_reason"] = reason
            refresh_ok, refreshed = _refresh_salesforce_token_from_refresh_token(instance_url, refresh_token)
            if not refresh_ok or not refreshed:
                role_status["refresh_error"] = str(refreshed or "refresh failed")[:500]
                return False

            access_token = refreshed
            with _PREFLIGHT_ENV_LOCK:
                settings[token_key] = refreshed
                settings["SF_TOKENS_REFRESHED_AT"] = str(int(time.time()))
                _write_env_file(
                    {
                        token_key: refreshed,
                        "SF_TOKENS_REFRESHED_AT": settings["SF_TOKENS_REFRESHED_AT"],
                    },
                    env_file_path,
                )
                _sf_orgs_cache = None
                _sf_orgs_cache_time = 0.0

            auth = _sf_auth_from_access_token(
                sf_bin=sf_bin,
                alias=alias,
                token=refreshed,
                instance_url=instance_url,
                env=env,
            )
            role_status["auth_attempted_from_refresh_token"] = True
            role_status["auth_returncode"] = auth.returncode
            if auth.returncode != 0:
                role_status["auth_error"] = _command_error(auth)
                return False

            with _PREFLIGHT_ENV_LOCK:
                _sf_orgs_cache = None
                _sf_orgs_cache_time = 0.0
            return True

        display = _run_cli_command(
            [sf_bin, "org", "display", "--target-org", alias, "--json"],
            env=env,
            timeout=25,
            retries=1,
        )
        if display.returncode != 0 and sfdx_auth_url:
            role_status["auth_attempted_from_sfdx_auth_url"] = True
            auth = _sf_auth_from_sfdx_auth_url(
                sf_bin=sf_bin,
                alias=alias,
                sfdx_auth_url=sfdx_auth_url,
                env=env,
            )
            role_status["auth_returncode"] = auth.returncode
            if auth.returncode != 0:
                role_status["auth_error"] = _command_error(auth)
            else:
                _sf_orgs_cache = None
                _sf_orgs_cache_time = 0.0
                display = _run_cli_command(
                    [sf_bin, "org", "display", "--target-org", alias, "--json"],
                    env=env,
                    timeout=25,
                    retries=1,
                )

        if display.returncode != 0 and access_token and instance_url:
            role_status["auth_attempted_from_env_token"] = True
            auth = _sf_auth_from_access_token(
                sf_bin=sf_bin,
                alias=alias,
                token=access_token,
                instance_url=instance_url,
                env=env,
            )
            role_status["auth_returncode"] = auth.returncode
            if auth.returncode != 0:
                role_status["auth_error"] = _command_error(auth)
            else:
                _sf_orgs_cache = None
                _sf_orgs_cache_time = 0.0
                display = _run_cli_command(
                    [sf_bin, "org", "display", "--target-org", alias, "--json"],
                    env=env,
                    timeout=25,
                    retries=1,
                )

        role_status["display_returncode"] = display.returncode
        if display.returncode != 0:
            role_status["error"] = _command_error(display)
            if sfdx_auth_url or (access_token and instance_url):
                fail(f"Salesforce {role} org `{alias}` could not be authenticated from the saved CaseOps token/auth URL.")
            else:
                fail(f"Salesforce {role} org `{alias}` is not authenticated in the pipeline runtime environment and the saved token/auth URL is missing.")
            return

        data = _json_from_stdout(display.stdout)
        org = data.get("result", {}) if isinstance(data, dict) else {}
        connected_status = str(org.get("connectedStatus") or "").strip()
        if connected_status and connected_status.lower() != "connected":
            role_status["connectedStatus"] = connected_status
            if refresh_and_auth(f"org display connectedStatus={connected_status}"):
                display = _run_cli_command(
                    [sf_bin, "org", "display", "--target-org", alias, "--json"],
                    env=env,
                    timeout=25,
                    retries=1,
                )
                role_status["display_returncode_after_refresh"] = display.returncode
                data = _json_from_stdout(display.stdout)
                org = data.get("result", {}) if isinstance(data, dict) else {}
                connected_status = str(org.get("connectedStatus") or "").strip()
                role_status["connectedStatus"] = connected_status
            if connected_status and connected_status.lower() != "connected":
                fail(f"Salesforce {role} org `{alias}` is stale in the pipeline runtime environment and refresh did not restore it.")
                return

        role_status.update({
            "authenticated": True,
            "username": org.get("username", ""),
            "orgId": org.get("id", ""),
            "instanceUrl": org.get("instanceUrl", ""),
            "connectedStatus": connected_status,
        })

        if run_soql:
            query_cmd = [
                sf_bin,
                "data",
                "query",
                "--target-org",
                alias,
                "--query",
                "SELECT Id FROM Organization LIMIT 1",
                "--json",
            ]
            query = _run_cli_command(query_cmd, env=env, timeout=30, retries=1)
            query_error = _command_error(query)
            if query.returncode != 0 and "INVALID_SESSION_ID" in query_error.upper():
                role_status["soql_refresh_attempted"] = True
                if refresh_and_auth("SOQL preflight returned INVALID_SESSION_ID"):
                    query = _run_cli_command(query_cmd, env=env, timeout=30, retries=1)
                    query_error = _command_error(query)
            role_status["soql_returncode"] = query.returncode
            role_status["soql_ok"] = query.returncode == 0
            if query.returncode != 0:
                role_status["soql_error"] = query_error
                fail(f"Salesforce {role} org `{alias}` failed SOQL preflight in the pipeline runtime environment.")

    if _env_flag("CASEOPS_ENABLE_PARALLEL_PRECHECKS", default=False):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(check_org, "prod", prod_alias),
                executor.submit(check_org, "sandbox", sandbox_alias),
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    fail(f"Salesforce preflight worker failed unexpectedly: {type(exc).__name__}: {exc}")
    else:
        check_org("prod", prod_alias)
        check_org("sandbox", sandbox_alias)
    result["sf"]["ok"] = (
        result["sf"]["installed"]
        and result["sf"]["prod"]["authenticated"]
        and result["sf"]["sandbox"]["authenticated"]
        and (not run_soql or (result["sf"]["prod"]["soql_ok"] and result["sf"]["sandbox"]["soql_ok"]))
    )
    return result


def _collect_manifest_candidate_entries(metadata_manifest_text: str) -> list[str]:
    """Extract candidate file/object entries from a metadata workspace manifest."""
    if not metadata_manifest_text:
        return []
    try:
        parsed = json.loads(metadata_manifest_text)
    except json.JSONDecodeError:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add_candidate_value(raw: Any) -> None:
        if isinstance(raw, str):
            value = raw.strip()
            if value and value not in seen:
                seen.add(value)
                candidates.append(value)
            return
        if isinstance(raw, dict):
            for field in (
                "path",
                "file",
                "filename",
                "file_name",
                "sourcePath",
                "source_path",
                "fullPath",
                "full_path",
                "apiName",
                "api_name",
                "fullName",
                "full_name",
                "name",
                "member",
                "componentName",
                "component_name",
            ):
                if field in raw:
                    _add_candidate_value(raw.get(field))
            return
        if isinstance(raw, (list, tuple)):
            for entry in raw:
                _add_candidate_value(entry)

    if isinstance(parsed, dict):
        manifest_values = []
        for key in ("files", "components", "candidate_components", "changed_components", "artifacts", "file_candidates"):
            value = parsed.get(key)
            if value is not None:
                manifest_values.append(value)
        if not manifest_values and isinstance(parsed.get("attempt"), (dict, list, str)):
            manifest_values.append(parsed.get("attempt"))
        for value in manifest_values:
            _add_candidate_value(value)
    elif isinstance(parsed, list):
        for item in parsed:
            _add_candidate_value(item)

    return candidates


def _collect_org_access_branch_evidence(run_soql: bool = True, preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    preflight = preflight if preflight is not None else _collect_runtime_preflight(run_soql=run_soql)
    ok = bool(preflight.get("ok"))
    sf = preflight.get("sf", {})
    prod = sf.get("prod", {})
    sandbox = sf.get("sandbox", {})
    return {
        "branch": "org_accessibility",
        "status": "pass" if ok else "fail",
        "blocking": not ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
        "summary": {
            "prod_authenticated": bool(prod.get("authenticated")),
            "sandbox_authenticated": bool(sandbox.get("authenticated")),
            "prod_soql_ok": bool(prod.get("soql_ok")) if run_soql else False,
            "sandbox_soql_ok": bool(sandbox.get("soql_ok")) if run_soql else False,
            "issues": preflight.get("issues") or [],
            "caseops_llm_auth": preflight.get("caseops_llm_auth", ""),
            "sf_installed": bool(sf.get("installed")),
        },
    }


def _collect_org_knowledge_branch_evidence(key: str, row: dict[str, str]) -> dict[str, Any]:
    index = _read_org_knowledge_index()
    selected = _select_org_knowledge_files(key, row)
    root = _org_knowledge_dir()
    selected_payload = [str(path.relative_to(root)) for path in selected if path.is_file()]
    missing_always_read = []
    for rel in index.get("always_read", []):
        if not isinstance(rel, str):
            continue
        if not (root / rel).is_file():
            missing_always_read.append(rel)
    status = "pass"
    if not selected_payload:
        status = "warn"
    if missing_always_read:
        status = "fail"

    return {
        "branch": "org_knowledge_validation",
        "status": status,
        "blocking": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "selected_count": len(selected_payload),
            "selected_files": selected_payload,
            "max_selected_limit": int(index.get("max_topic_files") or PIPELINE_CONTEXT_LIMITS["max_context_files"]),
            "missing_always_read": missing_always_read,
            "missing_always_read_count": len(missing_always_read),
        },
        "advisory": bool(missing_always_read or not selected_payload),
    }


def _collect_object_component_branch_evidence(key: str, metadata_workspace_manifest: str) -> dict[str, Any]:
    metadata_dirs = _metadata_workspace_dirs()
    workspace_dir = metadata_dirs["sandbox_work"] / key
    if not metadata_workspace_manifest:
        return {
            "branch": "object_component_precheck",
            "status": "pass",
            "blocking": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "manifest_present": False,
                "manifest_path": str(_path_relative_for_prompt(workspace_dir / "metadata-workspace.json")),
                "candidate_count": 0,
                "missing_file_candidates": [],
                "non_file_candidates": 0,
            },
        }

    candidates = _collect_manifest_candidate_entries(metadata_workspace_manifest)
    if not candidates:
        return {
            "branch": "object_component_precheck",
            "status": "pass",
            "blocking": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "manifest_present": True,
                "manifest_path": str(_path_relative_for_prompt(workspace_dir / "metadata-workspace.json")),
                "candidate_count": 0,
                "missing_file_candidates": [],
                "non_file_candidates": 0,
            },
        }

    missing_file_candidates: list[str] = []
    non_file_candidates = 0
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        looks_like_file = bool(
            candidate.endswith((
                ".cls", ".trigger", ".object", ".object-meta.xml", ".field", ".field-meta.xml", ".flow", ".layout",
                ".layout-meta.xml", ".permissionSet", ".permissionSet-meta.xml", ".permissionSetGroup",
                ".permissionSetGroup-meta.xml", ".apex", ".queue", ".apex-meta.xml", ".xml"
            )) or "/" in candidate or "\\" in candidate
        )
        if not looks_like_file:
            non_file_candidates += 1
            continue
        found = False
        direct = (workspace_dir / candidate)
        if direct.exists():
            found = True
        elif candidate.endswith(".xml") and (workspace_dir / f"{candidate}.xml").exists():
            found = True
        if not found:
            inferred_name = candidate
            if "/" not in candidate and "\\" not in candidate:
                inferred_hits = [
                    p for p in workspace_dir.glob(f"**/{inferred_name}.*")
                    if p.is_file()
                ]
                found = bool(inferred_hits)
        if not found:
            missing_file_candidates.append(candidate)

    status = "pass"
    if missing_file_candidates:
        status = "fail"

    return {
        "branch": "object_component_precheck",
        "status": status,
        "blocking": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "manifest_present": True,
            "manifest_path": str(_path_relative_for_prompt(workspace_dir / "metadata-workspace.json")),
            "candidate_count": len(candidates),
            "missing_file_candidates": missing_file_candidates,
            "missing_file_candidate_count": len(missing_file_candidates),
            "non_file_candidates": non_file_candidates,
        },
    }


def _write_issue_evidence_branch_file(key: str, branch: str, payload: dict[str, Any]) -> Path:
    evidence_dir = _pipeline_state_evidence_dir(key)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    safe_branch = re.sub(r"[^A-Za-z0-9._-]", "_", branch or "branch")
    path = evidence_dir / f"{safe_branch}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _persist_issue_evidence_summary(key: str, summary: dict[str, Any]) -> None:
    state = _read_pipeline_state(key)
    if not isinstance(state, dict):
        state = {}
    state["schema_version"] = PIPELINE_STATE_SCHEMA_VERSION
    state["evidence_prechecks"] = summary
    path = _pipeline_state_path(key)
    _validate_instance_path(path, "write")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_issue_evidence_branches(key: str, run_soql: bool = True) -> dict[str, Any]:
    row = _find_manifest_row(key)
    manifest_path = _metadata_workspace_dirs()["sandbox_work"] / key / "metadata-workspace.json"
    manifest_text = _read_small_text(manifest_path, 1_000_000)
    enabled = _env_flag("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", default=False)
    if not enabled:
        return {
            "enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "branches": {},
            "all_ok": True,
            "blocking_branches": [],
            "failed_branches": [],
            "evidence_files": [],
        }

    def _run(branch_fn):
        return branch_fn()

    branches: list[tuple[str, Any]] = []
    branches.append(("org_accessibility", lambda: _collect_org_access_branch_evidence(run_soql=run_soql)))
    branches.append(("org_knowledge_validation", lambda: _collect_org_knowledge_branch_evidence(key, row)))
    branches.append(("object_component_precheck", lambda: _collect_object_component_branch_evidence(key, manifest_text)))

    collected: dict[str, dict[str, Any]] = {}
    evidence_files: list[str] = []
    if len(branches) <= 1:
        branch_results = [fn() for _name, fn in branches]
    elif _env_flag("CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES", default=False):
        with ThreadPoolExecutor(max_workers=min(len(branches), 3)) as executor:
            futures = {executor.submit(_run, fn): name for name, fn in branches}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "branch": name,
                        "status": "fail",
                        "blocking": False if name != "org_accessibility" else True,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {"error": f"{type(exc).__name__}: {exc}"},
                    }
                if not isinstance(result, dict):
                    result = {
                        "branch": name,
                        "status": "fail",
                        "blocking": False if name != "org_accessibility" else True,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "summary": {"error": "non-dict evidence result"},
                    }
                if result.get("branch") != name:
                    result["branch"] = name
                collected[name] = result
                try:
                    evidence_file = _write_issue_evidence_branch_file(key, name, result)
                    evidence_files.append(_path_relative_for_prompt(evidence_file))
                    result["evidence_file"] = _path_relative_for_prompt(evidence_file)
                except Exception:
                    continue
    else:
        for name, fn in branches:
            try:
                result = fn()
            except Exception as exc:
                result = {
                    "branch": name,
                    "status": "fail",
                    "blocking": False if name != "org_accessibility" else True,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "summary": {"error": f"{type(exc).__name__}: {exc}"},
                }
            if result.get("branch") != name:
                result["branch"] = name
            collected[name] = result
            try:
                evidence_file = _write_issue_evidence_branch_file(key, name, result)
                evidence_files.append(_path_relative_for_prompt(evidence_file))
                result["evidence_file"] = _path_relative_for_prompt(evidence_file)
            except Exception:
                continue

    blocking_branches = [branch for branch, result in collected.items() if result.get("blocking")]
    failed_branches = [branch for branch, result in collected.items() if result.get("status") == "fail"]
    all_ok = collected.get("org_accessibility", {}).get("status") == "pass"
    if all_ok:
        all_ok = all(
            not result.get("blocking") or result.get("status") == "pass"
            for result in collected.values()
        )

    summary = {
        "enabled": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "branches": collected,
        "all_ok": all_ok,
        "blocking_branches": blocking_branches,
        "failed_branches": failed_branches,
        "evidence_files": evidence_files,
    }
    _persist_issue_evidence_summary(key, summary)
    return summary


def _emit_runtime_preflight_or_stop(run_key: str, run_soql: bool = True, preflight: dict[str, Any] | None = None) -> bool:
    """Log and enforce runtime preflight before Claude-backed pipeline work starts."""
    _log_emit_line(run_key, "Preflight: validating Claude runtime, Salesforce CLI auth, and SOQL access")
    try:
        preflight = preflight or _collect_runtime_preflight(run_soql=run_soql)
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
    if prod.get("auth_attempted_from_env_token"):
        _log_emit_line(run_key, "Preflight: Production sf alias was authenticated from saved CaseOps token")
    if sandbox.get("auth_attempted_from_env_token"):
        _log_emit_line(run_key, "Preflight: Sandbox sf alias was authenticated from saved CaseOps token")
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
    """Tell Claude how to open Salesforce when CaseOps spawns the CLI without exposing link secrets."""
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
            "- Generic visual-only Salesforce session link is configured in `CASEOPS_SALESFORCE_MAGIC_LINK`. "
            "Read it only at the moment a browser inspection is required. Do not echo, print, log, paste, or store its value."
        )
    if prod_magic:
        lines.append(
            f"- **Production ({prod_label})** via `CASEOPS_PRODUCTION_MAGIC_LINK` — **visual read-only only**. "
            "Use `sf` CLI/SOQL for queries and metadata inspection. No Production creates, edits, deletes, deployments, "
            "or API calls with the frontdoor SID. Do not echo, print, log, paste, or store this env var value."
        )
    if sand_magic:
        lines.append(
            f"- **Sandbox ({sand_label})** via `CASEOPS_SANDBOX_MAGIC_LINK` — visual UI fallback only. "
            "Use `sf project deploy`, `sf data query`, Apex tests, and other CLI commands for investigation/deploy/test unless "
            "a browser-only action is required. Do not echo, print, log, paste, or store this env var value."
        )
    if not has_magic:
        lines.append(
            "- No Salesforce session link is set in `.env` "
            "(`CASEOPS_SALESFORCE_MAGIC_LINK`, `CASEOPS_PRODUCTION_MAGIC_LINK`, and/or `CASEOPS_SANDBOX_MAGIC_LINK`). "
            "If login blocks progress, say what you need."
        )
    lines.append("")
    return "\n".join(lines)


def _do_stream_proc(cmd: list[str], run_key: str) -> int:
    """Stream subprocess output to log queue. Returns exit code."""
    if _is_legacy_pipeline_cmd(cmd):
        _log_emit_line(
            run_key,
            "ERROR: Legacy command blocked: run_pipeline.py is deprecated and cannot be executed.",
        )
        return 1
    if cmd and cmd[0] == sys.executable:
        cmd = [cmd[0], "-u"] + cmd[1:]
    try:
        env = os.environ.copy()
        env["COLUMNS"] = "999"  # Prevent terminal wrapping in subprocess output
        env["CASEOPS_JIRA_OUT_DIR"] = str(OUTPUTS / "jira")  # Instance-specific Jira output dir
        env["CASEOPS_ENV_FILE"] = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
        # 2026-06-06 compatibility alias; remove after deployments have moved to CASEOPS_ENV_FILE.
        env["CASEOPS_JIRA_ENV_FILE"] = env["CASEOPS_ENV_FILE"]
        if TEMP_ROOT:
            env["CASEOPS_TEMP_DIR"] = str(TEMP_ROOT)
        metadata_dirs = _metadata_workspace_dirs()
        env["CASEOPS_METADATA_ROOT"] = str(metadata_dirs["root"])
        env["CASEOPS_METADATA_CACHE_DIR"] = str(metadata_dirs["cache_root"])
        env["CASEOPS_METADATA_WORKSPACES_DIR"] = str(metadata_dirs["root"])
        env["CASEOPS_METADATA_RAW_PROD_DIR"] = str(metadata_dirs["raw_prod"])
        env["CASEOPS_METADATA_SANDBOX_WORK_DIR"] = str(metadata_dirs["sandbox_work"])
        env["CASEOPS_METADATA_CONFIRMED_DIR"] = str(metadata_dirs["confirmed"])
        _apply_caseops_env_aliases(env)
        _apply_caseops_sf_guard_env(env)

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
            **_popen_process_group_kwargs(),
        )
        _register_run_process(run_key, proc, "subprocess")
        assert proc.stdout
        for line in proc.stdout:
            if _run_stop_requested(run_key):
                _log_emit_line(run_key, "Stop requested; terminating subprocess stream.")
                _terminate_process_group(proc)
                break
            _log_emit_line(run_key, line.rstrip())
        proc.wait()
        _log_emit_line(run_key, f"-- exit code {proc.returncode} --")
        return proc.returncode
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: {exc}")
        return 1
    finally:
        if "proc" in locals():
            _unregister_run_process(run_key, proc)


def _is_legacy_pipeline_cmd(cmd: list[str]) -> bool:
    """Return True when the command references the removed run_pipeline.py script."""
    return any(Path(arg).name == "run_pipeline.py" for arg in cmd if arg)


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


def _do_stream_anthropic_messages_api(prompt: str, run_key: str, issue_key: str | None = None) -> bool:
    """Stream a single user turn via Anthropic Messages API (API key on your Anthropic account).

    If issue_key is provided, parse Suggested reply and [INTERNAL] output into separate files.
    """
    if Anthropic is None:
        _log_emit_line(
            run_key,
            "ERROR: Python package `anthropic` is not installed. "
            "Install with: pip install anthropic",
        )
        return False
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        _log_emit_line(
            run_key,
            "ERROR: ANTHROPIC_API_KEY is empty. Set it in `.env` when using CASEOPS_LLM_AUTH=api_key.",
        )
        return False
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
        token_usage = {field: 0 for field in _TOKEN_USAGE_FIELDS}
        operator_name = (
            os.environ.get("CASEOPS_EXAMPLE_ASSIGNEE_NAME")
            or os.environ.get("CASEOPS_DEFAULT_ACTOR")
            or "the operator"
        ).strip()
        system_prompt = f"""You are CaseOps, a Jira triage and issue investigation assistant supporting {operator_name}.

## Your voice
Sound like a practical support operator, not like a perfect LLM. Be direct, concrete, human.

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
- Include Action: what the operator does next, if applicable.

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
                try:
                    final_message = stream.get_final_message()
                    _merge_token_usage(token_usage, getattr(final_message, "usage", None))
                except Exception:
                    pass
        _log_emit_line(run_key, "-- stream complete --")
        if any(token_usage.values()):
            _log_emit_line(run_key, _format_token_usage(token_usage))
        return full_response

    try:
        full_output = call_api()
        if issue_key:
            _save_claude_output(full_output, issue_key)
        return True
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: Anthropic API (after retries): {exc}")
        return False


def _do_stream_claude_code_cli(prompt: str, run_key: str, issue_key: str | None = None) -> bool:
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
        "--input-format",
        "text",
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
                _log_emit_line(run_key, "Open Settings > Claude and paste output from `claude setup-token`.")

        env = _claude_process_env()
        env["CASEOPS_OUTPUTS_DIR"] = str(OUTPUTS)
        if env.get("CLAUDE_CODE_TMPDIR"):
            _log_emit_line(run_key, f"Claude temp dir: {env['CLAUDE_CODE_TMPDIR']}")
        _log_emit_line(run_key, f"Invoking: {claude_bin} -p <stdin redacted> --output-format stream-json ...")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            bufsize=1,
            **_popen_process_group_kwargs(),
        )
        _register_run_process(run_key, proc, "claude")
        _log_emit_line(run_key, f"Process started (PID: {proc.pid})")
        assert proc.stdin
        proc.stdin.write(prompt)
        proc.stdin.close()
        assert proc.stdout
        assert proc.stderr
        assistant_text = []
        tool_uses: dict[str, tuple[str, str]] = {}
        stream_q: queue.Queue[tuple[str, str | None]] = queue.Queue()
        token_usage = {field: 0 for field in _TOKEN_USAGE_FIELDS}
        final_token_usage = {field: 0 for field in _TOKEN_USAGE_FIELDS}
        total_cost_usd: float | None = None
        current_tool_step: int | None = None

        def _read_pipe(pipe: Any, label: str) -> None:
            try:
                for line in pipe:
                    stream_q.put((label, line))
            finally:
                stream_q.put((label, None))

        threading.Thread(target=_read_pipe, args=(proc.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=_read_pipe, args=(proc.stderr, "stderr"), daemon=True).start()

        idle_timeout = _env_int("CASEOPS_CLAUDE_IDLE_TIMEOUT_SECONDS", 240, min_value=60, max_value=3600)
        total_timeout = _env_int("CASEOPS_CLAUDE_TOTAL_TIMEOUT_SECONDS", 1200, min_value=300, max_value=14400)
        started_at = time.monotonic()
        last_output_at = started_at
        open_streams = {"stdout", "stderr"}
        killed_for_timeout = False

        while open_streams:
            try:
                source, raw_value = stream_q.get(timeout=15)
            except queue.Empty:
                now = time.monotonic()
                if proc.poll() is not None:
                    continue
                if _run_stop_requested(run_key):
                    _log_emit_line(run_key, "Stop requested; killing Claude subprocess")
                    _terminate_process_group(proc)
                    killed_for_timeout = True
                    break
                if now - last_output_at > idle_timeout:
                    _log_emit_line(
                        run_key,
                        f"ERROR: Claude process produced no output for {idle_timeout}s — killing subprocess",
                    )
                    _terminate_process_group(proc)
                    killed_for_timeout = True
                    break
                if now - started_at > total_timeout:
                    _log_emit_line(
                        run_key,
                        f"ERROR: Claude process exceeded total timeout of {total_timeout}s — killing subprocess",
                    )
                    _terminate_process_group(proc)
                    killed_for_timeout = True
                    break
                continue

            if raw_value is None:
                open_streams.discard(source)
                continue

            raw = raw_value.strip()
            if not raw:
                continue
            if source == "stderr":
                _log_emit_line(run_key, f"ERR: {raw}")
                last_output_at = time.monotonic()
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                _log_emit_line(run_key, raw)
                last_output_at = time.monotonic()
                continue

            etype = event.get("type", "")
            emitted_progress = False
            usage_target = final_token_usage if etype == "result" else token_usage
            for usage_payload in _extract_token_usage_payloads(event):
                _merge_token_usage(usage_target, usage_payload)

            if etype == "assistant":
                for block in event.get("message", {}).get("content", []):
                    btype = block.get("type", "")
                    if btype == "text":
                        text = block.get("text", "")
                        if issue_key:
                            assistant_text.append(text)
                        for line in text.splitlines():
                            if line.strip():
                                marker = _PIPELINE_STEP_MARKER_RE.search(line)
                                if marker:
                                    try:
                                        current_tool_step = int(marker.group(1))
                                    except ValueError:
                                        pass
                                _log_emit_line(run_key, line)
                                emitted_progress = True
                    elif btype == "tool_use":
                        tool = block.get("name", "tool")
                        if _is_pipeline_internal_unavailable_tool(tool):
                            _log_emit_line(
                                run_key,
                                f"WARNING: tool '{tool}' is unavailable in CaseOps pipeline runs for STEP_{current_tool_step or 'unknown'}; continuing without its failed output.",
                            )
                        elif not _is_tool_allowlisted(current_tool_step, tool):
                            _log_emit_line(
                                run_key,
                                f"WARNING: tool '{tool}' used outside allowlist for STEP_{current_tool_step or 'unknown'}",
                            )
                        inp = block.get("input", {})
                        detail = inp.get("command") or inp.get("file_path") or inp.get("path") or ""
                        detail = str(detail).replace("\r", " ").replace("\n", " ").strip()
                        tool_id = str(block.get("id") or "")
                        if tool_id:
                            tool_uses[tool_id] = (str(tool), detail)
                        _log_emit_line(run_key, f"[{tool}]{' ' + detail if detail else ''}")
                        emitted_progress = True

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
                    suppress_result = _is_suppressed_tool_result(tool, detail)
                    for text in _content_text_fragments(block):
                        if issue_key and not suppress_result:
                            assistant_text.append(text)
                        _emit_tool_result_text(run_key, text, suppress=suppress_result)
                        if not suppress_result and text.strip():
                            emitted_progress = True

            elif etype == "result":
                subtype = event.get("subtype", "")
                cost = event.get("cost_usd")
                if cost is None:
                    cost = event.get("total_cost_usd")
                try:
                    total_cost_usd = float(cost) if cost is not None else total_cost_usd
                except (TypeError, ValueError):
                    pass
                cost_str = f"  cost: ${total_cost_usd:.4f}" if total_cost_usd is not None else ""
                _log_emit_line(run_key, f"-- {subtype}{cost_str} --")
                emitted_progress = True

            elif etype == "system":
                pass  # ignore init events

            if emitted_progress:
                last_output_at = time.monotonic()

        try:
            returncode = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _log_emit_line(run_key, "ERROR: Claude process did not exit after stream timeout — killing subprocess")
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
            return False

        if killed_for_timeout:
            return False
        effective_usage = final_token_usage if any(final_token_usage.values()) else token_usage
        if any(effective_usage.values()) or total_cost_usd is not None:
            _log_emit_line(run_key, _format_token_usage(effective_usage, total_cost_usd))
        if returncode == 0 and issue_key and assistant_text:
            full_output = "\n".join(assistant_text)
            _save_claude_output(full_output, issue_key)
        elif returncode != 0:
            _log_emit_line(run_key, f"-- exit code {returncode} --")
            return False
        return True

    except FileNotFoundError:
        _log_emit_line(run_key, "WARNING: 'claude' CLI not found on PATH")
        _log_emit_line(run_key, "Attempting fallback: launching Claude Code in new window via PowerShell script...")
        _fallback_launch_claude_window(issue_key, prompt, run_key)
        return False
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: {exc}")
        return False
    finally:
        if "proc" in locals():
            _unregister_run_process(run_key, proc)


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


def _do_stream_claude(prompt: str, run_key: str, issue_key: str | None = None) -> bool:
    """LLM entry: API Messages when ``api_key`` auth; else Claude Code CLI.

    If issue_key is provided, parse Suggested reply and [INTERNAL] output into separate files.
    """
    if caseops_llm_auth_uses_anthropic_api_key():
        return _do_stream_anthropic_messages_api(prompt, run_key, issue_key)
    return _do_stream_claude_code_cli(prompt, run_key, issue_key)


def _stream_proc(cmd: list[str], run_key: str) -> None:
    rc = 1
    try:
        rc = _do_stream_proc(cmd, run_key)
        if cmd and "jira_sync.py" in (arg for arg in cmd) and rc == 0:
            _log_emit_line(run_key, "Rebuilding similarity index after Jira sync...")
            _rebuild_similarity_clusters_if_enabled(
                run_key=run_key,
                manifest_rows=_read_manifest(),
                log=lambda msg: _log_emit_line(run_key, msg),
            )
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _finish_run_control(run_key)
        # Invalidate jira_summary caches after operations
        # - Global operations: clear all caches so fresh data is fetched from disk
        # - Individual issue operations: clear that issue's cache entry
        if run_key == _GLOBAL_KEY:
            jira_summary_cache.clear()
        else:
            # For individual issue syncs/runs, clear that issue's cached data
            _invalidate_jira_summary_cache(run_key)

        if cmd and "jira_sync.py" in (arg for arg in cmd) and rc == 0:
            if run_key == _GLOBAL_KEY:
                manifest_changed()
            else:
                manifest_changed([run_key])
        _log_emit_line(run_key, "Done: global run" if run_key == _GLOBAL_KEY else f"Done: {run_key}")
        _log_emit_done(run_key)


def _sync_issue_from_jira_now(key: str, *, timeout: int = 120) -> tuple[bool, str]:
    """Refresh one issue's Jira raw bundle/summary after a local Jira write."""
    env_file = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
    cmd = [
        sys.executable,
        "jira_sync.py",
        "--env-file",
        env_file,
        "--issue",
        key,
        "--out-dir",
        str(OUTPUTS / "jira"),
    ]
    env = os.environ.copy()
    env["CASEOPS_ENV_FILE"] = env_file
    # 2026-06-06 compatibility alias; remove after deployments have moved to CASEOPS_ENV_FILE.
    env["CASEOPS_JIRA_ENV_FILE"] = env_file
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out refreshing {key} from Jira after {timeout}s."
    except Exception as exc:
        return False, str(exc)[:500]

    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        return False, details[:500]

    _invalidate_jira_summary_cache(key)
    _rebuild_similarity_clusters_if_enabled(
        run_key=key,
        manifest_rows=_read_manifest(),
        log=lambda msg: _log_emit_line(key, msg),
    )
    manifest_changed([key])
    return True, ""


def _issue_sync_result(key: str) -> dict[str, Any]:
    ok, error = _sync_issue_from_jira_now(key)
    result: dict[str, Any] = {"ok": ok}
    if not ok:
        result["error"] = error
    return result


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
        _finish_run_control(run_key)
        # Phase 2: invalidate caches when pipeline completes so stale flags aren't served
        if issue_key:
            _invalidate_jira_summary_cache(issue_key)
            investigation_cache.pop(issue_key, None)
        _log_emit_line(run_key, "Done: global run" if run_key == _GLOBAL_KEY else f"Done: {run_key}")
        _log_emit_done(run_key)


def _issue_pipeline_runtime_ready(run_key: str) -> bool:
    """Validate runtime gates before an issue pipeline run starts."""
    evidence = _run_issue_evidence_branches(run_key, run_soql=True)
    evidence_preflight = evidence.get("branches", {}).get("org_accessibility", {}).get("preflight") if evidence.get("enabled") else None

    sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
    if not sandbox_target:
        _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env")
        _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
        _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env and retry.")
        return False
    if evidence.get("enabled") and not evidence.get("all_ok"):
        _log_emit_line(run_key, "Preflight: evidence branch blockers detected; review branch evidence files.")
        branch_status = ", ".join(f"{name}:{result.get('status', 'unknown')}" for name, result in evidence.get("branches", {}).items())
        if branch_status:
            _log_emit_line(run_key, f"Evidence summary: {branch_status}")

    if not _emit_runtime_preflight_or_stop(run_key, preflight=evidence_preflight):
        return False

    if not caseops_llm_auth_uses_anthropic_api_key():
        try:
            claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
            subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
            _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
            _log_emit_line(run_key, "       Verify: `claude --version` runs, then open Settings > Claude and paste output from `claude setup-token`.")
            return False

    if caseops_llm_auth_uses_anthropic_api_key():
        api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
            _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")
    return True


def _stream_full_issue(key: str, run_key: str, run_preflight: bool = True, force_active: bool = False) -> None:
    """Run full CaseOps fix pipeline via the mounted jira-salesforce-fix-pipeline playbook.

    This invokes Claude Code with direct file-path instructions for Steps 1-12 orchestration.
    Do NOT call deprecated run_pipeline.py — that calls removed agents.
    """
    run_started = datetime.now(timezone.utc)
    should_update_metrics = False
    run_status = "failed"
    row: dict[str, str] = {}
    try:
        _log_emit_run_start(run_key, key)
        _log_emit_line(run_key, f"-- Processing {key} via jira-salesforce-fix-pipeline playbook --")

        if run_preflight and not _issue_pipeline_runtime_ready(run_key):
            return

        row = next((r for r in _read_manifest() if r.get("Key") == key), {})
        resume_plan, resume_path, resume_block = _prepare_resume_plan(
            key,
            row.get("Status", ""),
            row.get("Updated", ""),
            force_active=force_active,
        )
        _log_resume_plan_summary(run_key, resume_plan, resume_path)
        if _resume_plan_short_circuit(run_key, resume_plan):
            return
        should_update_metrics = True
        prompt = _build_claude_prompt(
            key,
            "Run the full CaseOps fix pipeline for this issue through completion of investigation, "
            "internal notes, and Jira customer message (and any sandbox/escalation steps the playbook "
            "requires for this issue). Read the mounted playbook files directly; do not invoke a slash-skill."
            + (
                " Operator override: ignore the normal pre-escalated Jira-status skip for this issue and process it as active."
                if force_active else ""
            ),
            resume_block,
        )
        if _do_stream_claude(prompt, run_key, key):
            run_status = "completed"
        elif _run_stop_requested(run_key):
            run_status = "stopped"
    finally:
        if should_update_metrics and run_status != "completed":
            _repair_pipeline_state_from_artifacts_after_run(
                key,
                run_key,
                reason=run_status,
                status=row.get("Status", ""),
                jira_updated=row.get("Updated", ""),
                force_active=force_active,
            )
        if should_update_metrics:
            run_ended = datetime.now(timezone.utc)
            try:
                latest = _update_pipeline_run_metrics(
                    key,
                    run_key,
                    run_started,
                    run_ended,
                    status=run_status,
                )
                _log_emit_line(run_key, _format_run_metrics_summary(key, latest))
            except Exception as exc:
                _log_emit_line(run_key, f"WARNING: failed to persist run metrics: {exc}")
        with _state_lock:
            _active_keys.discard(run_key)
        _finish_run_control(run_key)
        # Phase 2: invalidate caches for this issue when full-issue run completes
        _invalidate_jira_summary_cache(key)
        investigation_cache.pop(key, None)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _stream_reprocess_issue(key: str, run_key: str, run_preflight: bool = True, force_active: bool = False) -> None:
    """Reprocess single issue without Jira sync via the mounted jira-salesforce-fix-pipeline playbook.

    Useful for re-running a single issue that failed or needs investigation updates.
    """
    run_started = datetime.now(timezone.utc)
    should_update_metrics = False
    run_status = "failed"
    row: dict[str, str] = {}
    try:
        _log_emit_run_start(run_key, f"{key} reprocess")
        _log_emit_line(run_key, f"-- Reprocessing {key} (no sync) via jira-salesforce-fix-pipeline playbook --")

        if run_preflight and not _issue_pipeline_runtime_ready(run_key):
            return

        row = next((r for r in _read_manifest() if r.get("Key") == key), {})
        resume_plan, resume_path, resume_block = _prepare_resume_plan(
            key,
            row.get("Status", ""),
            row.get("Updated", ""),
            force_active=force_active,
        )
        _log_resume_plan_summary(run_key, resume_plan, resume_path)
        if _resume_plan_short_circuit(run_key, resume_plan):
            return
        should_update_metrics = True
        prompt = _build_claude_prompt(
            key,
            "Reprocess the CaseOps fix pipeline for this issue without re-syncing from Jira. "
            "Read the mounted jira-salesforce-fix-pipeline playbook files directly; do not invoke a slash-skill."
            + (
                " Operator override: ignore the normal pre-escalated Jira-status skip for this issue and process it as active."
                if force_active else ""
            ),
            resume_block,
        )
        if _do_stream_claude(prompt, run_key, key):
            run_status = "completed"
        elif _run_stop_requested(run_key):
            run_status = "stopped"
    finally:
        if should_update_metrics and run_status != "completed":
            _repair_pipeline_state_from_artifacts_after_run(
                key,
                run_key,
                reason=run_status,
                status=row.get("Status", ""),
                jira_updated=row.get("Updated", ""),
                force_active=force_active,
            )
        if should_update_metrics:
            run_ended = datetime.now(timezone.utc)
            try:
                latest = _update_pipeline_run_metrics(
                    key,
                    run_key,
                    run_started,
                    run_ended,
                    status=run_status,
                )
                _log_emit_line(run_key, _format_run_metrics_summary(key, latest))
            except Exception as exc:
                _log_emit_line(run_key, f"WARNING: failed to persist run metrics: {exc}")
        with _state_lock:
            _active_keys.discard(run_key)
        _finish_run_control(run_key)
        _invalidate_jira_summary_cache(key)
        investigation_cache.pop(key, None)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _global_max_parallel() -> int:
    return _env_int("CASEOPS_GLOBAL_MAX_PARALLEL", 1, min_value=1, max_value=4)


def _global_max_queue_passes() -> int:
    return _env_int("CASEOPS_GLOBAL_MAX_QUEUE_PASSES", 12, min_value=1, max_value=24)


def _plan_pending_issue_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps that require per-issue work. Global summary/report steps are excluded."""
    return [
        step for step in (plan.get("steps") or [])
        if step.get("step") not in {11, 12}
        and step.get("status") not in {"complete", "skipped"}
    ]


def _global_issue_queue_fingerprint(plan: dict[str, Any]) -> str:
    """In-memory queue fingerprint used to detect progress within one global run."""
    payload = {
        "status": plan.get("status") or "",
        "source_mtime": plan.get("source_mtime") or "",
        "mode": plan.get("mode") or "",
        "routing": plan.get("routing") or {},
        "deliverable": plan.get("deliverable") or {},
        "loop_state": plan.get("loop_state") or {},
        "next_step": plan.get("next_step") or {},
        "signatures": plan.get("signatures") or {},
        "transition_contracts": plan.get("transition_contracts") or {},
        "artifacts": plan.get("artifacts") or {},
        "metadata": plan.get("metadata") or {},
        "steps": plan.get("steps") or [],
    }
    return _sha256_signature(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _global_issue_queue_snapshot(key: str) -> tuple[bool, str, str]:
    row = next((r for r in _read_manifest() if r.get("Key") == key), {})
    plan = _build_pipeline_resume_plan(key, row.get("Status", ""), row.get("Updated", ""))
    fingerprint = _global_issue_queue_fingerprint(plan)
    pending = _plan_pending_issue_steps(plan)
    if pending:
        next_step = pending[0]
        return False, f"incomplete; next STEP_{next_step.get('step')} ({next_step.get('name')}, {next_step.get('status')})", fingerprint
    return True, "complete", fingerprint


def _global_issue_queue_detail(key: str) -> tuple[bool, str]:
    complete, detail, _fingerprint = _global_issue_queue_snapshot(key)
    return complete, detail


def _select_global_issue_queue(run_key: str) -> list[str]:
    rows = _read_manifest()
    queued: list[str] = []
    skipped = 0
    skipped_escalated = 0
    for row in rows:
        key = (row.get("Key") or "").strip()
        if not key:
            continue
        status = row.get("Status", "")
        if _disposition(status) == "escalated":
            skipped_escalated += 1
            continue
        complete, detail = _global_issue_queue_detail(key)
        if not complete:
            _log_emit_line(
                run_key,
                f"Queue: {key} {detail}",
            )
            queued.append(key)
        else:
            skipped += 1
    if skipped_escalated:
        _log_emit_line(run_key, f"Queue: skipped {skipped_escalated} issue(s) already Escalated to Engineering.")
    _log_emit_line(run_key, f"Queue: {len(queued)} issue(s) need pipeline work; {skipped} already current; {skipped_escalated} escalated skipped.")
    return queued


def _run_global_issue_worker(key: str, index: int, total: int, *, reprocess: bool) -> tuple[str, bool, str]:
    with _state_lock:
        if key in _active_keys:
            return key, False, "already running"
        _active_keys.add(key)

    _log_emit_line(_GLOBAL_KEY, f"Queue: starting {key} ({index}/{total})")
    try:
        if reprocess:
            _stream_reprocess_issue(key, key, run_preflight=False)
        else:
            _stream_full_issue(key, key, run_preflight=False)

        complete, detail = _global_issue_queue_detail(key)
        if not complete:
            _log_emit_line(_GLOBAL_KEY, f"Queue: {key} {detail}")
            return key, False, detail
        _log_emit_line(_GLOBAL_KEY, f"Queue: {key} complete")
        return key, True, "complete"
    except Exception as exc:
        detail = f"failed unexpectedly: {type(exc).__name__}: {exc}"
        _log_emit_line(_GLOBAL_KEY, f"Queue: {key} {detail}")
        return key, False, detail


def _stream_global_skill(instruction: str, run_key: str) -> None:
    """Run global CaseOps pipeline as a CaseOps-owned issue queue."""
    try:
        _log_emit_line(run_key, f"-- Running CaseOps pipeline: {instruction.split(':')[1].strip() if ':' in instruction else instruction} --")

        if not _issue_pipeline_runtime_ready(run_key):
            return

        if "sync all issues from jira" in instruction.lower():
            env_file = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
            _log_emit_line(run_key, "STEP_1 __sync__")
            _log_emit_line(run_key, "CaseOps runtime: running Jira sync in the foreground")
            rc = _do_stream_proc(
                [sys.executable, "jira_sync.py", "--env-file", env_file, "--out-dir", str(OUTPUTS / "jira")],
                run_key,
            )
            if rc != 0:
                _log_emit_line(run_key, f"ERROR: Jira sync failed with exit code {rc}; stopping Auto-Process All before issue processing.")
                return
            _rebuild_similarity_clusters_if_enabled(
                run_key=run_key,
                manifest_rows=_read_manifest(),
                log=lambda msg: _log_emit_line(run_key, msg),
            )
            manifest_changed()
            _log_emit_line(run_key, "STEP_1 __sync__ complete")

        _log_emit_line(run_key, "STEP_2 __queue__")
        reprocess = "reprocess all active issues" in instruction.lower()
        queue_keys = _select_global_issue_queue(run_key)
        if not queue_keys:
            _log_emit_line(run_key, "Queue: no issue pipeline work needed.")
            return

        max_parallel = _global_max_parallel()
        max_passes = _global_max_queue_passes()
        total_initial = len(queue_keys)
        last_snapshots = {key: _global_issue_queue_snapshot(key) for key in queue_keys}
        last_details = {key: snapshot[1] for key, snapshot in last_snapshots.items()}
        last_fingerprints = {key: snapshot[2] for key, snapshot in last_snapshots.items()}
        incomplete_details = dict(last_details)
        incomplete_reasons: dict[str, str] = {key: f"needs work; {detail}" for key, detail in last_details.items()}
        completed_keys: set[str] = set()
        stop_reason = "completed"

        _log_emit_line(
            run_key,
            f"Queue: processing {total_initial} issue(s), max_parallel={max_parallel}, max_passes={max_passes}",
        )

        for queue_pass in range(1, max_passes + 1):
            if not queue_keys:
                break
            if _run_stop_requested(run_key):
                _log_emit_line(run_key, "Queue: stop requested; no further issues will be started.")
                stop_reason = "stop requested"
                break

            _log_emit_line(run_key, f"Queue pass {queue_pass}: processing {len(queue_keys)} issue(s)")
            pass_results: list[tuple[str, bool, str]] = []
            if max_parallel == 1:
                for idx, key in enumerate(queue_keys, start=1):
                    if _run_stop_requested(run_key):
                        _log_emit_line(run_key, "Queue: stop requested; no further issues will be started.")
                        stop_reason = "stop requested"
                        break
                    pass_results.append(_run_global_issue_worker(key, idx, len(queue_keys), reprocess=reprocess))
            else:
                with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                    futures = {
                        executor.submit(_run_global_issue_worker, key, idx, len(queue_keys), reprocess=reprocess): key
                        for idx, key in enumerate(queue_keys, start=1)
                    }
                    for future in as_completed(futures):
                        pass_results.append(future.result())
                        if _run_stop_requested(run_key):
                            for pending in futures:
                                pending.cancel()
                            _log_emit_line(run_key, "Queue: stop requested; pending issue starts were canceled where possible.")
                            stop_reason = "stop requested"
                            break

            next_queue: list[str] = []
            pass_completed = 0
            pass_incomplete = 0
            progressed = 0
            for key, ok, detail in pass_results:
                previous_detail = last_details.get(key)
                previous_fingerprint = last_fingerprints.get(key)
                snapshot_complete, snapshot_detail, snapshot_fingerprint = _global_issue_queue_snapshot(key)
                if ok and snapshot_complete:
                    completed_keys.add(key)
                    incomplete_details.pop(key, None)
                    incomplete_reasons.pop(key, None)
                    pass_completed += 1
                    if previous_detail != "complete" or previous_fingerprint != snapshot_fingerprint:
                        progressed += 1
                    last_details[key] = "complete"
                    last_fingerprints[key] = snapshot_fingerprint
                    continue
                pass_incomplete += 1
                incomplete_details[key] = snapshot_detail
                if detail.startswith("failed unexpectedly") or detail == "already running":
                    incomplete_reasons[key] = f"worker {detail}; planner says {snapshot_detail}"
                else:
                    incomplete_reasons[key] = f"needs more work; {snapshot_detail}"
                if snapshot_detail != previous_detail or snapshot_fingerprint != previous_fingerprint:
                    progressed += 1
                    incomplete_reasons[key] = f"advanced this pass; {snapshot_detail}"
                    next_queue.append(key)
                last_details[key] = snapshot_detail
                last_fingerprints[key] = snapshot_fingerprint

            _log_emit_line(
                run_key,
                f"Queue pass {queue_pass}: complete={pass_completed}, incomplete={pass_incomplete}, progressed={progressed}",
            )

            if _run_stop_requested(run_key):
                stop_reason = "stop requested"
                break
            if not next_queue:
                remaining = len(incomplete_details)
                if remaining:
                    stop_reason = "stalled"
                    _log_emit_line(
                        run_key,
                        f"Queue stalled: {remaining} issue(s) still incomplete, but no issue advanced during pass {queue_pass}.",
                    )
                    _log_emit_line(run_key, "Queue stalled: stopping to avoid repeating the same failed work.")
                    for key, detail in incomplete_details.items():
                        if not incomplete_reasons.get(key, "").startswith("worker "):
                            incomplete_reasons[key] = f"stalled/no progress in pass {queue_pass}; {detail}"
                break

            queue_keys = next_queue
            if queue_pass < max_passes:
                _log_emit_line(run_key, f"Queue: requeueing {len(queue_keys)} issue(s) that advanced but are not complete.")
        else:
            if incomplete_details:
                stop_reason = "max passes reached"
                _log_emit_line(
                    run_key,
                    f"Queue: reached max_passes={max_passes}; remaining incomplete issues require manual review or another run.",
                )
                for key, detail in incomplete_details.items():
                    if not incomplete_reasons.get(key, "").startswith("worker "):
                        incomplete_reasons[key] = f"max_passes={max_passes} reached; {detail}"

        complete = len(completed_keys)
        incomplete = len(incomplete_details)
        if incomplete == 0 and stop_reason == "completed":
            stop_reason = "all queued issues complete"
        _log_emit_line(run_key, f"Queue: finished. complete={complete}, incomplete={incomplete}, reason={stop_reason}")
        if incomplete:
            for key, detail in incomplete_details.items():
                reason = incomplete_reasons.get(key) or f"needs work; {detail}"
                _log_emit_line(run_key, f"Queue incomplete: {key} — {reason}")
        manifest_changed()
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _finish_run_control(run_key)
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
            existing.append(f"  - {FILE_LABELS[ftype]}: {_path_relative_for_prompt(path)}")

    files_block = "\n".join(existing) if existing else "  - None yet"
    org_knowledge_block = _build_org_knowledge_context_block(key, row)

    skill_md = (ROOT / "skills" / "jira-salesforce-fix-pipeline" / "SKILL.md").resolve()
    skill_line = str(skill_md) if skill_md.is_file() else f"(missing) {skill_md}"

    # Configured outputs directory, normally /data/outputs in Docker.
    outputs_dir_relative = OUTPUTS.relative_to(ROOT).as_posix() if OUTPUTS.is_relative_to(ROOT) else str(OUTPUTS)

    # Configured env file, normally /data/.env in Docker.
    env_file_path = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
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
        f"## CaseOps Output Directory\n"
        f"**CRITICAL for Docker runs:** All file paths in this run must use:\n"
        f"`{outputs_dir_relative}/` instead of the generic `outputs/` references in the playbook.\n"
        f"Example: Instead of `outputs/investigations/{{KEY}}.md`, use `{outputs_dir_relative}/investigations/{{KEY}}.md`\n\n"
        f"## CaseOps Configuration (.env)\n"
        f"**CRITICAL for Docker runs:** Use the active configuration file:\n"
        f"- Read Jira credentials and Salesforce orgs from: `{env_file_relative}`\n"
        f"- Do NOT read from `ROOT/.env`; Docker uses `/data/.env`.\n"
        f"- Environment variable available: `CASEOPS_ENV_FILE={env_file_path}`\n"
        f"- Canonical Salesforce aliases: Production uses `CASEOPS_PRODUCTION_READ_ORG`; Sandbox uses `CASEOPS_SANDBOX_TARGET_ORG`.\n"
        f"- Do not invent generic `ORG`, `PROD_ORG`, or `SANDBOX_ORG` variables unless you assign them from the canonical aliases in the same shell command.\n"
        f"- Do not `source {env_file_relative}` in shell commands. Some values contain spaces and are not shell-safe. CaseOps already exports the needed runtime env vars to this process.\n"
        f"- If a command needs local aliases, assign them from exported vars inline, e.g. `PROD_ORG=\"$CASEOPS_PRODUCTION_READ_ORG\"; SANDBOX_ORG=\"$CASEOPS_SANDBOX_TARGET_ORG\"; ...`.\n\n"
        f"## Salesforce Metadata Workspace\n"
        f"**CRITICAL for clean rollback:** Do not use root-level `temp*`, "
        f"`retrieve*`, `deploy*`, or `metadata*` directories. Use this persistent workspace contract:\n"
        f"- Raw Production retrievals, read-only cache: `${{CASEOPS_METADATA_RAW_PROD_DIR}}/{key}/`\n"
        f"- Issue workspace: `${{CASEOPS_METADATA_WORKSPACES_DIR}}/{key}/`\n"
        f"- Sandbox solution attempts: `${{CASEOPS_METADATA_SANDBOX_WORK_DIR}}/{key}/attempt-001/`, "
        f"`attempt-002/`, etc.\n"
        f"- Confirmed packages: `${{CASEOPS_METADATA_CONFIRMED_DIR}}/{key}/confirmed/support-owned/` or "
        f"`${{CASEOPS_METADATA_CONFIRMED_DIR}}/{key}/confirmed/engineering-proposal/`\n"
        f"- Environment variables available:\n"
        f"  - `CASEOPS_METADATA_ROOT={str(_metadata_workspace_dirs()['root'])}`\n"
        f"  - `CASEOPS_METADATA_CACHE_DIR={str(_metadata_workspace_dirs()['cache_root'])}`\n"
        f"  - `CASEOPS_METADATA_WORKSPACES_DIR={str(_metadata_workspace_dirs()['root'])}`\n"
        f"  - `CASEOPS_METADATA_RAW_PROD_DIR={str(_metadata_workspace_dirs()['raw_prod'])}`\n"
        f"  - `CASEOPS_METADATA_SANDBOX_WORK_DIR={str(_metadata_workspace_dirs()['sandbox_work'])}`\n"
        f"  - `CASEOPS_METADATA_CONFIRMED_DIR={str(_metadata_workspace_dirs()['confirmed'])}`\n"
        f"- Production metadata is read-only reference material. Never edit files under "
        f"`CASEOPS_METADATA_RAW_PROD_DIR`.\n"
        f"- Do not run broad Production retrieves such as `sf project retrieve start --metadata Flow`, "
        f"`--metadata Account`, `--metadata EmailTemplate`, or wildcard folders unless the issue explicitly "
        f"requires every component of that type. First identify the exact component with SOQL, describe/list "
        f"metadata, org-knowledge, or `scripts/sf_caseops_helper.py`, then retrieve only named components "
        f"(for example `--metadata Flow:My_Flow` or `--metadata EmailTemplate:Folder/Template`).\n"
        f"- Every external Salesforce CLI command must be bounded and produce operator-visible progress. "
        f"If a retrieve/query gives no useful output within 90 seconds, stop that approach, print "
        f"`STEP_LOOP {key} command_timeout`, record the command and elapsed time, and replan with a narrower "
        f"SOQL/helper/list-metadata query. Do not repeat the same stalled command.\n"
        f"- Before each Sandbox deploy attempt, retrieve the current Sandbox baseline for every component "
        f"you will change into `attempt-N/baseline-sandbox/`, place candidate metadata in "
        f"`attempt-N/candidate/`, and keep rollback metadata in `attempt-N/revert/`.\n"
        f"- If an attempt is not viable, revert the Sandbox to the captured baseline before starting the "
        f"next attempt, then record the revert command/result in the test report.\n"
        f"- Maintain `${{CASEOPS_METADATA_SANDBOX_WORK_DIR}}/{key}/metadata-workspace.json` with "
        f"attempt number, components touched, baseline path, candidate path, revert status, and confirmed "
        f"package path when applicable.\n"
        f"- Do not use legacy `.temp/metadata` for new work; it is migration-only historical evidence.\n"
        f"- Sub-agents spawned in Steps 5, 6, and 9 must follow this workspace contract "
        f"(see sub-agent-prompts.md).\n\n"
        f"## Instruction\n"
        f"{instruction}\n\n"
        f"## Live Progress Requirement\n"
        f"- Execute the pipeline in this Claude Code process. Do not start background work and say you will be notified later.\n"
        f"- Do not use the Workflow tool, `/workflows`, detached scripts, background agents, background shell jobs, `nohup`, or any runner that returns a task ID instead of streaming current work.\n"
        f"- Sub-agents are allowed only for the specific playbook steps that require them, and only when their result is awaited before continuing to the next pipeline step.\n"
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
        f"   - `sf project retrieve start --metadata Type:Name` or another named/narrow selector (pull targeted metadata)\n"
        f"   - `sf sobject get --sobject [type]` (inspect objects/fields)\n"
        f"2. **Use SOQL queries** via `sf data query` to inspect data, field values, record types, assignments\n"
        f"3. **Never use Playwright, browser automation, frontdoor links, or frontdoor SIDs** for metadata queries, SOQL/API access, field inspection, permission checks, retrieval, deploy, or Apex tests\n"
        f"4. **Only open browser / frontdoor links for:**\n"
        f"   - Visual verification (testing layouts, field placement, visual tests)\n"
        f"   - UI clicks (when automation can't use CLI, e.g., custom buttons, flow runs)\n"
        f"   - Human-readable confirmation\n"
        f"5. If `sf` reports no authenticated orgs, treat that as a CaseOps/container auth configuration blocker. Do **not** test frontdoor SIDs with `curl` and do not conclude Salesforce API is unreachable from frontdoor 401s.\n"
        f"6. **Production is read-only in normal pipeline runs.** Do not run `sf data create`, `sf data update`, `sf data delete`, permission-set assignment commands, Apex anonymous execution, deploys, or any other mutating command against Production. For Support-resolvable Production data/config/permission fixes, document the exact operator action and validation plan only.\n"
        f"\n{_salesforce_browser_prompt_section()}"
        f"## CaseOps Output Files (update these when your task is complete)\n"
        f"You can read and write these files directly for issue {key}:\n"
        f"(Use `{outputs_dir_relative}/` prefix for Docker/persistent output paths)\n"
        f"\n"
        f"| File | Purpose | When to Update |\n"
        f"|------|---------|----------------|\n"
        f"| `{outputs_dir_relative}/investigations/{key}.md` | Investigation record (issue understanding, Salesforce problem, similar items analysis) | After diagnosis, before drafting notes |\n"
        f"| `{outputs_dir_relative}/internal-notes/{key}.md` | Internal notes for operator (root cause, escalation decision, fix notes) | When you've diagnosed the issue |\n"
        f"| `{outputs_dir_relative}/jira-messages/{key}.md` | Customer-facing Jira message (confirmed fix OR engineering escalation) | When ready to respond to customer |\n"
        f"| `{outputs_dir_relative}/test-reports/{key}.md` | Test cases, results, and fix validation | After testing the fix in Sandbox |\n"
        f"| `{outputs_dir_relative}/engineering-escalations/{key}.md` | Engineering handoff (if escalating) | When escalating to Engineering team |\n"
        f"| `{outputs_dir_relative}/generated-files/{key}/` | Issue-specific generated files such as spreadsheets, exports, CSVs, or supporting documents | Whenever a run creates non-markdown files |\n"
        f"\n"
        f"**Update guidance:**\n"
        f"- Read existing files first (if they exist) to preserve prior work\n"
        f"- For any existing output file, use Read followed by Edit. Use Write only when the file does not already exist.\n"
        f"- For daily summaries, write/read `summaries/<YYYY-MM-DD>/issue-summary-<YYYY-MM-DD>.md`; "
        f"for today it is `{_path_relative_for_prompt(_today_issue_summary_path())}`.\n"
        f"- Check if today's summary file exists before writing; if it exists, Read it and Edit it.\n"
        f"- Update them directly (do not ask operator or wait for confirmation)\n"
        f"- Commit your changes with `git add` + `git commit` if substantial updates\n"
        f"- If you cannot complete a task, update the relevant file to document progress and blockers\n"
        f"\n"
        f"## Rules\n"
        f"- Do not ask the user to pick a workflow; the playbook above is the workflow.\n"
        f"- Proceed with the next pipeline steps implied by the playbook and by which files "
        f"already exist for {key} in `{outputs_dir_relative}/`.\n"
        f"- Create or update artifacts in `{outputs_dir_relative}/` that this issue needs (paths as shown above).\n"
        f"- Never save issue-generated spreadsheets, CSVs, PDFs, images, or other supporting files directly in `{outputs_dir_relative}/`; save them under `{outputs_dir_relative}/generated-files/{key}/`.\n"
        f"- If direct evidence confirms a no-deploy Support action such as assigning an existing permission set or making a data/config correction, stop deep investigation, skip Sandbox deploy, write a no-deploy test report, and proceed to internal notes/Jira message. Do **not** execute the Production action; leave it as an operator/admin action unless the operator explicitly starts an approved Production-write workflow.\n"
        f"- Hard stop for permission-set assignment fixes: once an existing permission set is identified as the missing access package, do not run further Apex/class/Flow-access checks unless the issue text or Salesforce error explicitly names Apex/class access as the failure.\n"
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


def _read_similarity_settings(settings: dict[str, str] | None = None) -> dict[str, Any]:
    settings = settings or {}
    include_closed = _env_flag_from_map(
        "CASEOPS_SIMILAR_ISSUES_INCLUDE_CLOSED",
        default=True,
        settings=settings,
    )
    current_user_only = _env_flag_from_map(
        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY",
        default=True,
        settings=settings,
    )
    current_user = (settings.get("CASEOPS_SIMILAR_ISSUES_CURRENT_USER") or "").strip()
    if not current_user:
        current_user = (os.environ.get("CASEOPS_SIMILAR_ISSUES_CURRENT_USER") or "").strip()

    return {
        "enabled": _env_flag_from_map("CASEOPS_SIMILAR_ISSUES_ENABLED", default=True, settings=settings),
        "include_closed": include_closed,
        "current_user_only": current_user_only,
        "current_user": current_user,
        "auto_cluster": _env_flag_from_map("CASEOPS_SIMILAR_ISSUES_AUTO_CLUSTER", default=True, settings=settings),
        "public_safe_summaries": _env_flag_from_map(
            "CASEOPS_SIMILAR_ISSUES_PUBLIC_SAFE_SUMMARIES",
            default=True,
            settings=settings,
        ),
        "candidate_limit": _env_int_from_map(
            "CASEOPS_SIMILAR_ISSUES_CANDIDATE_LIMIT",
            15,
            min_value=1,
            max_value=200,
            settings=settings,
        ),
        "lookback_days": _env_int_from_map(
            "CASEOPS_SIMILAR_ISSUES_LOOKBACK_DAYS",
            180,
            min_value=1,
            max_value=3650,
            settings=settings,
        ),
        "pipeline_context": _env_flag_from_map("CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT", default=False, settings=settings),
        "model_adjudication": _env_flag_from_map("CASEOPS_SIMILAR_ISSUES_MODEL_ADJUDICATION", default=False, settings=settings),
        "delta_mode": _env_flag_from_map("CASEOPS_SIMILAR_ISSUES_DELTA_MODE", default=False, settings=settings),
        "org_aliases": {
            str(settings.get("CASEOPS_PRODUCTION_READ_ORG") or os.environ.get("CASEOPS_PRODUCTION_READ_ORG") or "").strip().lower(),
            str(settings.get("CASEOPS_SANDBOX_TARGET_ORG") or os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip().lower(),
        },
    }


def _rebuild_similarity_clusters_if_enabled(
    *,
    run_key: str,
    manifest_rows: list[dict[str, str]] | None = None,
    settings: dict[str, str] | None = None,
    log_prefix: str | None = None,
    log: Any = None,
) -> dict[str, Any] | None:
    similarity_settings = _read_similarity_settings(settings)
    if not similarity_settings["enabled"]:
        return None

    try:
        return rebuild_issue_clusters(
            outputs_dir=OUTPUTS,
            manifest_rows=manifest_rows,
            include_closed=bool(similarity_settings["include_closed"]),
            current_user_only=bool(similarity_settings["current_user_only"]),
            auto_cluster=bool(similarity_settings["auto_cluster"]),
            candidate_limit=int(similarity_settings["candidate_limit"]),
            lookback_days=int(similarity_settings["lookback_days"]),
            current_user=str(similarity_settings["current_user"]),
            public_safe_summaries=bool(similarity_settings["public_safe_summaries"]),
            org_aliases=set(similarity_settings["org_aliases"]),
            log=(lambda msg: _log_emit_line(run_key, msg)) if log is None else log,
        )
    except Exception as exc:
        message = (
            f"{log_prefix + ': ' if log_prefix else ''}"
            f"similarity cluster rebuild failed: {type(exc).__name__}: {exc}"
        )
        if log is not None:
            log(message)
        else:
            _log_emit_line(run_key, message)
        return None


def _safe_cluster_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _build_similarity_lookup_for_plan(
    key: str,
    *,
    status: str = "",
) -> dict[str, Any]:
    similarity_settings = _read_similarity_settings()
    if not bool(similarity_settings.get("pipeline_context")):
        return {"enabled": False, "lookup_performed": False, "selected_mode": "full_investigation", "lookup_error": ""}

    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
    if not isinstance(cluster_context, dict):
        return {
            "enabled": True,
            "lookup_performed": False,
            "selected_mode": "full_investigation",
            "lookup_error": "cluster context not available",
        }

    cluster_id = _safe_cluster_text(cluster_context.get("cluster_id"))
    if not cluster_id:
        return {
            "enabled": True,
            "lookup_performed": True,
            "cluster_id": "",
            "cluster_state": _safe_cluster_text(cluster_context.get("cluster_state") or "unclustered"),
            "selected_mode": "full_investigation",
            "selected_mode_reason": "No cluster match found.",
            "open_matches": [],
            "closed_matches": [],
            "members": [],
            "canonical_issue": "",
            "classification": "",
            "cluster_type": _safe_cluster_text(cluster_context.get("cluster_type")),
            "summary_url": _safe_cluster_text(cluster_context.get("summary_url")),
            "summary_preview": _safe_cluster_text(cluster_context.get("summary_preview")),
            "safety": {},
            "candidate_count": 0,
            "open_count": 0,
            "closed_count": 0,
        }

    members = cluster_context.get("members") or []
    open_matches = cluster_context.get("open_matches") or []
    closed_matches = cluster_context.get("closed_matches") or []
    normalized = {
        "enabled": True,
        "lookup_performed": True,
        "model_adjudication_enabled": bool(similarity_settings.get("model_adjudication")),
        "delta_mode_enabled": bool(similarity_settings.get("delta_mode")),
        "cluster_id": cluster_id,
        "cluster_state": _safe_cluster_text(cluster_context.get("cluster_state")),
        "canonical_issue": _safe_cluster_text(cluster_context.get("cluster", {}).get("canonical_issue") if isinstance(cluster_context.get("cluster"), dict) else ""),
        "cluster_type": _safe_cluster_text(cluster_context.get("cluster_type")),
        "summary_url": _safe_cluster_text(cluster_context.get("summary_url")),
        "summary_preview": _safe_cluster_text(cluster_context.get("summary_preview")),
        "adjudication": cluster_context.get("adjudication") if isinstance(cluster_context.get("adjudication"), dict) else None,
        "adjudication_packet": cluster_context.get("adjudication_packet") if isinstance(cluster_context.get("adjudication_packet"), dict) else None,
        "members": [],
        "open_matches": [],
        "closed_matches": [],
        "classifications": [],
    }

    for member in members:
        if not isinstance(member, dict):
            continue
        normalized["members"].append({
            "key": _safe_cluster_text(member.get("key")),
            "classification": _safe_cluster_text(member.get("classification")),
            "reasons": list(member.get("reasons") or []) if isinstance(member.get("reasons"), list) else [],
            "relationship": _safe_cluster_text(member.get("relationship")),
            "evidence_terms": list(member.get("evidence_terms") or []) if isinstance(member.get("evidence_terms"), list) else [],
            "status": _safe_cluster_text(member.get("status")),
            "is_open": bool(member.get("is_open")),
            "is_stale": bool(member.get("is_stale")),
            "confidence": member.get("confidence"),
            "adjudication": member.get("adjudication") if isinstance(member.get("adjudication"), dict) else None,
        })
    for member in open_matches:
        if not isinstance(member, dict):
            continue
        normalized["open_matches"].append({
            "key": _safe_cluster_text(member.get("key")),
            "classification": _safe_cluster_text(member.get("classification")),
            "reasons": list(member.get("reasons") or []) if isinstance(member.get("reasons"), list) else [],
            "evidence_terms": list(member.get("evidence_terms") or []) if isinstance(member.get("evidence_terms"), list) else [],
            "status": _safe_cluster_text(member.get("status")),
            "is_stale": bool(member.get("is_stale")),
            "jira_updated": _safe_cluster_text(member.get("jira_updated")),
            "confidence": member.get("confidence"),
            "adjudication": member.get("adjudication") if isinstance(member.get("adjudication"), dict) else None,
        })
    for member in closed_matches:
        if not isinstance(member, dict):
            continue
        normalized["closed_matches"].append({
            "key": _safe_cluster_text(member.get("key")),
            "classification": _safe_cluster_text(member.get("classification")),
            "reasons": list(member.get("reasons") or []) if isinstance(member.get("reasons"), list) else [],
            "evidence_terms": list(member.get("evidence_terms") or []) if isinstance(member.get("evidence_terms"), list) else [],
            "status": _safe_cluster_text(member.get("status")),
            "is_stale": bool(member.get("is_stale")),
            "jira_updated": _safe_cluster_text(member.get("jira_updated")),
            "confidence": member.get("confidence"),
            "adjudication": member.get("adjudication") if isinstance(member.get("adjudication"), dict) else None,
        })

    safety_raw = cluster_context.get("cluster", {}).get("safety") if isinstance(cluster_context.get("cluster"), dict) else {}
    safety = {
        "requires_delta_validation": bool(safety_raw.get("requires_delta_validation") if isinstance(safety_raw, dict) else False),
        "reuse_allowed": bool(safety_raw.get("reuse_allowed") if isinstance(safety_raw, dict) else False),
        "reuse_reason": _safe_cluster_text(safety_raw.get("reuse_reason") if isinstance(safety_raw, dict) else ""),
    }
    normalized["safety"] = safety

    normalized["candidate_count"] = len(normalized["members"])
    normalized["open_count"] = len(normalized["open_matches"])
    normalized["closed_count"] = len(normalized["closed_matches"])

    target = None
    key_lower = key.lower()
    for member in normalized["members"]:
        if member["key"].lower() == key_lower:
            target = member
            break
    classification = _safe_cluster_text(target["classification"] if target else normalized["cluster_type"])
    normalized["classification"] = classification
    if not classification:
        classification = "related_context_only"
    normalized["classifications"] = sorted({member["classification"] for member in normalized["members"] if member.get("classification")})
    normalized["issue_is_stale"] = bool(target["is_stale"]) if target else False

    delta_mode_enabled = bool(similarity_settings.get("delta_mode"))
    selected_mode = "full_investigation"
    if normalized["issue_is_stale"]:
        selected_mode = "manual_review"
        selected_mode_reason = "Related cluster evidence is stale for this issue."
    elif normalized["cluster_id"]:
        if classification == "same_problem_same_fix":
            if safety["reuse_allowed"]:
                selected_mode = "delta_validation" if delta_mode_enabled and safety["requires_delta_validation"] else "cluster_context_full_investigation"
                selected_mode_reason = (
                    "Use delta validation path; reuse is allowed for this cluster but requires issue-level validation."
                    if delta_mode_enabled and safety["requires_delta_validation"]
                    else "Same-problem signal found; run context-aware investigation in full scope."
                )
            else:
                selected_mode = "cluster_context_full_investigation"
                selected_mode_reason = "Same-problem candidate found; reuse safety does not currently allow direct delta reuse."
        elif classification == "same_problem_needs_record_validation":
            if delta_mode_enabled and safety["reuse_allowed"] and safety["requires_delta_validation"]:
                selected_mode = "delta_validation"
                selected_mode_reason = "Same root-cause pattern found; require record/user-level validation."
            else:
                selected_mode = "cluster_context_full_investigation"
                selected_mode_reason = "Same-problem-like signal found, but safe reuse requires additional safety gates."
        elif classification == "same_symptom_different_possible_cause":
            selected_mode = "cluster_context_full_investigation"
            selected_mode_reason = "Same symptom appears, but root cause may differ."
        elif classification == "related_context_only":
            selected_mode = "cluster_context_full_investigation"
            selected_mode_reason = "Related context found; run normal investigation with similarity context."
        elif classification == "unrelated":
            selected_mode = "full_investigation"
            selected_mode_reason = "No usable similar-issue signal for this issue."
        else:
            selected_mode = "cluster_context_full_investigation"
            selected_mode_reason = "Cluster signal present; treat as related context."
    else:
        selected_mode_reason = "No issue cluster assigned; run full investigation."

    normalized["selected_mode"] = selected_mode
    normalized["selected_mode_reason"] = selected_mode_reason
    normalized["adjudication_status"] = (
        "valid"
        if isinstance(normalized.get("adjudication"), dict) and normalized["adjudication"].get("valid")
        else "not_available"
    )
    if normalized["model_adjudication_enabled"] and normalized["adjudication_status"] != "valid":
        normalized["model_adjudication_fallback"] = "No valid persisted adjudication; keep normal/full investigation behavior."
        if selected_mode == "delta_validation":
            normalized["selected_mode"] = "cluster_context_full_investigation"
            normalized["selected_mode_reason"] = "Delta validation blocked because no valid model adjudication is persisted."
    delta_plan = build_delta_validation_plan(
        normalized,
        delta_mode_enabled=delta_mode_enabled,
    )
    normalized["delta_validation"] = delta_plan
    if delta_mode_enabled:
        write_delta_validation_plan(OUTPUTS, issue_key=key, plan=delta_plan)
        if not delta_plan.get("allowed") and normalized["selected_mode"] == "delta_validation":
            normalized["selected_mode"] = delta_plan.get("fallback_mode") or "cluster_context_full_investigation"
            normalized["selected_mode_reason"] = f"Delta validation blocked: {delta_plan.get('reason', 'safety gate failed')}"
    return normalized



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
    internal_only = {"hypothesis"}
    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
    if cluster_context.get("cluster_id"):
        tabs.append({"id": "similar_issues", "label": "Similar Issues"})
    for ftype, rel in FILE_LOCATIONS.items():
        if ftype == "attachments" or ftype in internal_only:
            continue
        path = OUTPUTS / rel.format(key=key)
        if path.exists():
            tabs.append({"id": ftype, "label": FILE_LABELS[ftype]})
    if _generated_files_for_issue(key):
        tabs.append({"id": "generated_files", "label": FILE_LABELS["generated_files"]})
    return tabs


def _generated_files_dir(key: str) -> Path:
    return OUTPUTS / "generated-files" / key


def _generated_files_for_issue(key: str) -> list[Path]:
    root = _generated_files_dir(key)
    if not root.is_dir():
        return []
    files = []
    try:
        for path in root.rglob("*"):
            if path.is_file():
                files.append(path)
    except OSError:
        return []
    return sorted(files, key=lambda p: p.relative_to(root).as_posix().lower())


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


def _summary_root_dir() -> Path:
    return OUTPUTS / _SUMMARY_DIR


def _summary_date_from_filename(name: str) -> str | None:
    match = _DAILY_SUMMARY_FILENAME_RE.match(name)
    if not match:
        return None
    return match.group(1)


def _issue_summary_path_for_date(summary_date: str) -> Path:
    return _summary_root_dir() / summary_date / f"issue-summary-{summary_date}.md"


def _today_issue_summary_path() -> Path:
    return _issue_summary_path_for_date(datetime.now().strftime("%Y-%m-%d"))


def _iter_daily_issue_summary_paths() -> list[Path]:
    root = _summary_root_dir()
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir.name):
            continue
        candidate = date_dir / f"issue-summary-{date_dir.name}.md"
        if candidate.is_file():
            paths.append(candidate)
    return paths


def _iter_legacy_issue_summary_paths() -> list[Path]:
    return sorted(
        (p for p in OUTPUTS.glob("issue-summary-*.md") if _summary_date_from_filename(p.name)),
        key=lambda p: p.name,
    )


def _latest_issue_summary_path() -> Path | None:
    """Return the most recently modified issue summary across legacy and daily locations."""
    candidates = _iter_daily_issue_summary_paths() + _iter_legacy_issue_summary_paths()
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _migrate_legacy_issue_summaries() -> None:
    """Move legacy root-level summaries into the daily summaries directory when possible."""
    for legacy in _iter_legacy_issue_summary_paths():
        summary_date = _summary_date_from_filename(legacy.name)
        if not summary_date:
            continue
        target = _issue_summary_path_for_date(summary_date)
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(target)
            print(f"[OK] Migrated legacy summary: {legacy.name} -> {_path_relative_for_prompt(target)}")
        except OSError as exc:
            print(f"[WARN] Could not migrate legacy summary {legacy}: {exc}")


_ROLLUP_FILENAME = re.compile(r"^(?:summaries/\d{4}-\d{2}-\d{2}/issue-summary-\d{4}-\d{2}-\d{2}\.md|issue-summary-\d{4}-\d{2}-\d{2}\.md)$")


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
    has_test_report = (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists()
    is_jira_escalated = _is_jira_engineering_escalated(status)
    is_jira_escalated_any = _is_jira_escalated_any(status)
    state_payload = _read_pipeline_state(key)
    has_schema = _state_has_schema(state_payload)
    has_data_only_legacy = _test_report_is_data_only(key)
    routing = _infer_routing_state(
        state_payload,
        has_eng_handoff=has_eng_handoff and (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).is_file(),
        has_test_report=has_test_report and (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).is_file(),
    )
    deliverable = _infer_deliverable_state(state_payload, is_data_only_legacy=has_data_only_legacy)
    is_blocked = routing["path"] == "on_hold" or (not has_schema and _investigation_indicates_blocked(key))
    is_data_only = _deliverable_is_data_only(deliverable, legacy_detected=has_data_only_legacy)

    needs_escalation = (
        (has_schema and routing["path"] == "engineering_required")
        or (not has_schema and has_eng_handoff)
    ) and not is_jira_escalated_any

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
        "needs_escalation": needs_escalation,
        "is_jira_escalated": is_jira_escalated,
        "is_jira_escalated_any": is_jira_escalated_any,

        # Pipeline state machine (authoritative status first, file-only fallback)
        "pipeline_state": _calculate_pipeline_state(key, status).value,
        "is_escalation_path": routing["path"] == "engineering_required",  # Source of truth: routing state
        "is_blocked": is_blocked,
        "is_data_only": is_data_only,
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


def _issue_resolution_text(key: str) -> str:
    """Return the issue's resolution artifacts used for derived tags."""
    rels = (
        "test_report",
        "internal_notes",
        "jira_message",
        "investigation",
    )
    parts: list[str] = []
    for rel in rels:
        path = OUTPUTS / FILE_LOCATIONS[rel].format(key=key)
        if not path.is_file():
            continue
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace")[:50000])
        except OSError:
            continue
    return "\n\n".join(parts)


def _text_requires_production_deploy(text: str) -> bool:
    """True when artifacts say a Production metadata/config deploy is required."""
    if not text:
        return False
    patterns = (
        r"(?is)production\s+(?:metadata\s+)?deploy(?:ment)?\s+required[^.\n|:]*[:?|]?\s*\*{0,2}yes\b",
        r"(?is)production\s+(?:metadata\s+)?deploy(?:ment)?\s+required[^.\n]*\bgearset\b",
        r"(?is)\b(?:yes|ready)\s*[-—]\s*gearset\b",
        r"(?is)\bgearset\s+(?:promotion|deploy(?:ment)?)\s+(?:required|needed)\b",
        r"(?is)\bmust\s+(?:be\s+)?(?:promote|promoted|deploy|deployed)\s+(?:from\s+sandbox\s+)?to\s+production\b",
        r"(?is)\bdeploy\s+(?:.+?\s+)?to\s+production\s+via\s+gearset\b",
        r"(?is)\bproduction\s+deployment\s+via\s+gearset\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _text_confirms_no_deploy(text: str) -> bool:
    """True when artifacts explicitly state no deploy/metadata deployment is needed."""
    if not text:
        return False
    patterns = (
        r"(?is)production\s+(?:metadata\s+)?deploy(?:ment)?\s+required[^.\n|:]*[:?|]?\s*\*{0,2}(?:no|n/?a)\b",
        r"(?is)sandbox\s+deploy\s+required[^.\n|:]*[:?|]?\s*\*{0,2}no\b",
        r"(?is)\bno\s+(?:production\s+)?(?:metadata\s+)?deploy(?:ment)?\s+(?:required|needed)\b",
        r"(?is)\bno-deploy\s+(?:rationale|fix|action)\b",
        r"(?is)\bfix\s+type:\s*\*{0,2}(?:data[-\s]?only|data\s+record\s+(?:creation|update)|no-deploy)\b",
        r"(?is)\bdata[-\s]?only\s+fix\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _text_has_data_or_admin_action(text: str) -> bool:
    """True when no-deploy resolution is a data/admin action, not a metadata candidate."""
    patterns = (
        r"(?is)\bdata[-\s]?only\b",
        r"(?is)\bdata\s+(?:record\s+)?(?:update|creation|correction|backfill|remediation|fix)\b",
        r"(?is)\brecord\s+(?:update|creation|correction|backfill|remediation)\b",
        r"(?is)\bpermission\s+set\s+assignment\b",
        r"(?is)\bassign(?:ing)?\s+(?:an?\s+)?(?:existing\s+)?permission\s+set\b",
        r"(?is)\bno-deploy\s+(?:admin|operator|support)\s+action\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _test_report_is_data_only(key: str) -> bool:
    """True when artifacts identify a no-deploy data/admin fix.

    `Data Only` must never appear for issues that require metadata promotion,
    Gearset, or any other Production deployment. Permission-set assignment can
    be no-deploy only when the needed permission set already exists in
    Production and the artifacts explicitly say no deploy is required.
    """
    text = _issue_resolution_text(key)
    if not text:
        return False
    if _text_requires_production_deploy(text):
        return False
    return _text_confirms_no_deploy(text) and _text_has_data_or_admin_action(text)


def _calculate_pipeline_state(key: str, status: str = "") -> PipelineState:
    """Calculate current pipeline state based on schema-driven routing and artifact presence.

    Jira status is the only source of truth for actual Jira escalation.
    CaseOps handoff is derived from durable routing state when available.
    Support-resolvable progression falls back to artifact presence for compatibility.
    """
    has_investigation = (OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)).exists()
    has_internal_notes = (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists()
    has_test_report = (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists()
    has_eng_handoff = (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).exists()
    state_payload = _read_pipeline_state(key)

    if _is_jira_engineering_escalated(status):
        return PipelineState.ESCALATED_TO_ENGINEERING

    if _state_has_schema(state_payload):
        routing = _infer_routing_state(
            state_payload,
            has_eng_handoff=has_eng_handoff and (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).is_file(),
            has_test_report=has_test_report and (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).is_file(),
        )
        if routing["path"] == "engineering_required":
            return PipelineState.ENGINEERING_HANDOFF
        if routing["path"] == "support_resolvable":
            if has_test_report:
                return PipelineState.VALIDATED
            if has_internal_notes:
                return PipelineState.ANALYZED
            if has_investigation:
                return PipelineState.INVESTIGATING
            return PipelineState.UNTRIAGED

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
    """True when outputs/test-reports/<KEY>.md confirms validation or a no-deploy fix."""
    path = OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if re.search(
        r"(?is)(resolution type:\*\*\s*no-deploy|fix type:\*\*\s*(?:data record creation|data-only|no-deploy)|##\s*No-Deploy Rationale|sandbox deploy required:\*\*\s*no|production metadata deploy required\s*[:|]\s*\*\*?no|production deploy required:\s*\*\*?n/?a)",
        text,
    ):
        if re.search(r"(?is)\b(blocked|not viable|not fixed|unresolved|do not proceed)\b", text):
            return False
        return bool(re.search(r"(?is)\bconfirmed\b|\[x\]|production metadata deploy required:\*\*\s*no", text))
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
    if re.search(r"\b(not\s+fixed|false|fail(?:ed|ing)?|unfixed)\b", blob):
        return False
    if re.search(r"\b(yes|pass(?:ed)?|confirmed|resolved)\b", blob):
        return True
    first = block_lines[0].lower().lstrip("-*•").strip()
    return first in ("yes", "y", "true", "✓", "ok")


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


@app.get("/favicon.ico")
def favicon_ico():
    return send_file(ROOT / "static" / "favicon.svg", mimetype="image/svg+xml")


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
    try:
        name = path.relative_to(OUTPUTS).as_posix()
    except ValueError:
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
    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
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
        "similar_issue_cluster": cluster_context,
        **flags,
    })


@app.get("/api/issue/<key>/file/<ftype>")
def api_file(key: str, ftype: str):
    if ftype == "generated_files":
        files = _generated_files_payload(key)
        if not files:
            return jsonify({"html": "<p class='empty'>No generated files for this issue.</p>", "files": []})
        rows = []
        for item in files:
            rows.append(
                "<li>"
                f"<a href=\"{item['url']}\" target=\"_blank\" rel=\"noopener\">{html.escape(item['filename'])}</a>"
                f" <span class=\"muted\">{html.escape(item['size_label'])}</span>"
                "</li>"
            )
        return jsonify({
            "html": "<h2>Generated Files</h2><ul>" + "".join(rows) + "</ul>",
            "files": files,
        })

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


@app.get("/api/issue/<key>/similarity-context")
def api_issue_similarity_context(key: str):
    return jsonify(read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key))


@app.get("/api/issue/<key>/similarity-adjudication-packet")
def api_issue_similarity_adjudication_packet(key: str):
    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
    if not isinstance(cluster_context, dict) or not cluster_context.get("cluster_id"):
        return jsonify({"error": "issue has no similarity cluster"}), 404
    packet = cluster_context.get("adjudication_packet")
    if not isinstance(packet, dict):
        return jsonify({"error": "adjudication packet unavailable"}), 404
    return jsonify(packet)


@app.post("/api/issue/<key>/similarity-adjudication")
def api_issue_similarity_adjudication(key: str):
    data = request.get_json(silent=True) or {}
    model_output = str(data.get("model_output", "")).strip()
    if not model_output:
        return jsonify({"error": "model_output required"}), 400
    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
    if not isinstance(cluster_context, dict) or not cluster_context.get("cluster_id"):
        return jsonify({"error": "issue has no similarity cluster"}), 404
    packet = cluster_context.get("adjudication_packet") if isinstance(cluster_context.get("adjudication_packet"), dict) else {}
    candidate_keys = packet.get("candidate_keys") if isinstance(packet.get("candidate_keys"), list) else []
    result = write_similarity_adjudication(
        outputs_dir=OUTPUTS,
        issue_key=key,
        cluster_id=str(cluster_context.get("cluster_id", "")),
        model_output=model_output,
        candidate_keys=candidate_keys,
    )
    return jsonify(result)


@app.post("/api/issue/<key>/similarity-safety-validation")
def api_issue_similarity_safety_validation(key: str):
    data = request.get_json(silent=True) or {}
    cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
    if not isinstance(cluster_context, dict) or not cluster_context.get("cluster_id"):
        return jsonify({"error": "issue has no similarity cluster"}), 404
    checks = data.get("salesforce_checks")
    if not isinstance(checks, list):
        checks = []
    result = write_cluster_safety_validation(
        OUTPUTS,
        issue_key=key,
        cluster_id=str(cluster_context.get("cluster_id", "")),
        validation_status=str(data.get("validation_status", "")).strip(),
        salesforce_checks=[str(item) for item in checks],
        reuse_reason=str(data.get("reuse_reason", "")).strip(),
    )
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)


@app.post("/api/issue/<key>/similarity-correction")
def api_issue_similarity_correction(key: str):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action", "")).strip()
    if not action:
        return jsonify({"error": "action required"}), 400

    cluster_id = str(data.get("cluster_id", "")).strip()
    reference_issue = str(data.get("reference_issue", "")).strip()
    canonical_issue = str(data.get("canonical_issue", "")).strip()
    reason = str(data.get("reason", "")).strip()

    if not cluster_id:
        cluster_context = read_issue_cluster_context(outputs_dir=OUTPUTS, issue_key=key)
        if isinstance(cluster_context, dict):
            cluster_id = str(cluster_context.get("cluster_id", "")).strip()
    if not cluster_id:
        return jsonify({"error": "issue has no similarity cluster"}), 404

    if action == "make_canonical" and not canonical_issue:
        canonical_issue = key

    result = write_similarity_correction(
        outputs_dir=OUTPUTS,
        issue=key,
        action=action,
        cluster_id=cluster_id,
        reference_issue=reference_issue,
        canonical_issue=canonical_issue,
        reason=reason,
    )

    if not isinstance(result, dict):
        return jsonify({"error": "internal correction error"}), 500

    if result.get("error"):
        return jsonify({"error": result.get("error")}), 400
    return jsonify(result)


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "full")
    key = data.get("key", "")

    is_global = action in ("sync", "full", "reprocess", "sync_new")
    run_key = _GLOBAL_KEY if is_global else key

    env_file = app.config.get("ENV_FILE_PATH", str(ROOT / ".env"))
    use_claude_cli = False
    use_full_issue = False
    use_reprocess_issue = False
    use_force_reprocess_issue = False
    use_global_skill = False
    cmd: list[str] | None = None

    if action == "sync":
        cmd = [
            sys.executable,
            "jira_sync.py",
            "--env-file",
            env_file,
            "--include-existing-active",
            "--out-dir",
            str(OUTPUTS / "jira"),
        ]
    elif action == "sync_new":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file, "--new-only", "--out-dir", str(OUTPUTS / "jira")]
    elif action == "sync_issue" and key:
        cmd = [
            sys.executable,
            "jira_sync.py",
            "--env-file",
            env_file,
            "--issue",
            key,
            "--out-dir",
            str(OUTPUTS / "jira"),
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
    elif action == "force_reprocess_issue" and key:
        use_force_reprocess_issue = True
    elif action == "claude_instruction" and key:
        instruction = data.get("instruction", "").strip()
        if not instruction:
            return jsonify({"error": "No instruction provided."}), 400
        use_claude_cli = True
        prompt = _build_claude_prompt(key, instruction)
    else:
        return jsonify({"error": "unknown action"}), 400

    # Guard against stale callers still trying to run deprecated scripts.
    if cmd is not None:
        if _is_legacy_pipeline_cmd(cmd):
            _log_emit_line(run_key, "ERROR: '/app/run_pipeline.py' is no longer supported. "
                                    "Use the updated sync/pipeline actions.")
            with _state_lock:
                _active_keys.discard(run_key)
            _finish_run_control(run_key)
            return jsonify({
                "error": "Legacy run_pipeline workflow removed. Use sync/reprocess/full actions from UI.",
            }), 400
        _log_emit_line(run_key, f"Resolved run request: action={action} key={key or '<none>'}")

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
    elif use_force_reprocess_issue:
        t = threading.Thread(target=_stream_reprocess_issue, args=(key, run_key, True, True), daemon=True)
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
        run_controls: dict[str, Any] = {}
        for key, control in _active_run_controls.items():
            processes = []
            for item in control.get("processes") or []:
                proc = item.get("process")
                processes.append({
                    "pid": item.get("pid"),
                    "label": item.get("label") or "process",
                    "running": bool(isinstance(proc, subprocess.Popen) and proc.poll() is None),
                })
            run_controls[key] = {
                "stop_requested": bool(control.get("stop_requested")),
                "processes": processes,
            }
        return jsonify({
            "active_keys": list(_active_keys),
            "count": len(_active_keys),
            "run_controls": run_controls,
            "caseops_llm_auth": (
                "api_key" if caseops_llm_auth_uses_anthropic_api_key() else "claude_code"
            ),
            "caseops_llm_backend": (
                "anthropic_messages_api"
                if caseops_llm_auth_uses_anthropic_api_key()
                else "claude_code_cli"
            ),
        })


@app.post("/api/run/stop")
def api_run_stop():
    data = request.get_json(silent=True) or {}
    requested_key = (data.get("key") or data.get("run_key") or "").strip()
    stop_all = bool(data.get("all"))

    with _state_lock:
        active_keys = list(_active_keys)

    if requested_key and requested_key != "*":
        targets = [requested_key]
    elif stop_all or requested_key == "*" or not requested_key:
        targets = active_keys
    else:
        return jsonify({
            "error": "key required when zero or multiple runs are active",
            "active_keys": active_keys,
        }), 400

    if not targets:
        return jsonify({"ok": True, "stopped": [], "active_keys": active_keys})

    stopped = [_request_stop_for_run(key) for key in targets]
    return jsonify({"ok": True, "stopped": stopped, "active_keys": active_keys})


@app.post("/api/pipeline-state/repair")
def api_pipeline_state_repair():
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or data.get("run_key") or "").strip()
    if not key:
        return jsonify({"error": "key required"}), 400

    with _state_lock:
        if key in _active_keys:
            return jsonify({"error": f"{key} is currently running; stop it before repairing state."}), 409

    row = _find_manifest_row(key)
    plan = _build_pipeline_resume_plan(
        key,
        row.get("Status", ""),
        row.get("Updated", ""),
        rebuild_from_artifacts=True,
    )
    plan["repair"] = {
        "rebuilt_from_artifacts": True,
        "rebuilt_at": datetime.now(timezone.utc).isoformat(),
        "previous_state_ignored": True,
    }
    plan_path = _write_pipeline_resume_plan(plan)
    _invalidate_jira_summary_cache(key)
    investigation_cache.pop(key, None)
    manifest_changed([key])
    next_step = plan.get("next_step") or {}
    return jsonify({
        "ok": True,
        "key": key,
        "plan_path": _path_relative_for_prompt(plan_path),
        "next_step": next_step,
        "quality_gates": plan.get("quality_gates") or {},
        "steps": [
            {
                "step": step.get("step"),
                "name": step.get("name"),
                "status": step.get("status"),
                "reason": step.get("reason"),
            }
            for step in (plan.get("steps") or [])
        ],
    })


@app.get("/health")
def health():
    return jsonify({"ok": True})


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
    """Remove one pipeline log file (JSON body: {\"key\": \"ISSUE-1\"} or __global__)."""
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


def _format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _generated_files_payload(key: str) -> list[dict[str, Any]]:
    root = _generated_files_dir(key)
    result = []
    for path in _generated_files_for_issue(key):
        try:
            stat = path.stat()
            rel = path.relative_to(root).as_posix()
        except OSError:
            continue
        mime_type, _encoding = mimetypes.guess_type(path.name)
        result.append({
            "filename": path.name,
            "path": rel,
            "mimeType": mime_type or "application/octet-stream",
            "size": stat.st_size,
            "size_label": _format_file_size(stat.st_size),
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "url": f"/files/generated/{key}/{urllib.parse.quote(rel)}",
        })
    return result


@app.get("/api/issue/<key>/generated-files")
def api_generated_files(key: str):
    return jsonify(_generated_files_payload(key))


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
        return jsonify({"ok": True, "id": result.get("id", ""), "sync": _issue_sync_result(key)})
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return jsonify({"error": f"Jira {exc.code}: {details[:300]}"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/issue/<key>/transitions")
def api_issue_transitions(key: str):
    _load_jira_env(Path(app.config.get("ENV_FILE_PATH", ROOT / ".env")))  # Use instance-specific .env
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

    _load_jira_env(Path(app.config.get("ENV_FILE_PATH", ROOT / ".env")))  # Use instance-specific .env
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

    return jsonify({"ok": True, "new_status": new_status, "sync": _issue_sync_result(key)})


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

        return jsonify({"ok": True, "id": result.get("id", ""), "sync": _issue_sync_result(key)})
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


@app.get("/files/generated/<key>/<path:filename>")
def serve_generated_file(key: str, filename: str):
    root = _generated_files_dir(key).resolve()
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return jsonify({"error": "forbidden"}), 403
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path, as_attachment=True)


@app.get("/files/issue-clusters/<path:filename>")
def serve_issue_cluster_file(filename: str):
    if not re.fullmatch(r"[a-z0-9._-]+\.md", str(filename).lower()):
        return jsonify({"error": "invalid"}), 400

    root = (OUTPUTS / "issue-clusters").resolve()
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return jsonify({"error": "forbidden"}), 403
    if not path.is_file():
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
    """Return Salesforce org identifiers from .env for URL construction."""
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
    """Return current settings from .env with secrets masked."""
    env_file_path = app.config.get("ENV_FILE_PATH")
    settings = _read_env_file(Path(env_file_path) if env_file_path else None)

    # Settings to expose in UI
    exposed_keys = {
        "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
        "CASEOPS_LLM_AUTH", "CASEOPS_ANTHROPIC_MODEL",
        "CASEOPS_GLOBAL_MAX_PARALLEL",
        "CASEOPS_GLOBAL_MAX_QUEUE_PASSES",
        "CASEOPS_ENABLE_PARALLEL_PRECHECKS",
        "CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES",
        "CASEOPS_SIMILAR_ISSUES_ENABLED",
        "CASEOPS_SIMILAR_ISSUES_INCLUDE_CLOSED",
        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY",
        "CASEOPS_SIMILAR_ISSUES_AUTO_CLUSTER",
        "CASEOPS_SIMILAR_ISSUES_PUBLIC_SAFE_SUMMARIES",
        "CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT",
        "CASEOPS_SIMILAR_ISSUES_MODEL_ADJUDICATION",
        "CASEOPS_SIMILAR_ISSUES_DELTA_MODE",
        "CASEOPS_SIMILAR_ISSUES_CANDIDATE_LIMIT",
        "CASEOPS_SIMILAR_ISSUES_LOOKBACK_DAYS",
        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER",
        "CASEOPS_AUTO_SYNC_ENABLED",
        "CASEOPS_AUTO_SYNC_INTERVAL_MINUTES",
        "CASEOPS_FLASK_DEBUG",
        "CASEOPS_CLAUDE_IDLE_TIMEOUT_SECONDS",
        "CASEOPS_CLAUDE_TOTAL_TIMEOUT_SECONDS",
        "CASEOPS_PRODUCTION_READ_ORG", "CASEOPS_SANDBOX_TARGET_ORG",
        "CASEOPS_PRODUCTION_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL",
    }
    defaults = {
        "CASEOPS_GLOBAL_MAX_PARALLEL": "1",
        "CASEOPS_GLOBAL_MAX_QUEUE_PASSES": "12",
        "CASEOPS_ENABLE_PARALLEL_PRECHECKS": "false",
        "CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES": "false",
        "CASEOPS_SIMILAR_ISSUES_ENABLED": "true",
        "CASEOPS_SIMILAR_ISSUES_INCLUDE_CLOSED": "true",
        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY": "true",
        "CASEOPS_SIMILAR_ISSUES_AUTO_CLUSTER": "true",
        "CASEOPS_SIMILAR_ISSUES_PUBLIC_SAFE_SUMMARIES": "true",
        "CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT": "false",
        "CASEOPS_SIMILAR_ISSUES_MODEL_ADJUDICATION": "false",
        "CASEOPS_SIMILAR_ISSUES_DELTA_MODE": "false",
        "CASEOPS_SIMILAR_ISSUES_CANDIDATE_LIMIT": "15",
        "CASEOPS_SIMILAR_ISSUES_LOOKBACK_DAYS": "180",
        "CASEOPS_SIMILAR_ISSUES_CURRENT_USER": "",
        "CASEOPS_AUTO_SYNC_ENABLED": "false",
        "CASEOPS_AUTO_SYNC_INTERVAL_MINUTES": "0",
        "CASEOPS_FLASK_DEBUG": "false",
        "CASEOPS_CLAUDE_IDLE_TIMEOUT_SECONDS": "240",
        "CASEOPS_CLAUDE_TOTAL_TIMEOUT_SECONDS": "1200",
    }

    response = {}
    for key in exposed_keys:
        value = settings.get(key, defaults.get(key, ""))
        # Mask secrets (but not URLs, aliases, or boolean flags)
        if key in ("JIRA_API_TOKEN",):
            response[key] = _mask_secret(value)
        else:
            response[key] = value

    return jsonify(response)


@app.route("/api/settings", methods=["POST"])
def api_post_settings():
    """Save settings to .env. Preserves masked values (doesn't overwrite)."""
    body = request.get_json(silent=True) or {}

    # Filter and validate (CASEOPS_LLM_AUTH is read-only, set via .env only)
    updates = {}
    for key in ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
                "CASEOPS_ANTHROPIC_MODEL",
                "CASEOPS_GLOBAL_MAX_PARALLEL",
                "CASEOPS_GLOBAL_MAX_QUEUE_PASSES",
                "CASEOPS_ENABLE_PARALLEL_PRECHECKS",
                "CASEOPS_ENABLE_PARALLEL_EVIDENCE_BRANCHES",
                "CASEOPS_SIMILAR_ISSUES_ENABLED",
                "CASEOPS_SIMILAR_ISSUES_INCLUDE_CLOSED",
                "CASEOPS_SIMILAR_ISSUES_CURRENT_USER_ONLY",
                "CASEOPS_SIMILAR_ISSUES_AUTO_CLUSTER",
                "CASEOPS_SIMILAR_ISSUES_PUBLIC_SAFE_SUMMARIES",
                "CASEOPS_SIMILAR_ISSUES_PIPELINE_CONTEXT",
                "CASEOPS_SIMILAR_ISSUES_MODEL_ADJUDICATION",
                "CASEOPS_SIMILAR_ISSUES_DELTA_MODE",
                "CASEOPS_SIMILAR_ISSUES_CANDIDATE_LIMIT",
                "CASEOPS_SIMILAR_ISSUES_LOOKBACK_DAYS",
                "CASEOPS_SIMILAR_ISSUES_CURRENT_USER",
                "CASEOPS_AUTO_SYNC_ENABLED",
                "CASEOPS_AUTO_SYNC_INTERVAL_MINUTES",
                "CASEOPS_FLASK_DEBUG",
                "CASEOPS_CLAUDE_IDLE_TIMEOUT_SECONDS",
                "CASEOPS_CLAUDE_TOTAL_TIMEOUT_SECONDS",
                "CASEOPS_PRODUCTION_READ_ORG", "CASEOPS_SANDBOX_TARGET_ORG",
                "CASEOPS_PRODUCTION_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL"]:
        if key not in body:
            continue
        value = str(body.get(key, "")).strip()
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
        path = str(messages_file.resolve())
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
        "caseops": {
            "version": CASEOPS_VERSION,
        },
        "paths": {
            "outputs_dir": str(OUTPUTS),
            "instance_dir": str(OUTPUTS.parent),
            "env_file": str(env_file_path) if env_file_path else "",
            "canned_messages_file": str(_persistent_canned_messages_file()),
        },
        "claude": {
            "installed": bool(shutil.which("claude")),
            "authenticated": False,
            "token_configured": bool((os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip()),
        },
        "sf_installed": bool(shutil.which("sf")),
        "sf_prod": {"authenticated": False, "alias": prod_alias},
        "sf_sandbox": {"authenticated": False, "alias": sand_alias},
    }


def _build_settings_status() -> dict[str, Any]:
    """Run the full Settings status probe. This may take several seconds."""
    status = _settings_status_skeleton()
    env_file_path = app.config.get("ENV_FILE_PATH")
    settings = _read_env_file(Path(env_file_path) if env_file_path else None)
    prod_alias = _env_first("CASEOPS_PRODUCTION_READ_ORG", settings=settings)
    sand_alias = _env_first("CASEOPS_SANDBOX_TARGET_ORG", settings=settings)

    # Ground truth check for auth/runtime: same path used by pipeline preflight.
    try:
        runtime_preflight = _collect_runtime_preflight(run_soql=False)
        status["runtime_preflight"] = runtime_preflight
        status["sf_installed"] = bool(runtime_preflight.get("sf", {}).get("installed", False))
        status["sf_prod"].update({
            "alias": (runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("alias", prod_alias),
            "authenticated": bool((runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("authenticated", False)),
            "username": (runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("username", ""),
            "orgId": (runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("orgId", ""),
            "instanceUrl": (runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("instanceUrl", ""),
            "connectedStatus": (runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("connectedStatus", ""),
            "soql_ok": bool((runtime_preflight.get("sf", {}).get("prod", {}) or {}).get("soql_ok", False)),
        })
        status["sf_sandbox"].update({
            "alias": (runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("alias", sand_alias),
            "authenticated": bool((runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("authenticated", False)),
            "username": (runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("username", ""),
            "orgId": (runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("orgId", ""),
            "instanceUrl": (runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("instanceUrl", ""),
            "connectedStatus": (runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("connectedStatus", ""),
            "soql_ok": bool((runtime_preflight.get("sf", {}).get("sandbox", {}) or {}).get("soql_ok", False)),
        })
        if caseops_llm_auth_uses_anthropic_api_key():
            status["claude"] = {
                "installed": bool(runtime_preflight.get("caseops_llm_auth") == "api_key"),
                "authenticated": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
                "token_configured": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
            }
        else:
            claude_preflight = runtime_preflight.get("claude", {})
            status["claude"].update({
                "installed": bool(claude_preflight.get("installed", False)),
                "authenticated": bool(claude_preflight.get("authenticated", False)),
                "token_configured": bool(claude_preflight.get("token_configured", False)),
                "version": str(claude_preflight.get("version", "") or "").strip(),
                "auth_status": claude_preflight.get("auth_status"),
                "ok": bool(claude_preflight.get("ok", False)),
            })
            if claude_preflight.get("auth_status"):
                status["claude"]["auth_status"] = claude_preflight.get("auth_status")
            if claude_preflight.get("version_warning"):
                status["claude"]["version_warning"] = claude_preflight["version_warning"]
            if claude_preflight.get("auth_error"):
                status["claude"]["auth_error"] = claude_preflight["auth_error"]
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
        env_file = Path(env_file_path) if env_file_path else ROOT / ".env"
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
        prod_token = _normalize_salesforce_access_token(_env_first("SF_PROD_ACCESS_TOKEN", settings=settings))
        prod_url = _env_first("SF_PROD_INSTANCE_URL", "CASEOPS_PRODUCTION_INSTANCE_URL", settings=settings)
        prod_sfdx_auth_url = _extract_salesforce_sfdx_auth_url(
            _env_first("SF_PROD_SFDX_AUTH_URL", "CASEOPS_PRODUCTION_SFDX_AUTH_URL", settings=settings)
        )
        sandbox_token = _normalize_salesforce_access_token(_env_first("SF_SANDBOX_ACCESS_TOKEN", settings=settings))
        sandbox_url = _env_first("SF_SANDBOX_INSTANCE_URL", "CASEOPS_SANDBOX_INSTANCE_URL", settings=settings)
        sandbox_sfdx_auth_url = _extract_salesforce_sfdx_auth_url(
            _env_first("SF_SANDBOX_SFDX_AUTH_URL", "CASEOPS_SANDBOX_SFDX_AUTH_URL", settings=settings)
        )

        if not any([prod_token, sandbox_token, prod_sfdx_auth_url, sandbox_sfdx_auth_url]):
            return jsonify({"error": "No SF auth values in environment (paste access token JSON or SFDX auth URL JSON first)"}), 400

        # Auth both orgs
        def auth_org(alias: str, token: str, url: str, sfdx_auth_url: str) -> tuple[bool, str]:
            """Authenticate one org. Returns (success, message)."""
            if not alias:
                return False, "missing org alias (CASEOPS_PRODUCTION_READ_ORG or CASEOPS_SANDBOX_TARGET_ORG)"
            env = os.environ.copy()
            env["HOME"] = _safe_runtime_home().as_posix()
            if sfdx_auth_url:
                proc = _sf_auth_from_sfdx_auth_url(
                    sf_bin=shutil.which("sf") or "sf",
                    alias=alias,
                    sfdx_auth_url=sfdx_auth_url,
                    env=env,
                )
                if proc.returncode == 0:
                    return True, "authenticated from SFDX auth URL"
                if not token:
                    return False, _command_error(proc)

            if not token or not url:
                return False, "missing token/url or SFDX auth URL"
            try:
                env["SF_ACCESS_TOKEN"] = token
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
        prod_ok, prod_msg = auth_org(prod_alias, prod_token, prod_url, prod_sfdx_auth_url) if (prod_token or prod_sfdx_auth_url) else (None, "skipped")
        sandbox_ok, sandbox_msg = auth_org(sandbox_alias, sandbox_token, sandbox_url, sandbox_sfdx_auth_url) if (sandbox_token or sandbox_sfdx_auth_url) else (None, "skipped")

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
                    env={**os.environ, "HOME": _safe_runtime_home().as_posix()},
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


@app.post("/api/setup/refresh-salesforce-tokens")
def api_refresh_salesforce_tokens():
    """Update SF tokens (access + optional refresh) and set refresh timestamp in .env."""
    try:
        body = request.get_json(silent=True) or {}
        prod_token = _normalize_salesforce_access_token(body.get("sf_prod_access_token"))
        sandbox_token = _normalize_salesforce_access_token(body.get("sf_sandbox_access_token"))
        prod_sfdx_auth_url = _extract_salesforce_sfdx_auth_url(body.get("sf_prod_refresh_token"))
        sandbox_sfdx_auth_url = _extract_salesforce_sfdx_auth_url(body.get("sf_sandbox_refresh_token"))
        prod_refresh_token = _extract_salesforce_refresh_token(body.get("sf_prod_refresh_token"))
        sandbox_refresh_token = _extract_salesforce_refresh_token(body.get("sf_sandbox_refresh_token"))

        if not any([prod_token, sandbox_token, prod_sfdx_auth_url, sandbox_sfdx_auth_url]):
            return jsonify({"error": "Paste at least one Salesforce access-token JSON value or SFDX auth URL JSON value"}), 400

        env_file = os.environ.get("CASEOPS_ENV_FILE") or app.config.get("ENV_FILE_PATH")
        if not env_file:
            return jsonify({"error": "CASEOPS_ENV_FILE not set"}), 500

        env_path = Path(env_file)
        env_content = env_path.read_text(encoding="utf-8")

        # Remove old token lines, keep everything else
        lines = env_content.split("\n")
        new_lines = [l for l in lines if not l.startswith((
            "SF_PROD_ACCESS_TOKEN=", "SF_SANDBOX_ACCESS_TOKEN=", "SF_TOKENS_REFRESHED_AT=",
            "SF_PROD_REFRESH_TOKEN=", "SF_SANDBOX_REFRESH_TOKEN=",
            "SF_PROD_SFDX_AUTH_URL=", "SF_SANDBOX_SFDX_AUTH_URL="
        ))]

        # Add new tokens and timestamp
        if prod_token:
            new_lines.append(f"SF_PROD_ACCESS_TOKEN={prod_token}")
        if sandbox_token:
            new_lines.append(f"SF_SANDBOX_ACCESS_TOKEN={sandbox_token}")
        if prod_sfdx_auth_url:
            new_lines.append(f"SF_PROD_SFDX_AUTH_URL={prod_sfdx_auth_url}")
        if sandbox_sfdx_auth_url:
            new_lines.append(f"SF_SANDBOX_SFDX_AUTH_URL={sandbox_sfdx_auth_url}")
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
        help="Workspace name for output isolation. Env config is always read from .env unless --env-file or CASEOPS_ENV_FILE is set.",
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
        help="Path to .env file (default: .env)",
    )
    _args = parser.parse_args()

    WORKSPACE = _args.workspace
    data_dir = (os.environ.get("CASEOPS_DATA_DIR") or "").strip()
    if _args.outputs_dir:
        OUTPUTS = Path(_args.outputs_dir)
    elif os.environ.get("CASEOPS_OUTPUTS_DIR"):
        OUTPUTS = Path(os.environ["CASEOPS_OUTPUTS_DIR"])
    elif data_dir:
        OUTPUTS = Path(data_dir) / "outputs"
    else:
        OUTPUTS = ROOT / "outputs" / WORKSPACE if WORKSPACE != "default" else ROOT / "outputs"
    _ensure_directory_writable(OUTPUTS, "outputs")

    env_override = (
        os.environ.get("CASEOPS_ENV_FILE")
        # 2026-06-06 compatibility alias; remove after deployments have moved to CASEOPS_ENV_FILE.
        or os.environ.get("CASEOPS_JIRA_ENV_FILE")
        or ""
    ).strip()
    if _args.env_file:
        env_file_path = Path(_args.env_file)
        _load_jira_env(env_file_path)
    elif env_override:
        env_file_path = Path(env_override)
        _load_jira_env(env_file_path)
    else:
        env_file_path = ROOT / ".env"
        _load_jira_env(env_file_path)

    os.environ["CASEOPS_ENV_FILE"] = str(env_file_path)
    # 2026-06-06 compatibility alias; remove after deployments have moved to CASEOPS_ENV_FILE.
    os.environ["CASEOPS_JIRA_ENV_FILE"] = str(env_file_path)

    # Initialize instance-specific runtime and metadata workspaces.
    temp_override = (os.environ.get("CASEOPS_TEMP_DIR") or "").strip()
    globals()["TEMP_ROOT"] = Path(temp_override) if temp_override else OUTPUTS.parent / ".temp"
    _ensure_directory_writable(TEMP_ROOT, ".temp root")
    _ensure_directory_writable(TEMP_ROOT / "claude-code", "Claude Code temp")
    _ensure_metadata_workspace_dirs()

    # Initialize instance-specific pipeline logs directory
    globals()["OUTPUTS_PIPELINE_LOGS"] = OUTPUTS / "pipeline-logs"

    # Pre-create all pipeline output subdirectories so Claude Code doesn't need write permissions to create them
    for subdir in [
        "jira", "investigations", "internal-notes", "jira-messages", "test-reports",
        "engineering-escalations", "hypothesis", "pipeline-logs", "pipeline-state",
        "issue-clusters",
        "closed-resolved", "generated-files", "org-knowledge", "metadata-cache", "metadata-workspaces", "summaries"
    ]:
        _ensure_directory_writable(OUTPUTS / subdir, f"outputs/{subdir}")
    _ensure_org_knowledge_defaults()
    _migrate_legacy_issue_summaries()

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

    # Validate .env file exists and is readable
    if not env_file_path.exists():
        legacy_env = env_file_path.parent / (".env" + ".jira")
        migration_hint = ""
        if env_file_path.name == ".env" and legacy_env.exists():
            migration_hint = (
                f"\nUpgrade note: CaseOps now uses `.env` as the single env file. "
                f"Rename `{legacy_env.name}` to `.env`, or start with `--env-file` for a custom path."
            )
        raise RuntimeError(f".env file does not exist: {env_file_path}{migration_hint}")
    if not env_file_path.is_file():
        raise RuntimeError(f".env is not a file: {env_file_path}")

    try:
        env_file_path.read_text(encoding="utf-8")
        print(f"[OK] .env file is readable")
    except Exception as e:
        raise RuntimeError(f".env file is not readable: {env_file_path}\nError: {e}") from e

    # Validate all required subdirectories exist
    required_subdirs = [
        "jira", "investigations", "internal-notes", "jira-messages", "test-reports",
        "engineering-escalations", "hypothesis", "pipeline-logs", "pipeline-state",
        "issue-clusters",
        "closed-resolved", "generated-files", "org-knowledge", "metadata-cache", "metadata-workspaces",
        _SUMMARY_DIR
    ]
    for subdir in required_subdirs:
        subdir_path = OUTPUTS / subdir
        if not subdir_path.exists():
            raise RuntimeError(f"Required subdirectory missing: {subdir_path}")
        if not subdir_path.is_dir():
            raise RuntimeError(f"Subdirectory is not a directory: {subdir_path}")
    print(f"[OK] All required subdirectories exist ({len(required_subdirs)} dirs)")

    _rebuild_similarity_clusters_if_enabled(
        run_key="startup",
        manifest_rows=_read_manifest(),
        log=lambda msg: None,
    )

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
    print(f"  - CASEOPS_ENV_FILE={env_file_path}")
    print(f"  - CASEOPS_WORKSPACE={WORKSPACE}")
    metadata_dirs = _metadata_workspace_dirs()
    print(f"  - CASEOPS_TEMP_DIR={TEMP_ROOT}")
    print(f"  - CASEOPS_METADATA_ROOT={metadata_dirs['root']}")
    print(f"  - CASEOPS_METADATA_CACHE_DIR={metadata_dirs['cache_root']}")
    print(f"  - CASEOPS_METADATA_WORKSPACES_DIR={metadata_dirs['root']}")
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

    # Initialize skill registry (loads all skills once at startup).
    # skills/ is the only canonical CaseOps skill source.
    # Claude runtime state and must not influence app behavior.
    print(f"Initializing skill registry...")
    skill_registry.load_all_skills(ROOT / "skills")
    print(f"[OK] Skill registry loaded: {skill_registry.skill_count()} skills")
    print(f"     Skills: {', '.join(skill_registry.list_skills())}\n")

    # Register skill paths (pass to subprocesses via env vars)
    print(f"Registering skill paths for subprocess environment...")
    skill_dir = ROOT / "skills"
    if skill_dir.exists():
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
        print("[WARN] Claude Code OAuth token not configured - open Settings > Claude")

    # Check Salesforce tokens and auto-refresh if needed (8h TTL, auto-refresh at 4h)
    _check_and_refresh_salesforce_tokens(env_file_path)

    print(f"[OK] Temp directory: {TEMP_ROOT}")
    print(f"[OK] Metadata workspace: {_metadata_workspace_dirs()['root']}")
    print(f"[OK] Metadata cache: {_metadata_workspace_dirs()['cache_root']}")

    # use_reloader=False prevents the dev reloader from killing SSE streams
    app.run(
        debug=_env_flag("CASEOPS_FLASK_DEBUG", False),
        threaded=True,
        host="0.0.0.0",
        port=_args.port,
        use_reloader=False,
    )
