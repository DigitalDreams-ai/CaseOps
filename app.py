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
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file, stream_with_context

try:
    import markdown as md_lib

    def render_md(text: str) -> str:
        return md_lib.markdown(text, extensions=["tables", "fenced_code"])

except ImportError:
    def render_md(text: str) -> str:
        import html
        return f"<pre style='white-space:pre-wrap'>{html.escape(text)}</pre>"


app = Flask(__name__)
ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def _load_jira_env() -> None:
    """Load .env.jira into os.environ (does not overwrite existing vars)."""
    env_file = ROOT / ".env.jira"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_jira_env()
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")


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

CLOSED_STATUSES = {"closed", "resolved"}
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
    "closed_resolved": "Closed/Resolved",
    "attachments":     "Attachments",
}

# Global actions (sync, triage, full) use this sentinel key.
_GLOBAL_KEY = "__global__"

# -- run state ---------------------------------------------------------------
# Multiple issue-specific runs are allowed in parallel.
# Global actions block each other and block new issue runs.
# Issue runs are blocked only while a global action is active.

_state_lock = threading.Lock()
_active_keys: set[str] = set()          # currently running run keys
_log_q: queue.Queue[str] = queue.Queue()  # tagged messages: "key|line" or "__done__|key"


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
            _log_q.put(f"{run_key}|{line.rstrip()}")
        proc.wait()
        _log_q.put(f"{run_key}|-- exit code {proc.returncode} --")
        return proc.returncode
    except Exception as exc:
        _log_q.put(f"{run_key}|ERROR: {exc}")
        return 1


