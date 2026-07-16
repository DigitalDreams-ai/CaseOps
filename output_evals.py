"""Deterministic and optional model-graded evaluation of CaseOps outputs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from message_rules import (
    BANNED_CORPORATE_PATTERNS,
    BANNED_CORPORATE_WORDS,
    FIRST_PERSON_PLURAL_RE,
    GENERIC_GREETING_WORDS,
    SALESFORCE_ID_ANY_RE,
)
from model_config import validate_pinned_model
from pipeline_gates import validate_escalation_handoff, validate_hypothesis_artifact


ARTIFACT_DIRS = {
    "jira_message": "jira-messages",
    "engineering_escalation": "engineering-escalations",
    "hypothesis": "hypothesis",
    "internal_notes": "internal-notes",
}
RUBRIC_DIMENSIONS = {
    "engineering_escalation": ("artifact_pinpointed", "reproducible", "actionable"),
    "jira_message": ("voice", "clarity", "next_step_clear"),
    "hypothesis": ("concrete_root_cause", "fix_smallest_viable"),
}
_SENTENCE_START_RE = re.compile(r"(?im)(?:^|[.!?]\s+)(?:This is|That is|It is)\b")
_SF_LINK_RE = re.compile(r"sf://\S+", re.IGNORECASE)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _check(passed: bool, reason: str = "") -> dict[str, Any]:
    return {"passed": bool(passed), "reason": "" if passed else reason}


def _contains_salesforce_id(text: str) -> bool:
    for match in SALESFORCE_ID_ANY_RE.finditer(text):
        value = match.group(0)
        if any(char.isdigit() for char in value) and any(char.isalpha() for char in value):
            return True
    return False


def _jira_message_checks(text: str) -> dict[str, dict[str, Any]]:
    greeting = re.search(r"(?im)^\s*Hi\s+([^,\r\n]+),", text)
    reporter = greeting.group(1).strip() if greeting else ""
    if reporter.casefold() in GENERIC_GREETING_WORDS:
        reporter = ""
    reporter_occurrences = len(re.findall(rf"(?i)\b{re.escape(reporter)}\b", text)) if reporter else 0
    without_sf_links = _SF_LINK_RE.sub("", text)
    corporate = [
        word for word, pattern in zip(BANNED_CORPORATE_WORDS, BANNED_CORPORATE_PATTERNS) if pattern.search(text)
    ]
    return {
        "no_internal_marker": _check("[INTERNAL]" not in text.upper(), "Contains [INTERNAL] content"),
        "no_first_person_plural": _check(not FIRST_PERSON_PLURAL_RE.search(text), "Contains we/us language"),
        "no_em_dash": _check("—" not in text, "Contains an em dash"),
        "sentence_start_variety": _check(len(_SENTENCE_START_RE.findall(text)) <= 1, "More than one sentence starts with This is/That is/It is"),
        "reporter_name_once": _check(reporter_occurrences <= 1, "Reporter name appears more than once"),
        "no_banned_corporate_words": _check(not corporate, f"Contains banned corporate wording: {', '.join(corporate)}"),
        "no_salesforce_ids": _check(not _contains_salesforce_id(without_sf_links), "Contains a Salesforce-style 15/18-character ID outside an sf:// link"),
    }


def _internal_notes_checks(text: str) -> dict[str, dict[str, Any]]:
    has_cause = bool(re.search(r"(?i)\b(?:NOT\s+(?:a|an|the)|Root cause)\b", text))
    has_action = bool(re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?Action(?:\*\*)?\s*:", text))
    separates_orgs = "production" in text.lower() and ("sandbox" in text.lower() or re.search(r"(?i)\bno[- ]deploy\b", text))
    return {
        "cause_statement": _check(has_cause, "Missing root-cause or NOT-a cause statement"),
        "action_statement": _check(has_action, "Missing Action: statement"),
        "production_sandbox_separation": _check(bool(separates_orgs), "Does not distinguish Production from Sandbox/no deploy"),
    }


def evaluate_artifact(outputs: Path, artifact_type: str, path: Path) -> dict[str, Any]:
    key = path.stem
    if artifact_type == "jira_message":
        checks = _jira_message_checks(_read_text(path))
    elif artifact_type == "internal_notes":
        checks = _internal_notes_checks(_read_text(path))
    elif artifact_type == "engineering_escalation":
        gate = validate_escalation_handoff(outputs, key)
        checks = {"artifact_gate": _check(gate.passed, gate.reason)}
    elif artifact_type == "hypothesis":
        gate = validate_hypothesis_artifact(outputs, key)
        checks = {"artifact_gate": _check(gate.passed, gate.reason)}
    else:
        raise ValueError(f"Unknown artifact type: {artifact_type}")
    return {
        "artifact_type": artifact_type,
        "key": key,
        "path": str(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "checks": checks,
        "deterministic_passed": all(item["passed"] for item in checks.values()),
    }


def _sample_artifacts(outputs: Path, lookback_days: int, max_artifacts: int, now: datetime) -> list[tuple[str, Path]]:
    cutoff = now - timedelta(days=max(0, lookback_days))
    candidates: list[tuple[float, str, Path]] = []
    for artifact_type, dirname in ARTIFACT_DIRS.items():
        for path in (outputs / dirname).glob("*.md"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if datetime.fromtimestamp(mtime, timezone.utc) >= cutoff:
                candidates.append((mtime, artifact_type, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(artifact_type, path) for _mtime, artifact_type, path in candidates[: max(1, max_artifacts)]]


def _rubric_prompt(result: dict[str, Any], text: str) -> str:
    dimensions = RUBRIC_DIMENSIONS[result["artifact_type"]]
    return (
        "Grade this CaseOps artifact. Return JSON only with this exact shape: "
        '{"scores":{"dimension":1},"worst_problem":"..."}. '
        f"Required dimensions: {', '.join(dimensions)}. Each score must be an integer from 1 to 5. "
        "Judge only the supplied artifact; do not infer missing evidence.\n\n"
        f"Artifact type: {result['artifact_type']}\nArtifact:\n{text}"
    )


def _parse_llm_grade(raw: Any, dimensions: tuple[str, ...]) -> dict[str, Any]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if isinstance(payload.get("result"), str):
            payload = json.loads(payload["result"])
        scores = payload.get("scores")
        if not isinstance(scores, dict):
            raise ValueError("scores object missing")
        normalized = {}
        for dimension in dimensions:
            value = int(scores.get(dimension))
            if value < 1 or value > 5:
                raise ValueError(f"score out of range: {dimension}")
            normalized[dimension] = value
        return {"scores": normalized, "worst_problem": str(payload.get("worst_problem") or ""), "llm_error": ""}
    except Exception as exc:
        return {"scores": {}, "worst_problem": "", "llm_error": f"{type(exc).__name__}: {exc}"}


def claude_cli_grader(model_id: str, *, env: dict[str, str] | None = None, timeout: int = 180) -> Callable[[str], str]:
    model_id = validate_pinned_model(model_id)

    claude_cmd = shutil.which("claude") or "/usr/local/bin/claude"

    def grade(prompt: str) -> str:
        completed = subprocess.run(
            [claude_cmd, "-p", "--output-format", "json", "--model", model_id],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env or os.environ.copy(),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "Claude grader failed").strip())
        return completed.stdout
    return grade


def _pass_rates(results: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[bool]] = {}
    for result in results:
        for name, check in result["checks"].items():
            totals.setdefault(f"{result['artifact_type']}.{name}", []).append(bool(check["passed"]))
    return {name: sum(values) / len(values) for name, values in sorted(totals.items()) if values}


def _mean_rubric_scores(results: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[int]] = {}
    for result in results:
        for name, score in (result.get("llm_grade") or {}).get("scores", {}).items():
            totals.setdefault(f"{result['artifact_type']}.{name}", []).append(int(score))
    return {name: round(sum(values) / len(values), 3) for name, values in sorted(totals.items()) if values}


def _last_history_entry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1]) if lines else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _unique_run_id(report_dir: Path, now: datetime) -> str:
    base = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    candidate = base
    suffix = 2
    while (report_dir / f"{candidate}.json").exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _markdown_summary(report: dict[str, Any], previous: dict[str, Any]) -> str:
    lines = [
        "# CaseOps Output Evaluation",
        "",
        f"Generated: {report['generated_at']}",
        f"Reason: {report['reason']}",
        f"Model: {report['model_id']}",
        f"Artifacts sampled: {report['artifact_count']}",
        "",
        "## Deterministic Pass Rates",
        "",
        "| Check | Pass rate | Change |",
        "| --- | ---: | ---: |",
    ]
    previous_rates = previous.get("pass_rates") if isinstance(previous.get("pass_rates"), dict) else {}
    for name, rate in report["pass_rates"].items():
        prior = previous_rates.get(name)
        delta = "n/a" if prior is None else f"{rate - float(prior):+.1%}"
        lines.append(f"| {name} | {rate:.1%} | {delta} |")
    if not report["pass_rates"]:
        lines.append("| No artifacts sampled | n/a | n/a |")

    failures = []
    for result in report["results"]:
        reasons = [check["reason"] for check in result["checks"].values() if not check["passed"]]
        if reasons:
            failures.append((result, reasons))
    lines.extend(["", "## Failing Artifacts", ""])
    if failures:
        for result, reasons in failures:
            lines.append(f"- {result['artifact_type']} {result['key']}: {'; '.join(reasons)}")
    else:
        lines.append("No deterministic failures.")
    return "\n".join(lines).rstrip() + "\n"


def run_output_evals(
    outputs: Path,
    *,
    model_id: str,
    lookback_days: int = 7,
    max_artifacts: int = 25,
    llm_enabled: bool = False,
    llm_grader: Callable[[str], Any] | None = None,
    alert_threshold: float = 0.9,
    signal_writer: Callable[..., Any] | None = None,
    reason: str = "manual",
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = Path(outputs)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    report_dir = outputs / "eval-reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    sampled = _sample_artifacts(outputs, lookback_days, max_artifacts, now)
    results = [evaluate_artifact(outputs, artifact_type, path) for artifact_type, path in sampled]

    if llm_enabled:
        for result in results:
            dimensions = RUBRIC_DIMENSIONS.get(result["artifact_type"])
            if not dimensions:
                continue
            if llm_grader is None:
                result["llm_grade"] = {"scores": {}, "worst_problem": "", "llm_error": "LLM grader is not configured"}
                continue
            try:
                raw = llm_grader(_rubric_prompt(result, _read_text(Path(result["path"]))))
            except Exception as exc:
                raw = {"scores": {}, "worst_problem": "", "llm_error": f"{type(exc).__name__}: {exc}"}
            if isinstance(raw, dict) and raw.get("llm_error"):
                result["llm_grade"] = raw
            else:
                result["llm_grade"] = _parse_llm_grade(raw, dimensions)

    timestamp = _unique_run_id(report_dir, now)
    history_path = report_dir / "history.jsonl"
    previous = _last_history_entry(history_path)
    pass_rates = _pass_rates(results)
    regressions = {name: rate for name, rate in pass_rates.items() if rate < alert_threshold}
    previous_rates = previous.get("pass_rates") if isinstance(previous.get("pass_rates"), dict) else {}
    new_regressions = {
        name: rate
        for name, rate in regressions.items()
        if name not in previous_rates or float(previous_rates[name]) >= alert_threshold
    }
    report = {
        "schema_version": 1,
        "run_id": timestamp,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "reason": reason,
        "model_id": model_id,
        "lookback_days": lookback_days,
        "max_artifacts": max_artifacts,
        "llm_enabled": llm_enabled,
        "artifact_count": len(results),
        "pass_rates": pass_rates,
        "regressions": regressions,
        "new_regressions": new_regressions,
        "mean_rubric_scores": _mean_rubric_scores(results),
        "results": results,
    }
    # Signal ALL regressions every run, not just new ones: a persistently
    # failing check must keep reappearing in the knowledge review queue, and
    # repeated signals feed the knowledge auditor's recurrence grouping.
    if regressions and signal_writer:
        try:
            signal_writer(
                outputs,
                issue_key="__output_evals__",
                run_id=timestamp,
                source_step="OUTPUT_EVALS",
                signal_type="output_quality_regression",
                summary=f"Output quality pass rate below {alert_threshold:.0%} for {len(regressions)} check(s) ({len(new_regressions)} new).",
                evidence=[f"{name}={rate:.1%}" for name, rate in regressions.items()],
                topic="output-quality",
            )
        except Exception as exc:
            report["signal_error"] = f"{type(exc).__name__}: {exc}"
    report_path = report_dir / f"{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    history_entry = {key: value for key, value in report.items() if key != "results"}
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
    latest_path = report_dir / "latest.md"
    latest_path.write_text(_markdown_summary(report, previous), encoding="utf-8")
    report["report_path"] = str(report_path)
    report["history_path"] = str(history_path)
    report["latest_path"] = str(latest_path)

    return report


def read_latest_report(outputs: Path) -> dict[str, Any]:
    report_dir = Path(outputs) / "eval-reports"
    history = _last_history_entry(report_dir / "history.jsonl")
    latest_md = _read_text(report_dir / "latest.md")
    return {"summary_markdown": latest_md, "headline": history}
