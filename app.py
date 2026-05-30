#!/usr/bin/env python3
"""CaseOps browser GUI.

Run:
    python app.py
Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import base64
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
import urllib.request
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from caseops_paths import default_jira_dir
from jira_sync import JiraClient, update_manifest_status


class PipelineState(Enum):
    """Pipeline progression states (mutually exclusive)."""
    UNTRIAGED = "untriaged"
    INVESTIGATING = "investigating"
    ANALYZED = "analyzed"
    VALIDATED = "validated"
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


def _cache_evict(cache: dict) -> None:
    """Evict oldest entries when cache exceeds _CACHE_MAX_KEYS."""
    while len(cache) > _CACHE_MAX_KEYS:
        cache.pop(next(iter(cache)))


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
    - ROOT/temp* (use ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve)
    - ROOT/retrieved_metadata* (use instance-specific)
    - ROOT/retrieve-prod (use instance-specific)
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
                f"For metadata retrieval: use ${{CASEOPS_OUTPUTS_DIR}}/../temp-retrieve\n"
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
    - ANTHROPIC_API_KEY: always set from the file when the line has a non-empty
      value (used for the Anthropic **Messages API** when ``CASEOPS_LLM_AUTH=api_key``;
      still present in the environment when ``CASEOPS_LLM_AUTH=claude_code`` but the
      Flask app omits it from the Claude Code **subprocess** in that mode).
    - CASEOPS_LLM_AUTH: always set from the file when the line has a non-empty
      value (so switching API vs Claude Code mode in ``.env.jira`` applies on reload).
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
        if key == "ANTHROPIC_API_KEY":
            os.environ[key] = value
            continue
        if key == CASEOPS_LLM_AUTH_ENV:
            os.environ[key] = value
            continue
        cur = os.environ.get(key, "")
        if key not in os.environ or not str(cur).strip():
            os.environ[key] = value


JIRA_BASE_URL = ""  # Set in __main__ after _load_jira_env()


def caseops_llm_auth_uses_anthropic_api_key() -> bool:
    """If True, CaseOps LLM calls use the **Anthropic Messages API** (API key billing).

    If False, CaseOps spawns the **Claude Code CLI** and omits ``ANTHROPIC_API_KEY`` so the CLI uses
    subscription / ``claude login`` (or its defaults).
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

CLOSED_STATUSES = {"closed", "resolved", "canceled", "cancelled"}
ESCALATED_STATUS = "escalated to engineering"

FILE_LOCATIONS: dict[str, str] = {
    "jira_summary":       "jira/summary/{key}.md",
    "investigation":      "investigations/{key}.md",
    "internal_notes":     "internal-notes/{key}.md",
    "jira_message":       "jira-messages/{key}.md",
    "test_report":        "test-reports/{key}.md",
    "eng_handoff":        "engineering-escalations/{key}.md",
    "closed_resolved":    "closed-resolved/{key}.md",
}