def _do_stream_claude(prompt: str, run_key: str) -> None:
    """Run Claude Code CLI non-interactively, parsing stream-json output."""
    cmd = ["claude", "-p", prompt,
           "--output-format", "stream-json",
           "--verbose",
           "--dangerously-skip-permissions"]
    try:
        proc = subprocess.Popen(
            cmd,
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
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                _log_q.put(f"{run_key}|{raw}")
                continue

            etype = event.get("type", "")

            if etype == "assistant":
                for block in event.get("message", {}).get("content", []):
                    btype = block.get("type", "")
                    if btype == "text":
                        for line in block.get("text", "").splitlines():
                            if line.strip():
                                _log_q.put(f"{run_key}|{line}")
                    elif btype == "tool_use":
                        tool = block.get("name", "tool")
                        inp  = block.get("input", {})
                        detail = inp.get("command") or inp.get("file_path") or inp.get("path") or ""
                        detail = str(detail)[:80]
                        _log_q.put(f"{run_key}|[{tool}]{' ' + detail if detail else ''}")

            elif etype == "result":
                subtype = event.get("subtype", "")
                cost    = event.get("cost_usd")
                cost_str = f"  cost: ${cost:.4f}" if cost else ""
                _log_q.put(f"{run_key}|-- {subtype}{cost_str} --")

            elif etype == "system":
                pass  # ignore init events

        if proc.stderr:
            err = proc.stderr.read().strip()
            if err:
                for line in err.splitlines():
                    _log_q.put(f"{run_key}|ERR: {line}")

        proc.wait()
        if proc.returncode != 0:
            _log_q.put(f"{run_key}|-- exit code {proc.returncode} --")

    except FileNotFoundError:
        _log_q.put(f"{run_key}|ERROR: 'claude' CLI not found. Is Claude Code installed and on PATH?")
    except Exception as exc:
        _log_q.put(f"{run_key}|ERROR: {exc}")


def _stream_proc(cmd: list[str], run_key: str) -> None:
    try:
        _do_stream_proc(cmd, run_key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _log_q.put(f"__done__|{run_key}")


def _stream_claude_proc(prompt: str, run_key: str) -> None:
    try:
        _do_stream_claude(prompt, run_key)
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _log_q.put(f"__done__|{run_key}")


def _stream_full_issue(key: str, run_key: str) -> None:
    """Run pipeline script then hand off to Claude for Internal Notes + Jira Message."""
    try:
        env_file = str(ROOT / ".env.jira")
        cmd = [sys.executable, "run_pipeline.py", "--env-file", env_file, "--issue", key]
        exit_code = _do_stream_proc(cmd, run_key)
        if exit_code == 0:
            _log_q.put(f"{run_key}|-- Handing off to Claude --")
            prompt = _build_claude_prompt(
                key,
                "Process this issue through the full jira-salesforce-fix-pipeline skill. "
                "Complete the investigation, draft internal notes, and draft the Jira message.",
            )
            _do_stream_claude(prompt, run_key)
        else:
            _log_q.put(f"{run_key}|-- Pipeline failed (exit {exit_code}) -- skipping Claude --")
    finally:
        with _state_lock:
            _active_keys.discard(run_key)
        _log_q.put(f"__done__|{run_key}")


def _build_claude_prompt(key: str, instruction: str) -> str:
    """Build a context-rich prompt for Claude Code."""
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

    return (
        f"Issue: {key} — {summary}\n"
        f"Status: {status}\n\n"
        f"Existing pipeline files:\n{files_block}\n\n"
        f"Instruction: {instruction}\n\n"
        f"Use the jira-salesforce-fix-pipeline skill to handle this. "
        f"Read the existing files above for context before taking any action."
    )


# -- helpers -----------------------------------------------------------------

def _manifest_path() -> Path:
    return OUTPUTS / "jira" / "manifest.csv"


def _read_manifest() -> list[dict[str, str]]:
    path = _manifest_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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


def _claude_prompt(key: str, summary: str) -> str:
    return (
        f'Process {key} through the jira-salesforce-fix-pipeline skill.\n\n'
        f'Issue: {summary}'
    )


# -- routes ------------------------------------------------------------------

@app.get("/")
def index():
    issues = _read_manifest()
    has_manifest = _manifest_path().exists()
    return render_template("index.html", issues=issues, has_manifest=has_manifest)


@app.get("/api/issues")
def api_issues():
    issues = _read_manifest()
    result = []
    for row in issues:
        key = row.get("Key", "")
        status = row.get("Status", "")
        result.append({
            "key": key,
            "status": status,
            "summary": row.get("Summary", ""),
            "disposition": _disposition(status),
            "updated": row.get("Updated", ""),
            "jira_url": f"{JIRA_BASE_URL}/browse/{key}" if JIRA_BASE_URL else "",
            "has_jira_message": (OUTPUTS / FILE_LOCATIONS["jira_message"].format(key=key)).exists(),
        })
    return jsonify(result)


@app.get("/api/issue/<key>")
def api_issue(key: str):
    issues = _read_manifest()
    row = next((r for r in issues if r.get("Key") == key), None)
    if not row:
        return jsonify({"error": "not found"}), 404
    tabs = _available_tabs(key)
    return jsonify({
        "key": key,
        "status": row.get("Status", ""),
        "summary": row.get("Summary", ""),
        "disposition": _disposition(row.get("Status", "")),
        "updated": row.get("Updated", ""),
        "tabs": tabs,
        "claude_prompt": _claude_prompt(key, row.get("Summary", "")),
        "jira_url": f"{JIRA_BASE_URL}/browse/{key}" if JIRA_BASE_URL else "",
    })


@app.get("/api/issue/<key>/file/<ftype>")
def api_file(key: str, ftype: str):
    rel = FILE_LOCATIONS.get(ftype)
    if not rel:
        return jsonify({"error": "unknown file type"}), 400
    path = OUTPUTS / rel.format(key=key)
    if not path.exists():
        return jsonify({"html": "<p class='empty'>File not yet generated.</p>"})
    text = path.read_text(encoding="utf-8", errors="replace")
    return jsonify({"html": render_md(text), "raw": text})


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "full")
    key = data.get("key", "")

    is_global = action in ("sync", "triage", "full")
    run_key = _GLOBAL_KEY if is_global else key

    env_file = str(ROOT / ".env.jira")
    use_claude_cli = False
    use_full_issue = False

    if action == "sync":
        cmd = [sys.executable, "jira_sync.py", "--env-file", env_file]
    elif action == "sync_issue" and key:
        cmd = [sys.executable, "run_pipeline.py", "--env-file", env_file, "--issue", key]
    elif action == "triage":
        cmd = [sys.executable, "run_pipeline.py", "--no-sync"]
    elif action == "full":
        cmd = [sys.executable, "run_pipeline.py", "--env-file", env_file]
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
        return jsonify({"active_keys": list(_active_keys), "count": len(_active_keys)})


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


@app.get("/files/attachments/<key>/<path:filename>")
def serve_attachment(key: str, filename: str):
    att_dir = OUTPUTS / "jira" / "attachments" / key
    path = (att_dir / filename).resolve()
    if not str(path).startswith(str(att_dir.resolve())):
        return jsonify({"error": "forbidden"}), 403
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(path)


if __name__ == "__main__":
    # use_reloader=False prevents the dev reloader from killing SSE streams
    app.run(debug=True, threaded=True, port=5000, use_reloader=False)
