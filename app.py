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
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

from caseops_paths import default_jira_dir
from jira_sync import JiraClient, update_manifest_status

try:
    import markdown as md_lib

    def render_md(text: str) -> str:
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

_CACHE_MAX_KEYS = 100


def _cache_evict(cache: dict) -> None:
    """Evict oldest entries when cache exceeds _CACHE_MAX_KEYS."""
    while len(cache) > _CACHE_MAX_KEYS:
        cache.pop(next(iter(cache)))


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

OUTPUTS_PIPELINE_LOGS = OUTPUTS / "pipeline-logs"
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
    with _PIPELINE_LOG_LOCK:
        with _pipeline_log_path(run_key).open("a", encoding="utf-8") as fh:
            fh.write(line)


def _log_emit_line(run_key: str, text: str) -> None:
    """Notify SSE clients and append to per-key pipeline history on disk."""
    _log_q.put(f"{run_key}|{text}")
    _persist_pipeline_record(run_key, text, kind="line")


def _log_emit_done(run_key: str) -> None:
    _log_q.put(f"__done__|{run_key}")
    _persist_pipeline_record(run_key, "", kind="done")


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


def _claude_process_env() -> dict[str, str]:
    """Environment for Claude Code CLI subprocess (``claude_code`` mode only)."""
    env = os.environ.copy()
    if not caseops_llm_auth_uses_anthropic_api_key():
        env.pop("ANTHROPIC_API_KEY", None)
    chrome = (env.get("CASEOPS_CLAUDE_BROWSER") or "").strip()
    if chrome:
        env["BROWSER"] = chrome
        if not (env.get("CLAUDE_CODE_CHROME_PATH") or "").strip():
            env["CLAUDE_CODE_CHROME_PATH"] = chrome
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
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            bufsize=1,
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
    """
    cmd = [
        "claude",
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
            "CaseOps LLM: Claude Code CLI (CASEOPS_LLM_AUTH=claude_code; ANTHROPIC_API_KEY omitted).",
        )
        proc = subprocess.Popen(
            cmd,
            env=_claude_process_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            bufsize=1,
        )
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
                        detail = str(detail)[:80]
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

        proc.wait()
        if proc.returncode == 0 and issue_key and assistant_text:
            full_output = "\n".join(assistant_text)
            _save_claude_output(full_output, issue_key)
        elif proc.returncode != 0:
            _log_emit_line(run_key, f"-- exit code {proc.returncode} --")

    except FileNotFoundError:
        _log_emit_line(run_key, "ERROR: 'claude' CLI not found. Is Claude Code installed and on PATH?")
    except Exception as exc:
        _log_emit_line(run_key, f"ERROR: {exc}")


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
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(suggested_text, encoding="utf-8")

    # Extract [INTERNAL] (internal notes)
    if internal_start != -1:
        internal_text = content[internal_start:].strip()
        # Remove header line
        internal_text = "\n".join(internal_text.split("\n")[1:]).strip()
        if internal_text:
            path = OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)
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
    """Run pipeline script then hand off to Claude for Internal Notes + Jira Message."""
    try:
        env_file = str(ROOT / ".env.jira")
        cmd = [
            sys.executable,
            "run_pipeline.py",
            "--env-file",
            env_file,
            "--outputs-dir",
            str(OUTPUTS),
            "--issue",
            key,
        ]
        exit_code = _do_stream_proc(cmd, run_key)
        if exit_code == 0:
            _log_emit_line(run_key, "-- Handing off to Claude --")
            prompt = _build_claude_prompt(
                key,
                "Run the full CaseOps fix pipeline for this issue through completion of investigation, "
                "internal notes, and Jira customer message (and any sandbox/escalation steps the playbook "
                "requires for this issue).",
            )
            _do_stream_claude(prompt, run_key, key)
        else:
            _log_emit_line(run_key, f"-- Pipeline failed (exit {exit_code}) -- skipping Claude --")
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        # Phase 2: invalidate caches for this issue when full-issue run completes
        jira_summary_cache.pop(key, None)
        investigation_cache.pop(key, None)
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
        f"\n"
        f"| File | Purpose | When to Update |\n"
        f"|------|---------|----------------|\n"
        f"| `outputs/investigations/{key}.md` | Investigation record (issue understanding, Salesforce problem, similar items analysis) | After diagnosis, before drafting notes |\n"
        f"| `outputs/internal-notes/{key}.md` | Internal notes for operator (root cause, escalation decision, fix notes) | When you've diagnosed the issue |\n"
        f"| `outputs/jira-messages/{key}.md` | Customer-facing Jira message (confirmed fix OR engineering escalation) | When ready to respond to customer |\n"
        f"| `outputs/test-reports/{key}.md` | Test cases, results, and fix validation | After testing the fix in Sandbox |\n"
        f"| `outputs/engineering-escalations/{key}.md` | Engineering handoff (if escalating) | When escalating to Engineering team |\n"
        f"\n"
        f"**Update guidance:**\n"
        f"- Read existing files first (if they exist) to preserve prior work\n"
        f"- Update them directly (do not ask operator or wait for confirmation)\n"
        f"- Commit your changes with `git add` + `git commit` if substantial updates\n"
        f"- If you cannot complete a task, update the relevant file to document progress and blockers\n"
        f"\n"
        f"## Rules\n"
        f"- Do not ask the user to pick a workflow or skill; the playbook above is the workflow.\n"
        f"- Proceed with the next pipeline steps implied by the playbook and by which outputs/ files "
        f"already exist for {key}.\n"
        f"- Create or update outputs/ artifacts this issue needs (paths as defined in the playbook).\n"
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


def _pipeline_file_flags(key: str) -> dict[str, bool]:
    """Which pipeline output files exist for this issue (for dashboard / API)."""
    # Phase 2: check investigation_cache before disk I/O for investigation/solution flags
    if key in investigation_cache:
        cached = investigation_cache[key]
        has_investigation = cached["has_investigation"]
        has_solution = cached["has_solution"]
    else:
        has_investigation = (OUTPUTS / FILE_LOCATIONS["investigation"].format(key=key)).exists()
        has_solution = (OUTPUTS / "solutions" / key).exists()
        investigation_cache[key] = {"has_investigation": has_investigation, "has_solution": has_solution}
        _cache_evict(investigation_cache)

    return {
        "has_jira_summary": (OUTPUTS / FILE_LOCATIONS["jira_summary"].format(key=key)).exists(),
        "has_investigation": has_investigation,
        "has_internal_notes": (OUTPUTS / FILE_LOCATIONS["internal_notes"].format(key=key)).exists(),
        "has_jira_message": (OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key)).exists(),
        "has_test_report": (OUTPUTS / FILE_LOCATIONS["test_report"].format(key=key)).exists(),
        "has_eng_handoff": (OUTPUTS / FILE_LOCATIONS["eng_handoff"].format(key=key)).exists(),
        "has_confirmed_solution": _test_report_confirms_fix(key),
        "has_solution": has_solution,
    }


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
        flags = _pipeline_file_flags(key)
        due = row.get("Due", "") or ""
        result.append({
            "key": key,
            "status": status,
            "summary": row.get("Summary", ""),
            "disposition": _disposition(status),
            "updated": row.get("Updated", ""),
            "due": due,
            "priority_name": row.get("Priority", "") or "",
            "sla_remaining_ms": _sla_remaining_ms(due),
            "jira_url": f"{JIRA_BASE_URL}/browse/{key}" if JIRA_BASE_URL else "",
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
    tabs = _available_tabs(key)
    due = row.get("Due", "") or ""
    flags = _pipeline_file_flags(key)
    return jsonify({
        "key": key,
        "status": row.get("Status", ""),
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
    if ftype == "jira_summary" and key in jira_summary_cache:
        return jsonify(jira_summary_cache[key])

    path = OUTPUTS / rel.format(key=key)
    if not path.exists():
        return jsonify({"html": "<p class='empty'>File not yet generated.</p>"})
    text = path.read_text(encoding="utf-8", errors="replace")
    result = {"html": render_md(text), "raw": text}

    # Phase 2: populate jira_summary cache
    if ftype == "jira_summary":
        jira_summary_cache[key] = result
        _cache_evict(jira_summary_cache)

    return jsonify(result)


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "full")
    key = data.get("key", "")

    is_global = action in ("sync", "triage", "full", "sync_new")
    run_key = _GLOBAL_KEY if is_global else key

    env_file = str(ROOT / ".env.jira")
    use_claude_cli = False
    use_full_issue = False

    if action == "sync":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file]
    elif action == "sync_new":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file, "--new-only"]
    elif action == "sync_issue" and key:
        cmd = [
            sys.executable,
            "run_pipeline.py",
            "--env-file",
            env_file,
            "--outputs-dir",
            str(OUTPUTS),
            "--issue",
            key,
        ]
    elif action == "triage":
        cmd = [sys.executable, "run_pipeline.py", "--no-sync", "--outputs-dir", str(OUTPUTS)]
    elif action == "full":
        cmd = [
            sys.executable,
            "run_pipeline.py",
            "--env-file",
            env_file,
            "--outputs-dir",
            str(OUTPUTS),
        ]
    elif action == "full_issue" and key:
        use_full_issue = True
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
            safe = msg.replace("\n", " ")
            yield f"data: {safe}\n\n"

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
    _load_jira_env()
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

    _load_jira_env()
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


@app.route("/api/canned-messages", methods=["GET"])
def api_canned_messages():
    messages_file = ROOT / "canned-messages.json"
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

    messages_file = ROOT / "canned-messages.json"
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

    if "[insert signature]" in body:
        sig_file = ROOT / "jira-signature.txt"
        sig = sig_file.read_text(encoding="utf-8").strip() if sig_file.exists() else ""
        body = body.replace("[insert signature]", sig)

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
    _args = parser.parse_args()

    WORKSPACE = _args.workspace
    OUTPUTS = ROOT / "outputs" / WORKSPACE if WORKSPACE != "default" else ROOT / "outputs"
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    _load_jira_env(ROOT / f".env.jira.{WORKSPACE}" if WORKSPACE != "default" else ROOT / ".env.jira")
    JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    app.config["WORKSPACE"] = WORKSPACE

    # use_reloader=False prevents the dev reloader from killing SSE streams
    app.run(debug=True, threaded=True, port=_args.port, use_reloader=False)