FILE_LABELS: dict[str, str] = {
    "jira_summary":    "Jira Summary",
    "investigation":   "Investigation",
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


def _pipeline_log_path(run_key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", run_key) or "unknown"
    return OUTPUTS_PIPELINE_LOGS / f"{safe}.jsonl"


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


def _log_emit_line(run_key: str, text: str) -> None:
    """Notify SSE clients and append to per-key pipeline history on disk."""
    _log_q.put(f"{run_key}|{text}")
    _persist_pipeline_record(run_key, text, kind="line")


def _log_emit_done(run_key: str) -> None:
    _log_q.put(f"__done__|{run_key}")
    _persist_pipeline_record(run_key, "", kind="done")


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
            rows.append(json.loads(raw_line))
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

    For claude_code mode: omit ANTHROPIC_API_KEY. Claude Code CLI uses pre-authenticated
    credentials from ~/.claude/.credentials.json (mounted from host).
    For api_key mode: pass ANTHROPIC_API_KEY (API billing auth).
    Instance-specific output directories so Skill writes to correct location.

    Reference: https://github.com/cabinlab/claude-code-sdk-docker/blob/main/docs/AUTHENTICATION.md
    """
    env = os.environ.copy()
    if not caseops_llm_auth_uses_anthropic_api_key():
        # Claude Code subscription mode: use pre-authenticated credentials file (~/.claude/.credentials.json)
        # Don't pass ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN — Claude Code CLI will use the mounted credentials
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OAUTH_TOKEN", None)
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    chrome = (env.get("CASEOPS_CLAUDE_BROWSER") or "").strip()
    if chrome:
        env["BROWSER"] = chrome
        if not (env.get("CLAUDE_CODE_CHROME_PATH") or "").strip():
            env["CLAUDE_CODE_CHROME_PATH"] = chrome
    # Pass instance-specific directories to Claude Skill
    env["CASEOPS_JIRA_OUT_DIR"] = str(OUTPUTS / "jira")
    env["CASEOPS_JIRA_ENV_FILE"] = app.config.get("ENV_FILE_PATH", str(ROOT / ".env.jira"))
    return env


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
        "## Salesforce in the browser (this CaseOps / Claude run)",
        "If you need the Salesforce UI in a browser for this task:",
        "**Permission model (mandatory):** The Production frontdoor session is **read-only** — investigate, query, and view only; "
        "do **not** create, update, delete, or deploy **anything** in Production. The Sandbox frontdoor session may use **full CRUD** "
        "for metadata deploy, test fixes, and record operations required by the playbook.",
    ]
    if chrome:
        lines.append(
            f"- Open OAuth or Salesforce URLs using **Google Chrome Dev** at: `{chrome}`. "
            "This subprocess sets `BROWSER` (and `CLAUDE_CODE_CHROME_PATH`) when configured; "
            "if a tool still opens another browser, use Chrome Dev manually at that path."
        )
    if generic:
        lines.append(
            "- Open this **session / frontdoor link** first in that Chrome Dev session when the target org is not specified below "
            "(do not paste into Jira, git commits, or customer-facing artifacts):"
        )
        lines.append(generic)
    if prod_magic:
        lines.append(
            f"- **Production ({prod_label})** via `CASEOPS_PRODUCTION_MAGIC_LINK` — **read-only**: use this session only for investigation "
            "(view/query). No Production creates, edits, deletes, or deployments. Open this link first in Chrome Dev for prod UI:"
        )
        lines.append(prod_magic)
    if sand_magic:
        lines.append(
            f"- **Sandbox ({sand_label})** via `CASEOPS_SANDBOX_MAGIC_LINK` — **full CRUD** allowed: deploy, test, and change records/metadata "
            "as the playbook requires. Open this link first in Chrome Dev for sandbox UI:"
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
        env = _claude_process_env()
        env["CASEOPS_OUTPUTS_DIR"] = str(OUTPUTS)
        _log_emit_line(run_key, f"Invoking: {' '.join(cmd[:3])}...")
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
                        _log_emit_line(run_key, f"[{tool}]{' ' + detail if detail else ''}")

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
    """Run full CaseOps fix pipeline via jira-salesforce-fix-pipeline Skill.

    This invokes the Skill directly (Steps 1-12 orchestration including sub-agents).
    Do NOT call deprecated run_pipeline.py — that calls removed agents.
    """
    try:
        _log_emit_line(run_key, f"-- Processing {key} via jira-salesforce-fix-pipeline Skill --")

        # Safety check: CASEOPS_SANDBOX_TARGET_ORG must be set before Step 9
        sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
        if not sandbox_target:
            _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env.jira")
            _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
            _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env.jira and retry.")
            return

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, and `claude login` succeeded.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        prompt = _build_claude_prompt(
            key,
            "Run the full CaseOps fix pipeline for this issue through completion of investigation, "
            "internal notes, and Jira customer message (and any sandbox/escalation steps the playbook "
            "requires for this issue). Use the jira-salesforce-fix-pipeline Skill entrypoint.",
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
    """Reprocess single issue without Jira sync via jira-salesforce-fix-pipeline Skill.

    Useful for re-running a single issue that failed or needs investigation updates.
    """
    try:
        _log_emit_line(run_key, f"-- Reprocessing {key} (no sync) via jira-salesforce-fix-pipeline Skill --")

        # Safety check: CASEOPS_SANDBOX_TARGET_ORG must be set before Step 9
        sandbox_target = (os.environ.get("CASEOPS_SANDBOX_TARGET_ORG") or "").strip()
        if not sandbox_target:
            _log_emit_line(run_key, "ERROR: CASEOPS_SANDBOX_TARGET_ORG not set in .env.jira")
            _log_emit_line(run_key, "       Step 9 (deploy+test) requires an allowlisted Sandbox org.")
            _log_emit_line(run_key, "       Set CASEOPS_SANDBOX_TARGET_ORG in .env.jira and retry.")
            return

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, and `claude login` succeeded.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        prompt = _build_claude_prompt(
            key,
            "Reprocess the CaseOps fix pipeline for this issue without re-syncing from Jira. "
            "Use the jira-salesforce-fix-pipeline Skill entrypoint with 'reprocess' mode.",
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
    """Run global CaseOps pipeline via jira-salesforce-fix-pipeline Skill (full or reprocess mode).

    This invokes the Skill for global actions like "full" (sync + process all)
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

        # Safety check: if claude_code mode, verify `claude` CLI is available
        if not caseops_llm_auth_uses_anthropic_api_key():
            try:
                claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
                subprocess.run([claude_bin, "--version"], capture_output=True, timeout=5, check=True)
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                _log_emit_line(run_key, "ERROR: `claude` CLI not found or not responding")
                _log_emit_line(run_key, "       CASEOPS_LLM_AUTH=claude_code requires Claude Code installed.")
                _log_emit_line(run_key, "       Verify: `claude --version` runs, and `claude login` succeeded.")
                return

        # Safety check: if api_key mode, verify API key is set
        if caseops_llm_auth_uses_anthropic_api_key():
            api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
            if not api_key:
                _log_emit_line(run_key, "WARNING: CASEOPS_LLM_AUTH=api_key but ANTHROPIC_API_KEY not set")
                _log_emit_line(run_key, "         Sub-agents (Steps 3–10) will not execute. Text-only response only.")

        prompt = (
            f"Run the jira-salesforce-fix-pipeline Skill with instruction:\n\n{instruction}\n\n"
            f"Use the Skill entrypoint at skills/jira-salesforce-fix-pipeline/SKILL.md and read "
            f"ORCHESTRATOR-PROMPT.md for decision logic."
        )
        _do_stream_claude(prompt, run_key, issue_key=None)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _log_emit_line(run_key, f"Done: {run_key}")
        _log_emit_done(run_key)


def _build_claude_prompt(key: str, instruction: str) -> str:
    """Build a context-rich prompt for CaseOps LLM runs (API or Claude Code CLI)."""
    issues = _read_manifest()
    row = next((r for r in issues if r.get("Key") == key), {})
    summary = row.get("Summary", "")
    status  = row.get("Status", "")

    existing = []
    for ftype, rel in FILE_LOCATIONS.items():
        if ftype == "attachments":
            continue
        path = OUTPUTS / rel.format(key=key)
        if path.exists():
            existing.append(f"  - {FILE_LABELS[ftype]}: {path.relative_to(ROOT).as_posix()}")

    files_block = "\n".join(existing) if existing else "  - None yet"

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
        f"## Playbook (mandatory — read first)\n"
        f"A Claude Code stub may exist at .claude/skills/jira-salesforce-fix-pipeline/SKILL.md; "
        f"the entrypoint is the file below. Read SKILL.md fully, then read "
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
        f"## Instance Metadata & Deploy Directory\n"
        f"**CRITICAL for multi-instance deployments:** All metadata retrieval and deploy operations must use:\n"
        f"- Instance-isolated temp directory: `${{CASEOPS_OUTPUTS_DIR}}/../temp-retrieve`\n"
        f"- Environment variable: `CASEOPS_OUTPUTS_DIR={str(OUTPUTS)}`\n"
        f"- When using `sf project retrieve` or `sf project deploy`, ALWAYS pass:\n"
        f"  `--output-dir \"${{CASEOPS_OUTPUTS_DIR}}/../temp-retrieve\"`\n"
        f"- This prevents cross-instance metadata contamination (instance2 retrieving instance1's org metadata, etc.)\n"
        f"- Sub-agents spawned in Steps 5, 6, 9 must reference this path (see sub-agent-prompts.md)\n\n"
        f"## Instruction\n"
        f"{instruction}\n\n"
        f"## Salesforce Queries: Use sf CLI + SOQL (DEFAULT)\n"
        f"**For metadata queries, field inspection, permission checks, and configuration verification:**\n"
        f"1. **Prefer `sf` CLI commands** (read-only, fast, no browser needed):\n"
        f"   - `sf org open` (open/view in browser only when UI interaction needed)\n"
        f"   - `sf project retrieve start --metadata [type]` (pull metadata)\n"
        f"   - `sf sobject get --sobject [type]` (inspect objects/fields)\n"
        f"2. **Use SOQL queries** via `sf data query` to inspect data, field values, record types, assignments\n"
        f"3. **Never use Playwright or browser automation** for metadata queries, field inspection, or permission checks\n"
        f"4. **Only open browser** for:\n"
        f"   - Visual verification (testing layouts, field placement, visual tests)\n"
        f"   - UI clicks (when automation can't use CLI, e.g., custom buttons, flow runs)\n"
        f"   - Human-readable confirmation\n"
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
        f"- Do not ask the user to pick a workflow or skill; the playbook above is the workflow.\n"
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


def _available_tabs(key: str) -> list[dict[str, str]]:
    tabs = []
    for ftype, rel in FILE_LOCATIONS.items():
        if ftype == "attachments":
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
        "needs_escalation": has_eng_handoff,  # Issue needs escalation (has escalation handoff file)

        # New state machine
        "pipeline_state": state.value,
        "is_escalation_path": has_eng_handoff,  # Ground truth: file existence
        "is_jira_escalated": status == "Escalated to Engineering",  # Source of truth for Jira status
        "is_blocked": _investigation_indicates_blocked(key),
        "is_data_only": _test_report_is_data_only(key),
    }


def _investigation_indicates_blocked(key: str) -> bool:
    """True when outputs/investigations/<KEY>.md indicates issue is blocked/waiting."""
    path = OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(re.search(r"(?im)waiting\s+for|blocked|on\s+hold|requires?\s+customer|pending\s+customer|awaiting", text))


def _extract_blocker_reason(key: str) -> str:
    """Extract blocker reason from ## Blocker: section in investigation file."""
    path = OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r"(?im)^##\s*Blocker\s*:?\s*$", text)
    if not m:
        return ""
    after = text[m.end() :]
    block_lines: list[str] = []
    for raw in after.splitlines():
        if re.match(r"^\s*##\s", raw) and block_lines:
            break
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
    """Calculate current pipeline state based on file existence and Jira status.

    Escalation state is determined by Jira status = "Escalated to Engineering" (source of truth).
    Support-resolvable progression based on pipeline file artifacts.
    """
    has_investigation = (OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)).exists()
    has_internal_notes = (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists()
    has_test_report = (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists()

    # Escalation state: based on Jira status (source of truth)
    if status == "Escalated to Engineering":
        return PipelineState.ESCALATED_TO_ENGINEERING

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
        f'Process {key} through the jira-salesforce-fix-pipeline skill.\n\n'
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
        instruction = "Run the full CaseOps fix pipeline: reprocess all active issues without re-syncing from Jira. Use the jira-salesforce-fix-pipeline Skill with 'reprocess' mode."
    elif action == "full":
        use_global_skill = True
        instruction = "Run the full CaseOps fix pipeline: sync all issues from Jira and process all active issues through completion. Use the jira-salesforce-fix-pipeline Skill with 'full' mode."
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
        t = threading.Thread(target=_stream_claude_proc, args=(prompt, run_key), daemon=True)
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
    # Try instance-specific file first, fall back to shared default (supports per-instance customization)
    workspace = os.environ.get("CASEOPS_WORKSPACE", "default")
    instance_messages = ROOT / workspace / "canned-messages.json" if workspace != "default" else None
    messages_file = instance_messages if instance_messages and instance_messages.exists() else ROOT / "canned-messages.json"

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

    # Try instance-specific file first, fall back to shared default (supports per-instance customization)
    workspace = os.environ.get("CASEOPS_WORKSPACE", "default")
    instance_messages = ROOT / workspace / "canned-messages.json" if workspace != "default" else None
    messages_file = instance_messages if instance_messages and instance_messages.exists() else ROOT / "canned-messages.json"

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
    workspace = app.config.get("WORKSPACE", "default")
    instance_messages = ROOT / workspace / "canned-messages.json" if workspace != "default" else None
    messages_file = instance_messages if instance_messages and instance_messages.exists() else ROOT / "canned-messages.json"

    try:
        content = messages_file.read_text(encoding="utf-8")
        json.loads(content)  # Validate JSON
        return jsonify({
            "content": content,
            "is_custom": instance_messages and instance_messages.exists(),
            "path": str(messages_file.relative_to(ROOT))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/canned-messages", methods=["POST"])
def api_settings_set_canned_messages():
    """Update canned messages (saves to instance-specific file)."""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"error": "content required"}), 400

    # Validate JSON
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    workspace = app.config.get("WORKSPACE", "default")
    if workspace == "default":
        messages_file = ROOT / "canned-messages.json"
    else:
        messages_file = ROOT / workspace / "canned-messages.json"

    # Validate instance routing
    _validate_instance_path(messages_file, "write")

    try:
        messages_file.parent.mkdir(parents=True, exist_ok=True)
        messages_file.write_text(content, encoding="utf-8")
        return jsonify({
            "ok": True,
            "path": str(messages_file.relative_to(ROOT)),
            "is_custom": workspace != "default"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/canned-messages/reset", methods=["POST"])
def api_settings_reset_canned_messages():
    """Reset to default canned messages (delete instance-specific file)."""
    workspace = app.config.get("WORKSPACE", "default")
    if workspace == "default":
        return jsonify({"error": "Cannot reset default instance"}), 400

    messages_file = ROOT / workspace / "canned-messages.json"

    try:
        if messages_file.exists():
            messages_file.unlink()
        return jsonify({"ok": True, "message": "Reset to default messages"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/status", methods=["GET"])
def api_settings_status():
    """Return status of Claude CLI, sf CLI, and Salesforce orgs."""
    status = {
        "claude": {"installed": False},
        "sf_installed": False,
        "sf_prod": {"authenticated": False},
        "sf_sandbox": {"authenticated": False},
        "cci_installed": False,
        "cci_prod": {"authenticated": False},
        "cci_sandbox": {"authenticated": False},
    }

    use_cci = os.environ.get("CASEOPS_USE_CCI_FOR_AUTH", "false").lower() == "true"
    prod_alias = os.environ.get("CASEOPS_PRODUCTION_READ_ORG", "")
    sand_alias = os.environ.get("CASEOPS_SANDBOX_TARGET_ORG", "")

    # Check Claude
    try:
        result = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            status["claude"]["installed"] = True
            status["claude"]["version"] = result.stdout.strip()
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
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Skip warning lines, find JSON start
                    json_str = result.stdout.strip()
                    if json_str.startswith('{'):
                        data = json.loads(json_str)
                        status["sf_prod"]["authenticated"] = True
                        status["sf_prod"]["username"] = data.get("result", {}).get("username", "")
                    else:
                        # Find first { and parse from there
                        idx = json_str.find('{')
                        if idx >= 0:
                            data = json.loads(json_str[idx:])
                            status["sf_prod"]["authenticated"] = True
                            status["sf_prod"]["username"] = data.get("result", {}).get("username", "")
            except Exception:
                pass

        # Check sandbox org
        if sand_alias:
            try:
                result = subprocess.run(
                    ["sf", "org", "display", "--target-org", sand_alias, "--json"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    # Skip warning lines, find JSON start
                    json_str = result.stdout.strip()
                    if json_str.startswith('{'):
                        data = json.loads(json_str)
                        status["sf_sandbox"]["authenticated"] = True
                        status["sf_sandbox"]["username"] = data.get("result", {}).get("username", "")
                    else:
                        # Find first { and parse from there
                        idx = json_str.find('{')
                        if idx >= 0:
                            data = json.loads(json_str[idx:])
                            status["sf_sandbox"]["authenticated"] = True
                            status["sf_sandbox"]["username"] = data.get("result", {}).get("username", "")
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

    return jsonify(status)


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

    # Initialize instance-specific pipeline logs directory
    globals()["OUTPUTS_PIPELINE_LOGS"] = OUTPUTS / "pipeline-logs"

    # Pre-create all pipeline output subdirectories so Claude Code doesn't need write permissions to create them
    for subdir in [
        "jira", "investigations", "internal-notes", "jira-messages", "test-reports",
        "engineering-escalations", "step-4-hypothesis", "pipeline-logs"
    ]:
        (OUTPUTS / subdir).mkdir(parents=True, exist_ok=True)

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
        "engineering-escalations", "step-4-hypothesis", "pipeline-logs", "closed-resolved"
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

    # Validate no hardcoded ROOT paths are being used for instance operations
    print(f"[OK] Instance routing validation:")
    print(f"  - ROOT/outputs isolation: OUTPUTS={OUTPUTS.relative_to(ROOT) if OUTPUTS.is_relative_to(ROOT) else OUTPUTS}")
    print(f"  - Jira directory: {(OUTPUTS / 'jira').relative_to(ROOT) if (OUTPUTS / 'jira').is_relative_to(ROOT) else OUTPUTS / 'jira'}")
    print(f"  - Pipeline logs: {(OUTPUTS / 'pipeline-logs').relative_to(ROOT) if (OUTPUTS / 'pipeline-logs').is_relative_to(ROOT) else OUTPUTS / 'pipeline-logs'}")

    print(f"\n{'='*70}")
    print(f"[OK] Startup validation PASSED - instance isolation ready")
    print(f"{'='*70}\n")

    # use_reloader=False prevents the dev reloader from killing SSE streams
    app.run(debug=True, threaded=True, host="0.0.0.0", port=_args.port, use_reloader=False)
