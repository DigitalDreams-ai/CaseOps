"""CaseOps Knowledge service.

This module keeps the governed knowledge lifecycle out of Flask route/prompt
code. Source-controlled core knowledge lives under ``skills/.../knowledge``;
runtime state and org-specific knowledge live under appdata outputs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CORE_KNOWLEDGE_ROOT = Path(__file__).resolve().parent / "skills" / "caseops-pipeline" / "knowledge" / "core"
KNOWLEDGE_SCHEMA_VERSION = 1

RUNTIME_DIRS = (
    "org-profile",
    "local-gotchas",
    "lessons-learned",
    "pending-lessons",
    "accepted-lessons",
    "rejected-lessons",
    "helper-work-items",
    "signals",
    "audit-reports",
    "decision-artifacts",
)

LESSON_ACTIVE_STATUSES = {"accepted", "active"}
LESSON_INACTIVE_STATUSES = {"pending", "rejected", "retired"}
ROUTES = {"org_lesson", "helper_work_item", "developer_review", "report_only"}
DEVELOPER_REVIEW_TYPES = {"core_knowledge", "guardrail", "template", "code", "queue_policy"}
QUALITY_LABELS = {"high", "medium", "low", "report_only"}
REDACTION_STATUSES = {"not_needed", "redacted", "blocked_unsafe", "unknown"}
HELPER_WORK_STATUSES = {"pending", "accepted_for_work", "implemented", "verified", "retired"}
HELPER_WORK_TRANSITIONS = {
    "pending": {"accepted_for_work", "retired"},
    "accepted_for_work": {"implemented", "retired"},
    "implemented": {"verified", "retired"},
    "verified": {"retired"},
    "retired": set(),
}
HIGH_VALUE_SINGLE_LESSON_TYPES = {
    "deploy_pattern_gap",
    "org_gotcha",
    "salesforce_behavior_gotcha",
    "validation_pattern",
}
HIGH_VALUE_SINGLE_HELPER_TYPES = {
    "deploy_tooling_gotcha",
}
PENDING_LESSON_SIGNAL_TYPES = {
    "helper_failure",
    "helper_available_not_used",
    "invalid_query_field",
    *HIGH_VALUE_SINGLE_LESSON_TYPES,
}
HELPER_WORK_SIGNAL_TYPES = {
    *HIGH_VALUE_SINGLE_HELPER_TYPES,
    "helper_related_failure",
    "invalid_command_pattern",
}
FAILURE_CLASSES = {
    "bad_context",
    "missing_helper",
    "helper_failure",
    "stale_state",
    "weak_template",
    "unsafe_prod_request",
    "invalid_salesforce_assumption",
    "queue_policy_skip",
    "noise",
}

DEFAULT_RUNTIME_INDEX: dict[str, Any] = {
    "version": KNOWLEDGE_SCHEMA_VERSION,
    "description": "CaseOps runtime org knowledge. Core knowledge is seeded from source files; org-profile and local lessons are appdata only.",
    "always_read": [],
    "max_context_chars": 12000,
    "max_context_chars_per_file": 1200,
    "max_topic_files": 6,
    "topics": [],
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(access[_-]?token|refresh[_-]?token|api[_-]?token|sid)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)frontdoor\.jsp\?sid=[^\s)]+"),
    re.compile(r"00D[A-Za-z0-9]{12,}![A-Za-z0-9._-]{20,}"),
    re.compile(r"ATATT[0-9A-Za-z._=-]{20,}"),
]


@dataclass(frozen=True)
class KnowledgeSelection:
    """Selected knowledge item with provenance and diagnostics."""

    path: Path
    rel_path: str
    layer: str
    knowledge_type: str
    topic_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class LessonRefinement:
    """Review-ready decision for a grouped set of audit signals."""

    action: str
    trigger: str
    lesson: str
    recommended_file: str
    knowledge_type: str
    confidence: str
    risk: str = "low"
    keywords: tuple[str, ...] = ()
    reason: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str, default: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned or default


def helper_work_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned or "helper-work-item"


def file_signature(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def redact_text(text: str) -> str:
    redacted = text or ""
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redaction_status_for_text(text: str) -> str:
    return "redacted" if contains_secret(text or "") else "not_needed"


def redaction_status_for_payload(payload: dict[str, Any]) -> str:
    return redaction_status_for_text(json.dumps(payload, ensure_ascii=False))


def contains_secret(text: str) -> bool:
    return redact_text(text) != (text or "")


def classify_failure_class(signal_type: str, topic: str = "", text: str = "") -> str:
    value = " ".join([signal_type or "", topic or "", text or ""]).lower()
    signal = (signal_type or "").lower()
    if signal in {"deploy_pattern_gap", "deploy_tooling_gotcha", "salesforce_behavior_gotcha", "validation_pattern", "org_gotcha"}:
        if "deploy" in signal or "deploy" in value:
            return "invalid_salesforce_assumption"
        if "validation" in signal:
            return "invalid_salesforce_assumption"
        return "bad_context"
    if any(item in value for item in ("invalidprojectworkspace", "invalid_sfdx_workspace", "sfdx workspace", "sfdx-project")):
        return "bad_context"
    if signal in {"helper_related_failure", "helper_failure"}:
        return "helper_failure"
    if any(item in value for item in ("json_decode", "jsondecode", "json_parse", "expecting value", "helper_failure")):
        return "helper_failure"
    if any(item in value for item in ("helper_available_not_used", "missing_helper")):
        return "missing_helper"
    if any(item in value for item in ("template", "markdown", "jira-message", "issue-brief", "handoff")):
        return "weak_template"
    if any(item in value for item in ("invalid_query", "invalid_type", "invalid field", "no such column", "salesforce")):
        return "invalid_salesforce_assumption"
    if any(item in value for item in ("prod", "production", "unsafe_prod", "frontdoor")):
        return "unsafe_prod_request"
    if any(item in value for item in ("queue_policy", "closed", "resolved", "engineering")):
        return "queue_policy_skip"
    if any(item in value for item in ("stale", "retry", "blocked", "state")):
        return "stale_state"
    if any(item in value for item in ("missing_file", "missing file", "no such file")):
        return "noise"
    return "noise"


def route_for_failure_class(failure_class: str, signal_type: str = "") -> tuple[str, str]:
    if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES or signal_type in {"invalid_query_field"}:
        return "org_lesson", ""
    if failure_class in {"missing_helper", "helper_failure"} or signal_type in {"helper_available_not_used", *HELPER_WORK_SIGNAL_TYPES}:
        return "helper_work_item", ""
    if failure_class in {"weak_template", "unsafe_prod_request", "bad_context", "invalid_salesforce_assumption", "stale_state"}:
        review_type = {
            "weak_template": "template",
            "unsafe_prod_request": "guardrail",
            "bad_context": "code",
            "invalid_salesforce_assumption": "core_knowledge",
            "stale_state": "queue_policy",
        }.get(failure_class, "code")
        return "developer_review", review_type
    return "report_only", ""


def quality_for_group(failure_class: str, recurrence: int, *, deterministic: bool = False) -> tuple[str, str]:
    if failure_class in {"queue_policy_skip", "noise"}:
        return "report_only", "Queue policy or noisy evidence is report-only unless it exposes a repair gap."
    if deterministic:
        return "high", "High-confidence deterministic helper or guardrail failure."
    if recurrence >= 3:
        return "high", f"Repeated across {recurrence} matching signals."
    if recurrence >= 2:
        return "medium", f"Repeated across {recurrence} matching signals."
    return "low", "Single signal or weak recurrence; keep report-only."


def knowledge_root(outputs: Path) -> Path:
    return outputs / "org-knowledge"


def _load_json(path: Path, default: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(default)
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_decision_artifact(
    outputs: Path,
    *,
    issue_key: str,
    decision_type: str,
    belief: str,
    evidence: list[str],
    action_or_refusal: str,
    next_need: str,
    failure_class: str,
    source: str,
    related_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    clean_evidence = [redact_text(item) for item in evidence[:12]]
    payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "artifact_id": f"{safe_slug(issue_key, '__global__')}-{safe_slug(decision_type, 'decision')}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        "decision_type": safe_slug(decision_type, "decision"),
        "belief": redact_text(belief),
        "evidence": clean_evidence,
        "action_or_refusal": redact_text(action_or_refusal),
        "next_need": redact_text(next_need),
        "failure_class": failure_class if failure_class in FAILURE_CLASSES else "noise",
        "issue_key": issue_key or "__global__",
        "source": redact_text(source),
        "related_artifacts": [redact_text(item) for item in (related_artifacts or [])[:12]],
        "redaction_status": redaction_status_for_text(json.dumps({
            "belief": belief,
            "evidence": evidence,
            "action_or_refusal": action_or_refusal,
            "next_need": next_need,
            "source": source,
            "related_artifacts": related_artifacts or [],
        }, ensure_ascii=False)),
        "created_at": utc_now_iso(),
    }
    if contains_secret(json.dumps(payload, ensure_ascii=False)):
        raise ValueError("Decision artifact contains secret-like content")
    path = knowledge_root(outputs) / "decision-artifacts" / f"{payload['artifact_id']}.json"
    _write_json(path, payload)
    return payload


def _read_json_files(directory: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not directory.exists():
        return items
    for path in sorted(directory.glob("*.json")):
        data = _load_json(path, {})
        if isinstance(data, dict):
            data["_source_path"] = str(path)
            items.append(data)
    return items


def _core_index() -> dict[str, Any]:
    data = _load_json(CORE_KNOWLEDGE_ROOT / "index.json", DEFAULT_RUNTIME_INDEX)
    return data if isinstance(data, dict) else copy.deepcopy(DEFAULT_RUNTIME_INDEX)


def _core_manifest() -> dict[str, Any]:
    data = _load_json(CORE_KNOWLEDGE_ROOT / "manifest.json", {})
    return data if isinstance(data, dict) else {}


def _core_files() -> list[Path]:
    if not CORE_KNOWLEDGE_ROOT.exists():
        return []
    return sorted(
        path for path in CORE_KNOWLEDGE_ROOT.rglob("*")
        if path.is_file() and path.name not in {"manifest.json"}
    )


def knowledge_type_for_rel(rel_path: str) -> str:
    manifest = _core_manifest()
    items = manifest.get("items") if isinstance(manifest.get("items"), dict) else {}
    item = items.get(rel_path)
    if isinstance(item, dict) and isinstance(item.get("type"), str):
        return item["type"]
    if rel_path == "run-rules.md":
        return "guardrail_rule"
    if rel_path == "helper-scripts.md" or rel_path == "helper-contract.md":
        return "helper_contract"
    if rel_path.startswith("query-patterns/"):
        return "query_pattern"
    if rel_path.startswith("deploy-patterns/"):
        return "deploy_pattern"
    if rel_path.startswith("salesforce-gotchas/") or rel_path.startswith("local-gotchas/"):
        return "gotcha"
    if rel_path.startswith("org-profile/"):
        return "org_convention"
    if rel_path.startswith("accepted-lessons/") or rel_path.startswith("lessons-learned/"):
        return "lesson_learned"
    return "gotcha"


def _merge_index(runtime_index: dict[str, Any], core_index: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if not isinstance(runtime_index, dict):
        return copy.deepcopy(core_index), True

    merged = copy.deepcopy(runtime_index)
    changed = False
    for key in ("version", "description", "max_context_chars", "max_context_chars_per_file", "max_topic_files"):
        if key not in merged and key in core_index:
            merged[key] = copy.deepcopy(core_index.get(key))
            changed = True

    always = merged.get("always_read")
    if not isinstance(always, list):
        always = []
        merged["always_read"] = always
        changed = True
    for rel in core_index.get("always_read", []):
        if isinstance(rel, str) and rel not in always:
            always.append(rel)
            changed = True

    topics = merged.get("topics")
    if not isinstance(topics, list):
        topics = []
        merged["topics"] = topics
        changed = True

    existing_by_id = {
        topic.get("id"): topic
        for topic in topics
        if isinstance(topic, dict) and isinstance(topic.get("id"), str)
    }
    for core_topic in core_index.get("topics", []):
        if not isinstance(core_topic, dict) or not isinstance(core_topic.get("id"), str):
            continue
        existing = existing_by_id.get(core_topic["id"])
        if not existing:
            topics.append(copy.deepcopy(core_topic))
            changed = True
            continue
        for key in ("title", "keywords", "files"):
            if key not in existing:
                existing[key] = copy.deepcopy(core_topic.get(key))
                changed = True
        for key in ("keywords", "files"):
            current = existing.get(key)
            if not isinstance(current, list):
                existing[key] = copy.deepcopy(core_topic.get(key, []))
                changed = True
                continue
            for item in core_topic.get(key, []):
                if item not in current:
                    current.append(item)
                    changed = True

    return merged, changed


def ensure_knowledge_defaults(outputs: Path) -> None:
    """Seed core knowledge and runtime dirs without overwriting appdata edits."""
    root = knowledge_root(outputs)
    root.mkdir(parents=True, exist_ok=True)
    for rel_dir in RUNTIME_DIRS:
        (root / rel_dir).mkdir(parents=True, exist_ok=True)

    core_index = _core_index()
    index_path = root / "index.json"
    if not index_path.exists():
        _write_json(index_path, core_index)
    else:
        existing = _load_json(index_path, {})
        merged, changed = _merge_index(existing if isinstance(existing, dict) else {}, core_index)
        if changed:
            _write_json(index_path, merged)

    for source in _core_files():
        rel = source.relative_to(CORE_KNOWLEDGE_ROOT)
        dest = root / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    readme = root / "org-profile" / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Org Profile Knowledge\n\n"
            "Store instance-specific Salesforce aliases, package notes, deployment conventions, and local exceptions here. "
            "Do not put secrets, access tokens, frontdoor links, or customer-private narrative in knowledge files.\n",
            encoding="utf-8",
        )


def read_runtime_index(outputs: Path) -> dict[str, Any]:
    ensure_knowledge_defaults(outputs)
    data = _load_json(knowledge_root(outputs) / "index.json", _core_index())
    return data if isinstance(data, dict) else _core_index()


def _search_text(key: str, row: dict[str, str], extra_text: str) -> str:
    parts = [key, row.get("Summary", ""), row.get("Status", ""), extra_text]
    return "\n".join(part for part in parts if part).lower()


def _add_selection(
    selected: dict[str, dict[str, Any]],
    rel_path: str,
    *,
    topic_id: str,
    reason: str,
    layer: str,
) -> None:
    entry = selected.setdefault(
        rel_path,
        {
            "topic_ids": [],
            "reasons": [],
            "layer": layer,
            "knowledge_type": knowledge_type_for_rel(rel_path),
        },
    )
    if topic_id and topic_id not in entry["topic_ids"]:
        entry["topic_ids"].append(topic_id)
    if reason and reason not in entry["reasons"]:
        entry["reasons"].append(reason)


def select_knowledge(
    outputs: Path,
    key: str,
    row: dict[str, str],
    extra_text: str,
) -> list[KnowledgeSelection]:
    """Select relevant active knowledge with reasons and layer labels."""
    index = read_runtime_index(outputs)
    root = knowledge_root(outputs)
    selected: dict[str, dict[str, Any]] = {}
    always_read = [rel for rel in index.get("always_read", []) if isinstance(rel, str)]
    always_set = set(always_read)
    for rel in always_read:
        _add_selection(selected, rel, topic_id="always_read", reason="always_read", layer=_layer_for_rel(rel))

    text = _search_text(key, row, extra_text)
    topic_scores: list[tuple[int, str, dict[str, Any], list[str]]] = []
    for topic in index.get("topics", []):
        if not isinstance(topic, dict):
            continue
        files = [rel for rel in topic.get("files", []) if isinstance(rel, str)]
        if not files:
            continue
        matched = [
            kw for kw in topic.get("keywords", [])
            if isinstance(kw, str) and kw.lower() in text
        ]
        if matched:
            topic_scores.append((len(matched), str(topic.get("id", "")), topic, matched[:8]))

    max_topic_files = int(index.get("max_topic_files") or 6)
    for _score, topic_id, topic, matched in sorted(topic_scores, key=lambda item: (-item[0], item[1])):
        reason = f"matched keywords: {', '.join(matched)}"
        for rel in [rel for rel in topic.get("files", []) if isinstance(rel, str)]:
            _add_selection(selected, rel, topic_id=topic_id, reason=reason, layer=_layer_for_rel(rel))
            topic_file_count = sum(1 for relpath in selected if relpath not in always_set)
            if topic_file_count >= max_topic_files:
                break
        topic_file_count = sum(1 for relpath in selected if relpath not in always_set)
        if topic_file_count >= max_topic_files:
            break

    accepted_lessons = _select_accepted_lessons(outputs, text)
    for lesson in accepted_lessons:
        rel = lesson.get("_rel_path")
        if isinstance(rel, str):
            _add_selection(
                selected,
                rel,
                topic_id=str(lesson.get("topic") or "accepted-lesson"),
                reason=str(lesson.get("_selection_reason") or "accepted lesson matched issue context"),
                layer="accepted-lessons",
            )

    selections: list[KnowledgeSelection] = []
    resolved_root = root.resolve()
    for rel, details in selected.items():
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        selections.append(KnowledgeSelection(
            path=candidate,
            rel_path=Path(rel).as_posix(),
            layer=str(details.get("layer") or _layer_for_rel(rel)),
            knowledge_type=str(details.get("knowledge_type") or knowledge_type_for_rel(rel)),
            topic_ids=tuple(details.get("topic_ids") or ()),
            reasons=tuple(details.get("reasons") or ()),
        ))
    return selections


def _select_accepted_lessons(outputs: Path, search_text: str, *, limit: int = 3) -> list[dict[str, Any]]:
    lessons: list[dict[str, Any]] = []
    for lesson in _read_json_files(knowledge_root(outputs) / "accepted-lessons"):
        status = str(lesson.get("status") or "").lower()
        if status not in LESSON_ACTIVE_STATUSES:
            continue
        haystack_parts = [
            str(lesson.get("topic") or ""),
            str(lesson.get("trigger") or ""),
            str(lesson.get("lesson") or ""),
            " ".join(str(item) for item in (lesson.get("keywords") or []) if isinstance(item, str)),
        ]
        haystack = " ".join(haystack_parts).lower()
        score = 0
        reasons: list[str] = []
        topic = str(lesson.get("topic") or "").lower()
        if topic and topic in search_text:
            score += 2
            reasons.append(f"matched accepted lesson topic: {topic}")
        for keyword in lesson.get("keywords") or []:
            if isinstance(keyword, str) and keyword.lower() in search_text:
                score += 1
                reasons.append(f"matched lesson keyword: {keyword}")
        if not score:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{4,}", haystack):
                if token.lower() in search_text:
                    score += 1
                    reasons.append(f"matched lesson term: {token}")
                    break
        if not score:
            continue
        source = Path(str(lesson.get("_source_path")))
        prompt_source = source.with_suffix(".md") if source.with_suffix(".md").exists() else source
        rel = prompt_source.relative_to(knowledge_root(outputs)).as_posix()
        lesson["_rel_path"] = rel
        lesson["_selection_score"] = score
        lesson["_selection_reason"] = "; ".join(reasons[:3])
        lessons.append(lesson)
    return sorted(lessons, key=lambda item: (-int(item.get("_selection_score") or 0), str(item.get("candidate_id") or "")))[:limit]


def _layer_for_rel(rel_path: str) -> str:
    if rel_path.startswith("org-profile/") or rel_path.startswith("local-gotchas/"):
        return "org-profile"
    if rel_path.startswith("accepted-lessons/") or rel_path.startswith("lessons-learned/"):
        return "accepted-lessons"
    return "core"


def selection_diagnostics(selections: list[KnowledgeSelection]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.rel_path,
            "layer": item.layer,
            "knowledge_type": item.knowledge_type,
            "topic_ids": list(item.topic_ids),
            "reasons": list(item.reasons),
            "signature": file_signature(item.path),
            "size": item.path.stat().st_size if item.path.exists() else 0,
        }
        for item in selections
    ]


def write_signal(
    outputs: Path,
    *,
    issue_key: str,
    run_id: str,
    source_step: str,
    signal_type: str,
    summary: str,
    evidence: list[str],
    topic: str = "",
    helper_available: str = "",
    knowledge_selected: list[str] | None = None,
    observed_at: str = "",
) -> dict[str, Any]:
    issue = safe_slug(issue_key, "issue")
    signal = safe_slug(signal_type, "signal")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    redacted_summary = redact_text(summary)
    redacted_evidence = [redact_text(item) for item in evidence[:12]]
    failure_class = classify_failure_class(signal_type, topic, " ".join([redacted_summary, *redacted_evidence]))
    route, developer_review_type = route_for_failure_class(failure_class, signal_type)
    quality, quality_reason = quality_for_group(failure_class, 1)
    if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES and quality in {"low", "report_only"}:
        quality = "medium"
        quality_reason = "Explicit high-value gotcha/deploy/validation signal is eligible for operator review."
    created_at = utc_now_iso()
    payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "signal_id": f"{issue}-{safe_slug(source_step, 'step')}-{timestamp}-{signal}",
        "issue_key": issue_key,
        "run_id": run_id,
        "source_step": source_step,
        "signal_type": signal_type,
        "topic": topic,
        "summary": redacted_summary,
        "evidence": redacted_evidence,
        "helper_available": helper_available,
        "knowledge_selected": knowledge_selected or [],
        "failure_class": failure_class,
        "route": route,
        "quality": quality,
        "quality_reason": quality_reason,
        "redaction_status": redaction_status_for_text(json.dumps({"summary": summary, "evidence": evidence}, ensure_ascii=False)),
        "observed_at": observed_at or created_at,
        "created_at": created_at,
    }
    if developer_review_type:
        payload["developer_review_type"] = developer_review_type
    validate_signal(payload)
    path = knowledge_root(outputs) / "signals" / f"{payload['signal_id']}.json"
    _write_json(path, payload)
    return payload


def validate_signal(payload: dict[str, Any]) -> None:
    required = ("signal_id", "issue_key", "run_id", "source_step", "signal_type", "summary", "evidence", "created_at")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"Signal missing required fields: {', '.join(missing)}")
    if payload.get("route") and payload["route"] not in ROUTES:
        raise ValueError("Signal has invalid route")
    if payload.get("quality") and payload["quality"] not in QUALITY_LABELS:
        raise ValueError("Signal has invalid quality")
    if payload.get("failure_class") and payload["failure_class"] not in FAILURE_CLASSES:
        raise ValueError("Signal has invalid failure_class")
    if payload.get("redaction_status") and payload["redaction_status"] not in REDACTION_STATUSES:
        raise ValueError("Signal has invalid redaction_status")
    if payload.get("developer_review_type") and payload["developer_review_type"] not in DEVELOPER_REVIEW_TYPES:
        raise ValueError("Signal has invalid developer_review_type")
    if contains_secret(json.dumps(payload, ensure_ascii=False)):
        raise ValueError("Signal contains secret-like content")


def validate_candidate(payload: dict[str, Any]) -> None:
    required = (
        "candidate_id",
        "source_signal_ids",
        "affected_issue_keys",
        "topic",
        "trigger",
        "lesson",
        "evidence",
        "knowledge_type",
        "org_specific",
        "confidence",
        "recurrence_count",
        "status",
    )
    missing = [field for field in required if payload.get(field) in (None, "", [])]
    if missing:
        raise ValueError(f"Lesson candidate missing required fields: {', '.join(missing)}")
    if payload.get("status") not in {"pending", "accepted", "active", "rejected", "retired"}:
        raise ValueError("Lesson candidate has invalid status")
    if payload.get("route") and payload["route"] not in ROUTES:
        raise ValueError("Lesson candidate has invalid route")
    if payload.get("quality") and payload["quality"] not in QUALITY_LABELS:
        raise ValueError("Lesson candidate has invalid quality")
    if payload.get("failure_class") and payload["failure_class"] not in FAILURE_CLASSES:
        raise ValueError("Lesson candidate has invalid failure_class")
    if payload.get("redaction_status") and payload["redaction_status"] not in REDACTION_STATUSES:
        raise ValueError("Lesson candidate has invalid redaction_status")
    if payload.get("developer_review_type") and payload["developer_review_type"] not in DEVELOPER_REVIEW_TYPES:
        raise ValueError("Lesson candidate has invalid developer_review_type")
    if payload.get("status") == "pending" and payload.get("quality") in {"low", "report_only"}:
        raise ValueError("Low/report-only candidates cannot be pending lessons")
    if contains_secret(json.dumps(payload, ensure_ascii=False)):
        raise ValueError("Lesson candidate contains secret-like content")


def validate_helper_work_item(payload: dict[str, Any]) -> None:
    required = (
        "work_item_id",
        "source_candidate_id",
        "topic",
        "summary",
        "lesson",
        "failure_class",
        "route",
        "quality",
        "redaction_status",
        "status",
    )
    missing = [field for field in required if payload.get(field) in (None, "", [])]
    if missing:
        raise ValueError(f"Helper work item missing required fields: {', '.join(missing)}")
    if payload.get("status") not in HELPER_WORK_STATUSES:
        raise ValueError("Helper work item has invalid status")
    if payload.get("route") != "helper_work_item":
        raise ValueError("Helper work item must use helper_work_item route")
    if payload.get("quality") not in QUALITY_LABELS:
        raise ValueError("Helper work item has invalid quality")
    if payload.get("failure_class") not in FAILURE_CLASSES:
        raise ValueError("Helper work item has invalid failure_class")
    if payload.get("redaction_status") not in REDACTION_STATUSES:
        raise ValueError("Helper work item has invalid redaction_status")
    if payload.get("status") == "implemented" and not payload.get("implementation_reference"):
        raise ValueError("Implemented helper work items require an implementation_reference")
    if payload.get("status") == "verified" and not payload.get("verification_reference"):
        raise ValueError("Verified helper work items require a verification_reference")
    if payload.get("status") == "retired" and not payload.get("retirement_reason"):
        raise ValueError("Retired helper work items require a retirement_reason")
    if contains_secret(json.dumps(payload, ensure_ascii=False)):
        raise ValueError("Helper work item contains secret-like content")


def _read_signal_files(outputs: Path) -> list[dict[str, Any]]:
    return _read_json_files(knowledge_root(outputs) / "signals")


LOG_SIGNAL_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "signal_type": "invalid_query_type",
        "topic": "salesforce-query",
        "needles": ("INVALID_TYPE", "Invalid type:"),
        "summary": "Salesforce query or metadata command hit an invalid type error.",
    },
    {
        "signal_type": "json_decode_error",
        "topic": "salesforce-cli-output",
        "needles": ("JSONDecodeError", "Expecting value: line 1 column"),
        "summary": "A command expected JSON output but received non-JSON output.",
    },
    {
        "signal_type": "invalid_sfdx_workspace",
        "topic": "deploy-command",
        "needles": ("InvalidProjectWorkspaceError", "does not contain a valid Salesforce DX project"),
        "summary": "Salesforce CLI command ran outside a valid Salesforce DX project workspace.",
    },
    {
        "signal_type": "missing_file_or_directory",
        "topic": "filesystem",
        "needles": ("No such file or directory", "cannot access", "not found"),
        "summary": "Pipeline command referenced a missing file, directory, or command.",
    },
)


def _classify_log_signal(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    for pattern in LOG_SIGNAL_PATTERNS:
        if any(str(needle).lower() in lowered for needle in pattern["needles"]):
            return pattern
    return None


def _iter_pipeline_log_records(
    outputs: Path,
    *,
    include_global: bool = True,
    line_cursors: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logs_dir = outputs / "pipeline-logs"
    scope = {
        "issue_logs_scanned": 0,
        "global_logs_scanned": 0,
        "global_logs_excluded_reason": "" if include_global else "Global queue logs excluded by caller.",
        "scan_started_at": utc_now_iso(),
        "scan_completed_at": "",
        "since_cursor": "",
        "until_cursor": "",
        "scope_limitations": [],
        "file_line_counts": {},
        "effective_line_cursors": {},
    }
    if not logs_dir.exists():
        scope["scope_limitations"].append("pipeline-logs directory does not exist")
        scope["scan_completed_at"] = utc_now_iso()
        return [], scope
    records: list[dict[str, Any]] = []
    cursors = line_cursors or {}
    for path in sorted(logs_dir.glob("*.jsonl")):
        is_global = path.name == "__global__.jsonl"
        if is_global and not include_global:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            scope["scope_limitations"].append(f"unable to read {path.name}")
            continue
        if is_global:
            scope["global_logs_scanned"] += 1
        else:
            scope["issue_logs_scanned"] += 1
        scope["file_line_counts"][path.name] = len(lines)
        cursor = max(0, int(cursors.get(path.name) or 0))
        if cursor > len(lines):
            scope["scope_limitations"].append(
                f"reset line cursor for truncated or rotated log: {path.name}"
            )
            cursor = 0
        scope["effective_line_cursors"][path.name] = cursor
        for line_no, line in enumerate(lines, start=1):
            if line_no <= cursor:
                continue
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "")
            if not text:
                continue
            records.append({
                "path": path,
                "is_global": is_global,
                "line_no": line_no,
                "ts": str(item.get("ts") or ""),
                "run_key": str(item.get("run_key") or path.stem),
                "text": text,
            })
    scope["scan_completed_at"] = utc_now_iso()
    return records, scope


def _write_log_signal_if_needed(outputs: Path, record: dict[str, Any], pattern: dict[str, Any]) -> bool:
    issue_key = safe_slug(str(record.get("run_key") or ""), "issue")
    signal_type = str(pattern["signal_type"])
    source_identity = "|".join([
        Path(str(record.get("path") or "")).name,
        str(record.get("line_no") or 0),
        str(record.get("ts") or ""),
        str(record.get("text") or ""),
    ])
    occurrence = hashlib.sha256(source_identity.encode("utf-8", errors="replace")).hexdigest()[:12]
    signal_id = f"{issue_key}-LOG-{safe_slug(signal_type)}-{occurrence}"
    path = knowledge_root(outputs) / "signals" / f"{signal_id}.json"
    if path.exists():
        return False
    evidence = str(record.get("text") or "")[:700]
    redacted_evidence = redact_text(evidence)
    redacted_source = redact_text(f"{Path(str(record.get('path') or '')).name}:{record.get('line_no') or 0}")
    failure_class = classify_failure_class(signal_type, str(pattern["topic"]), redacted_evidence)
    route, developer_review_type = route_for_failure_class(failure_class, signal_type)
    quality, quality_reason = quality_for_group(failure_class, 1)
    created_at = utc_now_iso()
    payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "signal_id": signal_id,
        "issue_key": issue_key,
        "run_id": issue_key,
        "source_step": "LOG",
        "signal_type": signal_type,
        "topic": str(pattern["topic"]),
        "summary": redact_text(str(pattern["summary"])),
        "evidence": [
            redacted_evidence,
            redacted_source,
        ],
        "helper_available": "",
        "knowledge_selected": [],
        "failure_class": failure_class,
        "route": route,
        "quality": quality,
        "quality_reason": quality_reason,
        "redaction_status": redaction_status_for_text(evidence),
        "observed_at": str(record.get("ts") or created_at),
        "source_log": Path(str(record.get("path") or "")).name,
        "source_line": int(record.get("line_no") or 0),
        "created_at": created_at,
    }
    if developer_review_type:
        payload["developer_review_type"] = developer_review_type
    validate_signal(payload)
    _write_json(path, payload)
    return True


def derive_signals_from_pipeline_logs(
    outputs: Path,
    *,
    max_created: int = 200,
    line_cursors: dict[str, int] | None = None,
    initialize_cursor_only: bool = False,
) -> dict[str, Any]:
    """Create deterministic signal artifacts from high-confidence pipeline log patterns."""
    ensure_knowledge_defaults(outputs)
    created = 0
    seen: set[tuple[str, str]] = set()
    records, scope = _iter_pipeline_log_records(outputs, line_cursors=line_cursors)
    next_cursors = dict(scope.get("effective_line_cursors") or {})
    if initialize_cursor_only:
        next_cursors.update({
            str(name): int(count)
            for name, count in (scope.get("file_line_counts") or {}).items()
        })
        scope["records_scanned"] = 0
        scope["signals_created"] = 0
        scope["next_log_cursors"] = next_cursors
        scope["cursor_initialized"] = True
        return scope
    records_scanned = 0
    for record in records:
        if created >= max_created:
            break
        records_scanned += 1
        path_name = Path(str(record.get("path") or "")).name
        next_cursors[path_name] = int(record.get("line_no") or 0)
        pattern = _classify_log_signal(str(record.get("text") or ""))
        if not pattern:
            continue
        issue_key = safe_slug(str(record.get("run_key") or ""), "issue")
        key = (issue_key, str(pattern["signal_type"]))
        if key in seen:
            continue
        seen.add(key)
        try:
            if _write_log_signal_if_needed(outputs, record, pattern):
                created += 1
        except ValueError:
            continue
    scope["records_scanned"] = records_scanned
    scope["signals_created"] = created
    scope["next_log_cursors"] = next_cursors
    scope["cursor_initialized"] = False
    return scope


def _read_auditor_state(outputs: Path) -> dict[str, Any]:
    state_path = knowledge_root(outputs) / "audit-reports" / "knowledge-auditor-state.json"
    data = _load_json(state_path, {"processed_signal_ids": [], "log_cursors": {}})
    return data if isinstance(data, dict) else {"processed_signal_ids": [], "log_cursors": {}}


def _candidate_exists(outputs: Path, source_signal_ids: list[str]) -> bool:
    target = set(source_signal_ids)
    for directory in ("pending-lessons", "accepted-lessons", "rejected-lessons"):
        for path in (knowledge_root(outputs) / directory).glob("*.json"):
            data = _load_json(path, {})
            if target == set(data.get("source_signal_ids") or []):
                return True
    for path in (knowledge_root(outputs) / "helper-work-items").glob("*.json"):
        data = _load_json(path, {})
        if target == set(data.get("source_signal_ids") or []):
            return True
    return False


def _semantic_key(signal_type: str, topic: str, route: str, discriminator: str = "") -> str:
    parts = [
        safe_slug(route, "report_only").lower(),
        safe_slug(signal_type, "unknown").lower(),
        safe_slug(topic, "general").lower(),
    ]
    if route != "helper_work_item" and discriminator:
        normalized = re.sub(r"\s+", " ", discriminator.strip().lower())
        parts.append(hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12])
    return ":".join(parts)


def _record_semantic_key(outputs: Path, record: dict[str, Any]) -> str:
    existing = str(record.get("semantic_key") or "").strip()
    if existing:
        return existing
    signals = _signals_for_candidate(outputs, record)
    signal_type, topic = _signal_type_topic_from_candidate(record, signals)
    route = str(record.get("route") or "")
    if not route:
        failure_class = str(record.get("failure_class") or "")
        route, _review_type = route_for_failure_class(failure_class, signal_type)
    discriminator = str(record.get("lesson") or record.get("trigger") or "")
    return _semantic_key(signal_type, topic, route, discriminator)


def _parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _merge_unique_strings(existing: Any, incoming: Any, *, limit: int | None = None) -> list[str]:
    merged: list[str] = []
    for value in [*(existing or []), *(incoming or [])]:
        text = str(value or "").strip()
        if text and text not in merged:
            merged.append(text)
        if limit is not None and len(merged) >= limit:
            break
    return merged


def _group_observed_after(group: list[dict[str, Any]], boundary: str) -> bool:
    boundary_dt = _parse_iso_datetime(boundary)
    if boundary_dt is None:
        return False
    for signal in group:
        observed = _parse_iso_datetime(str(signal.get("observed_at") or signal.get("created_at") or ""))
        if observed and observed > boundary_dt:
            return True
    return False


def _semantic_records(outputs: Path, semantic_key: str, route: str) -> list[tuple[Path, dict[str, Any]]]:
    root = knowledge_root(outputs)
    directories = ("helper-work-items",) if route == "helper_work_item" else (
        "pending-lessons",
        "accepted-lessons",
        "rejected-lessons",
    )
    matches: list[tuple[Path, dict[str, Any]]] = []
    for directory in directories:
        for path in sorted((root / directory).glob("*.json")):
            record = _load_json(path, {})
            if isinstance(record, dict) and record and _record_semantic_key(outputs, record) == semantic_key:
                matches.append((path, record))
    return matches


def _merge_or_reopen_semantic_record(
    outputs: Path,
    *,
    signal_type: str,
    topic: str,
    route: str,
    group: list[dict[str, Any]],
    evidence: list[str],
    issue_keys: list[str],
    semantic_key: str = "",
) -> str:
    """Merge a group into one semantic record and reopen only for newer evidence."""
    semantic_key = semantic_key or _semantic_key(signal_type, topic, route)
    matches = _semantic_records(outputs, semantic_key, route)
    if not matches:
        return ""

    status_rank = {
        "verified": 5,
        "implemented": 4,
        "accepted_for_work": 3,
        "pending": 2,
        "accepted": 2,
        "active": 2,
        "retired": 1,
        "rejected": 1,
    }
    path, record = sorted(
        matches,
        key=lambda item: (
            -status_rank.get(str(item[1].get("status") or "pending"), 0),
            str(item[1].get("created_at") or ""),
            str(item[0]),
        ),
    )[0]
    status = str(record.get("status") or "pending")
    terminal = status in {"retired", "rejected", "verified"}
    boundary = str(
        record.get("retired_at")
        or record.get("rejected_at")
        or record.get("verified_at")
        or ""
    )
    if terminal and not _group_observed_after(group, boundary):
        return "covered"

    updated = copy.deepcopy(record)
    if terminal:
        history = list(updated.get("resolution_history") or [])
        history.append({
            "status": status,
            "retired_at": updated.get("retired_at"),
            "rejected_at": updated.get("rejected_at"),
            "verified_at": updated.get("verified_at"),
            "retirement_reason": updated.get("retirement_reason"),
            "rejection_reason": updated.get("rejection_reason"),
            "implementation_reference": updated.get("implementation_reference"),
            "verification_reference": updated.get("verification_reference"),
        })
        updated["resolution_history"] = history
        updated["status"] = "pending"
        updated["reopened_at"] = utc_now_iso()
        updated["reopen_reason"] = "New evidence was observed after the previous resolution."
        for key in (
            "retired_at",
            "rejected_at",
            "verified_at",
            "retirement_reason",
            "rejection_reason",
            "implementation_reference",
            "verification_reference",
        ):
            updated.pop(key, None)

    source_ids = [str(item.get("signal_id") or "") for item in group]
    updated["source_signal_ids"] = _merge_unique_strings(updated.get("source_signal_ids"), source_ids)
    updated["affected_issue_keys"] = _merge_unique_strings(updated.get("affected_issue_keys"), issue_keys)
    updated["evidence"] = _merge_unique_strings(updated.get("evidence"), evidence, limit=20)
    updated["recurrence_count"] = len(updated["source_signal_ids"])
    updated["signal_type"] = signal_type
    updated["semantic_key"] = semantic_key
    updated["updated_at"] = utc_now_iso()
    updated.pop("_source_path", None)
    if route == "helper_work_item":
        validate_helper_work_item(updated)
    else:
        validate_candidate(updated)
    _write_json(path, updated)
    return "reopened" if terminal else "merged"


def _signals_for_candidate(outputs: Path, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for signal_id in candidate.get("source_signal_ids") or []:
        if not isinstance(signal_id, str) or not signal_id:
            continue
        signal = _load_json(knowledge_root(outputs) / "signals" / f"{safe_slug(signal_id)}.json", {})
        if isinstance(signal, dict) and signal:
            signals.append(signal)
    return signals


def _signal_type_topic_from_candidate(candidate: dict[str, Any], signals: list[dict[str, Any]]) -> tuple[str, str]:
    for signal in signals:
        signal_type = str(signal.get("signal_type") or "").strip()
        topic = str(signal.get("topic") or "").strip()
        if signal_type:
            return signal_type, topic or str(candidate.get("topic") or "general")
    candidate_id = str(candidate.get("candidate_id") or "")
    for pattern in LOG_SIGNAL_PATTERNS:
        signal_type = str(pattern["signal_type"])
        if signal_type in candidate_id:
            return signal_type, str(candidate.get("topic") or pattern.get("topic") or "general")
    return "", str(candidate.get("topic") or "general")


def _refine_lesson_candidate(signal_type: str, topic: str, group: list[dict[str, Any]]) -> LessonRefinement:
    """Turn raw grouped signals into review-ready lesson or helper decisions."""
    recurrence = len(group)
    summaries = [str(item.get("summary")) for item in group if item.get("summary")]
    if signal_type == "invalid_query_type":
        return LessonRefinement(
            action="helper_work_item",
            trigger="Repeated Salesforce INVALID_TYPE errors while querying data or metadata.",
            lesson=(
                "CaseOps should verify an object or metadata type exists before retrying after INVALID_TYPE. "
                "Use verify-sobject, sobject-fields, describe, EntityDefinition, or another focused helper check "
                "before broad SOQL retries. Treat absent optional or managed-package objects as investigation "
                "evidence, not as a pipeline failure, unless the issue depends on that package being installed."
            ),
            recommended_file="query-patterns/object-existence.md",
            knowledge_type="helper_contract",
            confidence="high" if recurrence >= 3 else "medium",
            keywords=("INVALID_TYPE", "EntityDefinition", "describe", "managed package", "sObject"),
            reason="This is a shared pipeline guardrail gap and should be fixed in core knowledge/helpers, not stored as org-local runtime knowledge.",
        )
    if signal_type == "invalid_sfdx_workspace":
        return LessonRefinement(
            action="helper_work_item",
            trigger="Repeated Salesforce CLI project commands ran outside a valid SFDX workspace.",
            lesson=(
                "CaseOps should run Salesforce project retrieve, deploy, and validate commands only inside an "
                "issue-scoped Salesforce DX workspace that contains sfdx-project.json. Initialize missing "
                "workspaces with scripts/sf_caseops_helper.py workspace-init or a guarded issue-scoped project "
                "workspace before raw sf project commands run."
            ),
            recommended_file="salesforce-gotchas/deploy-and-sandbox.md",
            knowledge_type="helper_contract",
            confidence="high" if recurrence >= 3 else "medium",
            keywords=("InvalidProjectWorkspaceError", "sfdx-project.json", "workspace-init", "sf project"),
            reason="This is a shared pipeline/runtime guardrail gap and should be fixed in core command routing, not stored as org-local runtime knowledge.",
        )
    if signal_type == "json_decode_error":
        return LessonRefinement(
            action="helper_work_item",
            trigger="Repeated CLI calls expected JSON but received non-JSON output.",
            lesson=(
                "CaseOps helpers should parse Salesforce CLI output defensively. When a command exits non-zero "
                "or prints non-JSON output, preserve the stderr/stdout excerpt and classify the failure instead "
                "of surfacing a raw JSONDecodeError."
            ),
            recommended_file="lessons-learned/general.md",
            knowledge_type="helper_contract",
            confidence="medium",
            keywords=("JSONDecodeError", "Expecting value", "non-JSON", "stderr", "stdout"),
            reason="This is a tooling robustness issue, so it should become helper work instead of runtime knowledge.",
        )
    if signal_type == "deploy_tooling_gotcha":
        return LessonRefinement(
            action="helper_work_item",
            trigger=f"Salesforce deploy tooling gotcha observed for {topic}.",
            lesson=_candidate_lesson_text(signal_type, topic, summaries),
            recommended_file="salesforce-gotchas/deploy-and-sandbox.md",
            knowledge_type="helper_contract",
            confidence="high" if recurrence >= 2 else "medium",
            keywords=tuple(_keywords_from_group(signal_type, topic, group)),
            reason="Deploy tooling gotchas are core helper behavior unless the operator explicitly promotes them as org-specific knowledge.",
        )
    if signal_type == "missing_file_or_directory":
        return LessonRefinement(
            action="suppress",
            trigger="Repeated missing file, directory, or command messages.",
            lesson=(
                "The grouped missing-file signals combine unrelated causes such as optional output checks, old "
                "paths, missing tools, and normal absence checks. Do not create a broad lesson from this bucket."
            ),
            recommended_file="lessons-learned/general.md",
            knowledge_type="lesson_learned",
            confidence="low",
            reason="Too broad and mixed-root-cause to be useful as accepted knowledge.",
        )
    if signal_type == "helper_failure":
        return LessonRefinement(
            action="helper_work_item",
            trigger=f"Repeated helper failure signal for {topic}.",
            lesson=f"When {topic} helper failures recur, inspect the helper failure_class and next_action before retrying ad hoc commands.",
            recommended_file=_recommended_file(signal_type, topic),
            knowledge_type="helper_contract",
            confidence="medium",
            reason="Helper failures are shared runtime contracts, not org-specific lessons.",
        )
    if signal_type == "invalid_query_field":
        return LessonRefinement(
            action="pending_lesson",
            trigger=f"Repeated invalid query field signal for {topic}.",
            lesson=f"When querying {topic} metadata or data, describe or verify fields first and use only returned fields.",
            recommended_file=_recommended_file(signal_type, topic),
            knowledge_type=_candidate_type(signal_type),
            confidence="medium",
        )
    if signal_type == "helper_available_not_used":
        return LessonRefinement(
            action="helper_work_item",
            trigger=f"Repeated helper available but not used signal for {topic}.",
            lesson=f"When a deterministic helper exists for {topic}, use it before equivalent raw Salesforce commands.",
            recommended_file=_recommended_file(signal_type, topic),
            knowledge_type="helper_contract",
            confidence="medium",
            reason="Helper bypass is a shared command-routing gap, not org-specific knowledge.",
        )
    if signal_type == "helper_related_failure":
        return LessonRefinement(
            action="suppress",
            trigger=f"Repeated helper related failure signal for {topic}.",
            lesson=(
                "A generic Claude or subprocess failure is not enough evidence of a deterministic helper defect. "
                "Create helper work only from a named helper command and a structured failure class."
            ),
            recommended_file="lessons-learned/general.md",
            knowledge_type="helper_contract",
            confidence="low",
            keywords=tuple(_keywords_from_group(signal_type, topic, group)),
            reason="Generic helper-related telemetry is too broad to produce actionable work.",
        )
    if signal_type == "invalid_command_pattern":
        return LessonRefinement(
            action="helper_work_item",
            trigger=f"Repeated invalid command pattern signal for {topic}.",
            lesson=(
                "CaseOps should route Salesforce queries, retrieves, deploys, and JSON API requests through "
                "the deterministic helper that owns their validation and structured failure contract."
            ),
            recommended_file="helper-scripts.md",
            knowledge_type="helper_contract",
            confidence="medium" if recurrence < 3 else "high",
            keywords=tuple(_keywords_from_group(signal_type, topic, group)),
            reason="Command bypass is a shared runtime guardrail gap, not org-specific knowledge.",
        )
    if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES:
        return LessonRefinement(
            action="pending_lesson",
            trigger=f"{signal_type.replace('_', ' ').title()} observed for {topic}.",
            lesson=_candidate_lesson_text(signal_type, topic, summaries),
            recommended_file=_recommended_file(signal_type, topic),
            knowledge_type=_candidate_type(signal_type),
            confidence="high" if recurrence >= 2 else "medium",
            keywords=tuple(_keywords_from_group(signal_type, topic, group)),
            reason="Explicit high-value CaseOps lesson signal; eligible for operator review even before recurrence reaches the default threshold.",
        )
    return LessonRefinement(
        action="pending_lesson",
        trigger=f"Repeated {signal_type.replace('_', ' ')} signal for {topic}.",
        lesson=_candidate_lesson_text(signal_type, topic, summaries),
        recommended_file=_recommended_file(signal_type, topic),
        knowledge_type=_candidate_type(signal_type),
        confidence="medium" if recurrence >= 2 else "low",
    )


def _candidate_contract_fields(signal_type: str, topic: str, group: list[dict[str, Any]], action: str) -> dict[str, Any]:
    text = " ".join(
        str(item.get("summary") or "") + " " + " ".join(str(ev) for ev in (item.get("evidence") or []))
        for item in group
    )
    failure_class = classify_failure_class(signal_type, topic, text)
    deterministic = action == "helper_work_item" or signal_type in {"invalid_query_type", "invalid_sfdx_workspace", "json_decode_error"}
    quality, quality_reason = quality_for_group(failure_class, len(group), deterministic=deterministic)
    route, developer_review_type = route_for_failure_class(failure_class, signal_type)
    if action == "pending_lesson":
        route = "org_lesson"
        developer_review_type = ""
        if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES and quality in {"low", "report_only"}:
            quality = "medium"
            quality_reason = "Explicit high-value gotcha/deploy/validation signal is eligible for operator review."
    elif action == "helper_work_item":
        route = "helper_work_item"
        developer_review_type = ""
    elif action == "suppress":
        route = "report_only"
        developer_review_type = ""
        quality = "report_only"
        quality_reason = "Suppressed by audit quality gate."
    fields = {
        "failure_class": failure_class,
        "route": route,
        "quality": quality,
        "quality_reason": quality_reason,
        "redaction_status": redaction_status_for_text(text),
    }
    if developer_review_type:
        fields["developer_review_type"] = developer_review_type
    return fields


def _keywords_from_group(signal_type: str, topic: str, group: list[dict[str, Any]], *, limit: int = 8) -> list[str]:
    words: list[str] = []
    seed_text = " ".join(
        [
            signal_type,
            topic,
            *[
                " ".join([str(item.get("summary") or ""), " ".join(str(ev) for ev in (item.get("evidence") or [])[:3])])
                for item in group
            ],
        ]
    )
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]{3,}\b", seed_text):
        if token.lower() in {"caseops", "salesforce", "metadata", "deploy", "query", "signal", "issue"}:
            continue
        if token not in words:
            words.append(token)
        if len(words) >= limit:
            break
    return words


def _group_meets_lesson_threshold(signal_type: str, group: list[dict[str, Any]], min_recurrence: int) -> tuple[bool, str]:
    if len(group) >= min_recurrence:
        return True, "recurrence"
    if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES | HIGH_VALUE_SINGLE_HELPER_TYPES and group:
        return True, "explicit_single_signal"
    return False, "below_recurrence"


def _normalize_existing_signals(outputs: Path) -> dict[str, Any]:
    """Backfill route/quality/failure contract fields for older signal files."""
    counts = {"normalized": 0, "blocked": 0}
    for path in sorted((knowledge_root(outputs) / "signals").glob("*.json")):
        signal = _load_json(path, {})
        if not isinstance(signal, dict) or not signal:
            continue
        signal_type = str(signal.get("signal_type") or "").strip() or "unknown"
        topic = str(signal.get("topic") or "").strip() or "general"
        summary = str(signal.get("summary") or "")
        evidence = [str(item) for item in (signal.get("evidence") or []) if item is not None]
        text = " ".join([summary, *evidence])
        failure_class = classify_failure_class(signal_type, topic, text)
        route, developer_review_type = route_for_failure_class(failure_class, signal_type)
        quality, quality_reason = quality_for_group(failure_class, 1)
        if signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES and quality in {"low", "report_only"}:
            quality = "medium"
            quality_reason = "Explicit high-value gotcha/deploy/validation signal is eligible for operator review."

        updated = copy.deepcopy(signal)
        changed = False
        defaults = {
            "schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "topic": topic,
            "observed_at": str(signal.get("created_at") or utc_now_iso()),
            "failure_class": failure_class,
            "route": route,
            "quality": quality,
            "quality_reason": quality_reason,
            "redaction_status": redaction_status_for_payload(signal),
        }
        if developer_review_type:
            defaults["developer_review_type"] = developer_review_type
        for key, value in defaults.items():
            should_override_legacy_high_value = (
                signal_type in HIGH_VALUE_SINGLE_LESSON_TYPES
                and key in {"failure_class", "route", "quality", "quality_reason"}
                and updated.get(key) != value
            )
            if updated.get(key) in (None, "", [], {}) or should_override_legacy_high_value:
                updated[key] = value
                changed = True
        if not changed:
            continue
        try:
            validate_signal(updated)
        except ValueError:
            counts["blocked"] += 1
            continue
        _write_json(path, updated)
        counts["normalized"] += 1
    return counts


def _refine_existing_pending_candidates(outputs: Path) -> dict[str, Any]:
    """Upgrade or retire pending candidates produced by older coarse audit logic."""
    counts = {
        "refined": 0,
        "converted_to_helper": 0,
        "suppressed": 0,
        "helper_work_item_ids": [],
    }
    pending_dir = knowledge_root(outputs) / "pending-lessons"
    for path in sorted(pending_dir.glob("*.json")):
        candidate = _load_json(path, {})
        if not isinstance(candidate, dict) or not candidate:
            continue
        signals = _signals_for_candidate(outputs, candidate)
        signal_type, topic = _signal_type_topic_from_candidate(candidate, signals)
        if not signal_type:
            continue
        group = signals or [{
            "summary": candidate.get("lesson") or "",
            "evidence": candidate.get("evidence") or [],
            "signal_type": signal_type,
            "topic": topic,
        }]
        refinement = _refine_lesson_candidate(signal_type, topic, group)
        updated = copy.deepcopy(candidate)
        updated.update({
            "topic": topic,
            "trigger": refinement.trigger,
            "lesson": refinement.lesson,
            "recommended_file": refinement.recommended_file,
            "knowledge_type": refinement.knowledge_type,
            "confidence": refinement.confidence,
            "risk": refinement.risk,
            "keywords": list(refinement.keywords),
            "refined_at": utc_now_iso(),
            "refinement_action": refinement.action,
            **_candidate_contract_fields(signal_type, topic, group, refinement.action),
        })
        if refinement.reason:
            updated["refinement_reason"] = refinement.reason
        if refinement.action == "pending_lesson":
            validate_candidate(updated)
            _write_json(path, updated)
            _write_candidate_markdown(outputs, updated)
            counts["refined"] += 1
            continue
        if refinement.action == "helper_work_item":
            helper = _helper_work_item_from_candidate(updated)
            helper["converted_at"] = utc_now_iso()
            _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(helper['work_item_id'])}.json", helper)
            counts["helper_work_item_ids"].append(helper["work_item_id"])
            rejected = copy.deepcopy(updated)
            rejected["status"] = "rejected"
            rejected["rejected_at"] = utc_now_iso()
            rejected["rejection_reason"] = refinement.reason or "Converted to helper work item."
            validate_candidate(rejected)
            _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{rejected['candidate_id']}.json", rejected)
            _write_candidate_markdown_in_dir(outputs, "rejected-lessons", rejected)
            _move_candidate_to_status(outputs, str(updated["candidate_id"]), "pending-lessons", delete_only=True)
            counts["converted_to_helper"] += 1
            continue
        if refinement.action == "suppress":
            rejected = copy.deepcopy(updated)
            rejected["status"] = "rejected"
            rejected["rejected_at"] = utc_now_iso()
            rejected["rejection_reason"] = refinement.reason or "Suppressed by lesson quality gate."
            validate_candidate(rejected)
            _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{rejected['candidate_id']}.json", rejected)
            _write_candidate_markdown_in_dir(outputs, "rejected-lessons", rejected)
            _move_candidate_to_status(outputs, str(updated["candidate_id"]), "pending-lessons", delete_only=True)
            counts["suppressed"] += 1
    return counts


def _refine_existing_accepted_lessons(outputs: Path) -> dict[str, Any]:
    """Improve or retire active lessons when deterministic refinement supersedes them."""
    counts = {"refined": 0, "retired": 0, "helper_work_item_ids": []}
    accepted_dir = knowledge_root(outputs) / "accepted-lessons"
    for path in sorted(accepted_dir.glob("*.json")):
        lesson = _load_json(path, {})
        if not isinstance(lesson, dict) or not lesson:
            continue
        status = str(lesson.get("status") or "").lower()
        if status not in LESSON_ACTIVE_STATUSES:
            continue
        signals = _signals_for_candidate(outputs, lesson)
        signal_type, topic = _signal_type_topic_from_candidate(lesson, signals)
        if not signal_type:
            continue
        group = signals or [{
            "summary": lesson.get("lesson") or "",
            "evidence": lesson.get("evidence") or [],
            "signal_type": signal_type,
            "topic": topic,
        }]
        refinement = _refine_lesson_candidate(signal_type, topic, group)
        if refinement.action == "helper_work_item":
            helper = _helper_work_item_from_candidate({
                **lesson,
                "topic": topic,
                "trigger": refinement.trigger,
                "lesson": refinement.lesson,
                "recommended_file": refinement.recommended_file,
                "knowledge_type": refinement.knowledge_type,
                "confidence": refinement.confidence,
                "risk": refinement.risk,
                "keywords": list(refinement.keywords),
                **_candidate_contract_fields(signal_type, topic, group, refinement.action),
            })
            _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(helper['work_item_id'])}.json", helper)
            retired = copy.deepcopy(lesson)
            retired["status"] = "retired"
            retired["retired_at"] = utc_now_iso()
            retired["retirement_reason"] = refinement.reason or "Superseded by core CaseOps knowledge/guardrails."
            retired["refined_at"] = utc_now_iso()
            retired["refinement_action"] = refinement.action
            retired.update(_candidate_contract_fields(signal_type, topic, group, refinement.action))
            validate_candidate(retired)
            _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{retired['candidate_id']}.json", retired)
            _write_candidate_markdown_in_dir(outputs, "rejected-lessons", retired)
            _move_candidate_to_status(outputs, str(retired["candidate_id"]), "accepted-lessons", delete_only=True)
            counts["retired"] += 1
            counts["helper_work_item_ids"].append(helper["work_item_id"])
            continue
        if refinement.action == "suppress":
            retired = copy.deepcopy(lesson)
            retired["status"] = "retired"
            retired["retired_at"] = utc_now_iso()
            retired["retirement_reason"] = refinement.reason or "Superseded by current lesson quality gates."
            retired["refined_at"] = utc_now_iso()
            retired["refinement_action"] = refinement.action
            retired.update(_candidate_contract_fields(signal_type, topic, group, refinement.action))
            validate_candidate(retired)
            _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{retired['candidate_id']}.json", retired)
            _write_candidate_markdown_in_dir(outputs, "rejected-lessons", retired)
            _move_candidate_to_status(outputs, str(retired["candidate_id"]), "accepted-lessons", delete_only=True)
            counts["retired"] += 1
            continue
        if refinement.action != "pending_lesson":
            continue
        if str(lesson.get("lesson") or "") == refinement.lesson and str(lesson.get("confidence") or "") == refinement.confidence:
            continue
        updated = copy.deepcopy(lesson)
        updated.update({
            "topic": topic,
            "trigger": refinement.trigger,
            "lesson": refinement.lesson,
            "recommended_file": refinement.recommended_file,
            "knowledge_type": refinement.knowledge_type,
            "confidence": refinement.confidence,
            "risk": refinement.risk,
            "keywords": list(refinement.keywords),
            "refined_at": utc_now_iso(),
            "refinement_action": refinement.action,
            **_candidate_contract_fields(signal_type, topic, group, refinement.action),
        })
        validate_candidate(updated)
        _write_json(path, updated)
        _write_candidate_markdown_in_dir(outputs, "accepted-lessons", updated)
        counts["refined"] += 1
    return counts


def _refine_existing_helper_work_items(outputs: Path) -> dict[str, Any]:
    """Normalize helper work items created before the route/quality contract."""
    counts = {"refined": 0}
    helper_dir = knowledge_root(outputs) / "helper-work-items"
    for path in sorted(helper_dir.glob("*.json")):
        helper = _load_json(path, {})
        if not isinstance(helper, dict) or not helper:
            continue
        signals = _signals_for_candidate(outputs, helper)
        pseudo_candidate = {
            "candidate_id": helper.get("source_candidate_id") or helper.get("work_item_id") or path.stem,
            "source_signal_ids": helper.get("source_signal_ids") or [],
            "topic": helper.get("topic") or "general",
            "lesson": helper.get("lesson") or helper.get("summary") or "",
        }
        signal_type, topic = _signal_type_topic_from_candidate(pseudo_candidate, signals)
        group = signals or [{
            "summary": helper.get("summary") or helper.get("lesson") or "",
            "evidence": helper.get("evidence") or [],
            "signal_type": signal_type or "helper_work_item",
            "topic": topic,
        }]
        contract_fields = _candidate_contract_fields(signal_type or "helper_work_item", topic, group, "helper_work_item")
        updated = copy.deepcopy(helper)
        updated["schema_version"] = int(updated.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION)
        updated["topic"] = topic or str(updated.get("topic") or "general")
        updated["status"] = str(updated.get("status") or "pending")
        updated["created_at"] = str(updated.get("created_at") or utc_now_iso())
        updated["signal_type"] = signal_type or str(updated.get("signal_type") or "helper_work_item")
        updated["semantic_key"] = _semantic_key(updated["signal_type"], updated["topic"], "helper_work_item")
        for key, value in contract_fields.items():
            if updated.get(key) in (None, "", [], {}):
                updated[key] = value
        if updated != helper:
            validate_helper_work_item(updated)
            _write_json(path, updated)
            counts["refined"] += 1
    return counts


def _consolidate_existing_helper_work_items(outputs: Path) -> dict[str, Any]:
    """Keep one lifecycle record per semantic helper problem without deleting history."""
    helper_dir = knowledge_root(outputs) / "helper-work-items"
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(helper_dir.glob("*.json")):
        item = _load_json(path, {})
        if isinstance(item, dict) and item:
            records.append((path, item))

    grouped: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for path, item in records:
        grouped[_record_semantic_key(outputs, item)].append((path, item))

    status_rank = {
        "verified": 5,
        "implemented": 4,
        "accepted_for_work": 3,
        "pending": 2,
        "retired": 1,
    }
    consolidated = 0
    retired_duplicates = 0
    for semantic_key, matches in grouped.items():
        if len(matches) < 2:
            continue
        canonical_path, canonical = sorted(
            matches,
            key=lambda entry: (
                -status_rank.get(str(entry[1].get("status") or "pending"), 0),
                str(entry[1].get("created_at") or ""),
                str(entry[0]),
            ),
        )[0]
        duplicates_to_retire = [
            (path, item)
            for path, item in matches
            if path != canonical_path
            and not (
                str(item.get("status") or "") == "retired"
                and str(item.get("superseded_by") or "") == str(canonical.get("work_item_id") or "")
            )
        ]
        if not duplicates_to_retire:
            continue
        updated = copy.deepcopy(canonical)
        all_signals: list[dict[str, Any]] = []
        for _path, item in matches:
            updated["source_signal_ids"] = _merge_unique_strings(
                updated.get("source_signal_ids"), item.get("source_signal_ids")
            )
            updated["affected_issue_keys"] = _merge_unique_strings(
                updated.get("affected_issue_keys"), item.get("affected_issue_keys")
            )
            updated["evidence"] = _merge_unique_strings(updated.get("evidence"), item.get("evidence"), limit=20)
            item_signals = _signals_for_candidate(outputs, item)
            all_signals.extend(item_signals or [{"observed_at": item.get("created_at")}])

        canonical_status = str(updated.get("status") or "pending")
        if canonical_status == "verified" and _group_observed_after(all_signals, str(updated.get("verified_at") or "")):
            history = list(updated.get("resolution_history") or [])
            history.append({
                "status": "verified",
                "verified_at": updated.get("verified_at"),
                "implementation_reference": updated.get("implementation_reference"),
                "verification_reference": updated.get("verification_reference"),
            })
            updated["resolution_history"] = history
            updated["status"] = "pending"
            updated["reopened_at"] = utc_now_iso()
            updated["reopen_reason"] = "A duplicate record contained evidence observed after verification."
            updated.pop("verified_at", None)
            updated.pop("implementation_reference", None)
            updated.pop("verification_reference", None)

        updated["semantic_key"] = semantic_key
        updated["recurrence_count"] = len(updated.get("source_signal_ids") or [])
        updated["updated_at"] = utc_now_iso()
        validate_helper_work_item(updated)
        _write_json(canonical_path, updated)

        for duplicate_path, duplicate in duplicates_to_retire:
            retired = copy.deepcopy(duplicate)
            previous_status = str(retired.get("status") or "pending")
            retired["status"] = "retired"
            retired["retired_at"] = utc_now_iso()
            retired["retirement_reason"] = (
                f"Superseded by semantic helper work item {updated['work_item_id']}."
            )
            retired["superseded_by"] = updated["work_item_id"]
            retired["superseded_from_status"] = previous_status
            retired["semantic_key"] = semantic_key
            validate_helper_work_item(retired)
            _write_json(duplicate_path, retired)
            retired_duplicates += 1
        consolidated += 1

    return {"consolidated": consolidated, "retired_duplicates": retired_duplicates}


def run_manual_audit(outputs: Path, *, min_recurrence: int = 2) -> dict[str, Any]:
    """Review signal/log artifacts and create pending lesson/helper candidates."""
    ensure_knowledge_defaults(outputs)
    started_at = utc_now_iso()
    signal_normalization = _normalize_existing_signals(outputs)
    pending_refinement = _refine_existing_pending_candidates(outputs)
    accepted_refinement = _refine_existing_accepted_lessons(outputs)
    helper_refinement = _refine_existing_helper_work_items(outputs)
    helper_consolidation = _consolidate_existing_helper_work_items(outputs)
    state_path = knowledge_root(outputs) / "audit-reports" / "knowledge-auditor-state.json"
    state = _read_auditor_state(outputs)
    existing_signals = any((knowledge_root(outputs) / "signals").glob("*.json"))
    initialize_cursor_only = state_path.exists() and "log_cursors" not in state and existing_signals
    log_scope = derive_signals_from_pipeline_logs(
        outputs,
        line_cursors=state.get("log_cursors") if isinstance(state.get("log_cursors"), dict) else {},
        initialize_cursor_only=initialize_cursor_only,
    )
    log_signals_created = int(log_scope.get("signals_created") or 0)
    processed = set(state.get("processed_signal_ids") or [])
    signals = [item for item in _read_signal_files(outputs) if item.get("signal_id") not in processed]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[(str(signal.get("signal_type") or "unknown"), str(signal.get("topic") or "general"))].append(signal)

    candidates: list[dict[str, Any]] = []
    helper_items: list[dict[str, Any]] = []
    existing_candidate_groups = 0
    suppressed_groups = 0
    helper_only_groups = 0
    below_threshold_details: list[dict[str, Any]] = []
    helper_only_details: list[dict[str, Any]] = []
    suppressed_details: list[dict[str, Any]] = []
    consumed_signal_ids: set[str] = set()
    for (signal_type, topic), group in grouped.items():
        eligible, eligibility_reason = _group_meets_lesson_threshold(signal_type, group, min_recurrence)
        if not eligible:
            below_threshold_details.append({
                "signal_type": signal_type,
                "topic": topic,
                "count": len(group),
                "reason": eligibility_reason,
            })
            continue
        source_ids = [str(item.get("signal_id")) for item in group if item.get("signal_id")]
        if not source_ids:
            continue
        if _candidate_exists(outputs, source_ids):
            existing_candidate_groups += 1
            consumed_signal_ids.update(source_ids)
            continue
        issue_keys = sorted({str(item.get("issue_key")) for item in group if item.get("issue_key")})
        summaries = [str(item.get("summary")) for item in group if item.get("summary")]
        evidence = []
        for item in group:
            for ev in item.get("evidence") or []:
                if isinstance(ev, str) and ev not in evidence:
                    evidence.append(ev)
                if len(evidence) >= 8:
                    break
        refinement = _refine_lesson_candidate(signal_type, topic, group)
        contract_fields = _candidate_contract_fields(signal_type, topic, group, refinement.action)
        semantic_result = _merge_or_reopen_semantic_record(
            outputs,
            signal_type=signal_type,
            topic=topic,
            route=str(contract_fields.get("route") or "report_only"),
            group=group,
            evidence=evidence or summaries[:5],
            issue_keys=issue_keys,
            semantic_key=_semantic_key(signal_type, topic, str(contract_fields.get("route") or "report_only"), refinement.lesson),
        )
        if semantic_result:
            existing_candidate_groups += 1
            consumed_signal_ids.update(source_ids)
            continue
        candidate = {
            "schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "candidate_id": f"lesson-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{safe_slug(signal_type)}-{safe_slug(topic)}",
            "source_signal_ids": source_ids,
            "affected_issue_keys": issue_keys,
            "topic": topic,
            "signal_type": signal_type,
            "semantic_key": _semantic_key(
                signal_type,
                topic,
                str(contract_fields.get("route") or "report_only"),
                refinement.lesson,
            ),
            "trigger": refinement.trigger,
            "lesson": refinement.lesson,
            "evidence": evidence or summaries[:5],
            "recommended_file": refinement.recommended_file,
            "knowledge_type": refinement.knowledge_type,
            "org_specific": False,
            "confidence": refinement.confidence,
            "recurrence_count": len(group),
            "risk": refinement.risk,
            "keywords": list(refinement.keywords),
            **contract_fields,
            "created_at": utc_now_iso(),
            "status": "pending",
            "eligibility_reason": eligibility_reason,
        }
        if refinement.reason:
            candidate["refinement_reason"] = refinement.reason
        if refinement.action == "suppress":
            suppressed_groups += 1
            suppressed_details.append({
                "signal_type": signal_type,
                "topic": topic,
                "count": len(group),
                "reason": refinement.reason or "Suppressed by audit quality gate.",
            })
            consumed_signal_ids.update(source_ids)
            continue
        if refinement.action == "helper_work_item":
            candidate["status"] = "rejected"
            validate_candidate(candidate)
            helper = _helper_work_item_from_candidate(candidate)
            _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(helper['work_item_id'])}.json", helper)
            write_decision_artifact(
                outputs,
                issue_key="__global__",
                decision_type="helper_work_item_created",
                belief=f"{signal_type} for {topic} should become deterministic helper work.",
                evidence=[f"signals={len(group)}", f"work_item_id={helper['work_item_id']}"],
                action_or_refusal="Created helper work item; did not create pending lesson.",
                next_need="Developer reviews and implements helper/code change.",
                failure_class=str(candidate.get("failure_class") or "missing_helper"),
                source="knowledge_auditor",
                related_artifacts=[f"org-knowledge/helper-work-items/{helper_work_filename(helper['work_item_id'])}.json"],
            )
            helper_items.append(helper)
            helper_only_groups += 1
            helper_only_details.append({
                "signal_type": signal_type,
                "topic": topic,
                "count": len(group),
                "reason": refinement.reason or "Routed to helper work item.",
                "work_item_id": helper["work_item_id"],
            })
            consumed_signal_ids.update(source_ids)
            continue
        if str(candidate.get("quality") or "") in {"low", "report_only"}:
            # Pending lessons must be medium/high quality (validate_candidate rejects
            # low/report_only); treat these groups as suppressed instead of aborting
            # the whole audit run.
            suppressed_groups += 1
            suppressed_details.append({
                "signal_type": signal_type,
                "topic": topic,
                "count": len(group),
                "reason": str(candidate.get("quality_reason") or "Low/report-only quality; not eligible as a pending lesson."),
            })
            consumed_signal_ids.update(source_ids)
            continue
        validate_candidate(candidate)
        _write_json(knowledge_root(outputs) / "pending-lessons" / f"{candidate['candidate_id']}.json", candidate)
        _write_candidate_markdown(outputs, candidate)
        write_decision_artifact(
            outputs,
            issue_key="__global__",
            decision_type="pending_lesson_created",
            belief=f"{signal_type} for {topic} is a reusable org lesson candidate.",
            evidence=[f"signals={len(group)}", f"candidate_id={candidate['candidate_id']}"],
            action_or_refusal="Created pending lesson for operator review.",
            next_need="Operator accepts, rejects, or converts the candidate.",
            failure_class=str(candidate.get("failure_class") or "noise"),
            source="knowledge_auditor",
            related_artifacts=[f"org-knowledge/pending-lessons/{candidate['candidate_id']}.json"],
        )
        candidates.append(candidate)
        consumed_signal_ids.update(source_ids)

    processed.update(consumed_signal_ids)
    state_payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "last_run_at": utc_now_iso(),
        "processed_signal_ids": sorted(processed),
        "log_cursors": dict(log_scope.get("next_log_cursors") or state.get("log_cursors") or {}),
    }
    _write_json(knowledge_root(outputs) / "audit-reports" / "knowledge-auditor-state.json", state_payload)

    audit_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "audit_id": audit_id,
        "started_at": started_at,
        "completed_at": utc_now_iso(),
        "issue_logs_scanned": int(log_scope.get("issue_logs_scanned") or 0),
        "global_logs_scanned": int(log_scope.get("global_logs_scanned") or 0),
        "global_logs_excluded_reason": str(log_scope.get("global_logs_excluded_reason") or ""),
        "scan_started_at": str(log_scope.get("scan_started_at") or ""),
        "scan_completed_at": str(log_scope.get("scan_completed_at") or ""),
        "since_cursor": str(log_scope.get("since_cursor") or ""),
        "until_cursor": str(log_scope.get("until_cursor") or ""),
        "scope_limitations": list(log_scope.get("scope_limitations") or []),
        "redaction_status": "not_needed",
        "signals_reviewed": len(signals),
        "signals_considered": len(signals),
        "signals_skipped": max(0, len(signals) - len(consumed_signal_ids)),
        "signals_normalized": signal_normalization["normalized"],
        "signals_normalization_blocked": signal_normalization["blocked"],
        "log_signals_created": log_signals_created,
        "signals_consumed": len(consumed_signal_ids),
        "groups_considered": len(grouped),
        "below_threshold_groups": len(below_threshold_details),
        "below_threshold_details": below_threshold_details,
        "existing_candidate_groups": existing_candidate_groups,
        "suppressed_groups": suppressed_groups,
        "suppressed_group_details": suppressed_details,
        "helper_only_groups": helper_only_groups,
        "helper_only_group_details": helper_only_details,
        "pending_lessons_refined": pending_refinement["refined"],
        "pending_lessons_converted_to_helper": pending_refinement["converted_to_helper"],
        "pending_lessons_suppressed": pending_refinement["suppressed"],
        "accepted_lessons_refined": accepted_refinement["refined"],
        "accepted_lessons_retired": accepted_refinement["retired"],
        "helper_work_items_refined": helper_refinement["refined"],
        "helper_work_item_groups_consolidated": helper_consolidation["consolidated"],
        "helper_work_item_duplicates_retired": helper_consolidation["retired_duplicates"],
        "candidates_created": len(candidates),
        "helper_work_items_created": len(helper_items) + int(pending_refinement["converted_to_helper"]) + len(accepted_refinement["helper_work_item_ids"]),
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "helper_work_item_ids": [item["work_item_id"] for item in helper_items] + list(pending_refinement["helper_work_item_ids"]) + list(accepted_refinement["helper_work_item_ids"]),
        "report_path": f"org-knowledge/audit-reports/audit-summary-{audit_id}.md",
    }
    _write_json(knowledge_root(outputs) / "audit-reports" / f"audit-summary-{audit_id}.json", summary)
    _write_audit_markdown(outputs, audit_id, summary, candidates, helper_items)
    return summary


def list_review_items(outputs: Path) -> dict[str, Any]:
    ensure_knowledge_defaults(outputs)
    root = knowledge_root(outputs)
    helper_items = _read_json_files(root / "helper-work-items")
    active_helper_items = [item for item in helper_items if str(item.get("status") or "pending") != "retired"]
    retired_helper_items = [item for item in helper_items if str(item.get("status") or "pending") == "retired"]
    return {
        "pending_lessons": _public_items(_read_json_files(root / "pending-lessons")),
        "accepted_lessons": _public_items(_read_json_files(root / "accepted-lessons")),
        "rejected_lessons": _public_items(_read_json_files(root / "rejected-lessons")),
        "helper_work_items": _public_items(active_helper_items),
        "retired_helper_work_items": _public_items(retired_helper_items),
        "signals": _public_items(_read_json_files(root / "signals")[-100:]),
        "audit_reports": sorted(path.name for path in (root / "audit-reports").glob("audit-summary-*.json"))[-20:],
    }


def _public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in items:
        copy_item = {key: value for key, value in item.items() if not key.startswith("_")}
        source = item.get("_source_path")
        if source:
            copy_item["source_path"] = source
        public.append(copy_item)
    return public


def accept_lesson(outputs: Path, candidate_id: str) -> dict[str, Any]:
    candidate = _load_candidate(outputs, "pending-lessons", candidate_id)
    updated = copy.deepcopy(candidate)
    updated["status"] = "accepted"
    updated["accepted_at"] = utc_now_iso()
    validate_candidate(updated)
    _write_json(knowledge_root(outputs) / "accepted-lessons" / f"{candidate_id}.json", updated)
    _write_candidate_markdown_in_dir(outputs, "accepted-lessons", updated)
    _move_candidate_to_status(outputs, candidate_id, "pending-lessons", delete_only=True)
    return updated


def reject_lesson(outputs: Path, candidate_id: str, *, reason: str = "") -> dict[str, Any]:
    candidate = _load_candidate(outputs, "pending-lessons", candidate_id)
    updated = copy.deepcopy(candidate)
    updated["status"] = "rejected"
    updated["rejected_at"] = utc_now_iso()
    updated["rejection_reason"] = redact_text(reason)
    validate_candidate(updated)
    _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{candidate_id}.json", updated)
    _write_candidate_markdown_in_dir(outputs, "rejected-lessons", updated)
    _move_candidate_to_status(outputs, candidate_id, "pending-lessons", delete_only=True)
    return updated


def retire_lesson(outputs: Path, candidate_id: str, *, reason: str = "") -> dict[str, Any]:
    lesson = _load_candidate(outputs, "accepted-lessons", candidate_id)
    updated = copy.deepcopy(lesson)
    updated["status"] = "retired"
    updated["retired_at"] = utc_now_iso()
    updated["retirement_reason"] = redact_text(reason)
    validate_candidate(updated)
    _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{candidate_id}.json", updated)
    _write_candidate_markdown_in_dir(outputs, "rejected-lessons", updated)
    _move_candidate_to_status(outputs, candidate_id, "accepted-lessons", delete_only=True)
    return updated


def convert_to_helper_work_item(outputs: Path, candidate_id: str) -> dict[str, Any]:
    candidate = _load_candidate(outputs, "pending-lessons", candidate_id)
    helper = _helper_work_item_from_candidate(candidate)
    helper["converted_at"] = utc_now_iso()
    validate_helper_work_item(helper)
    _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(helper['work_item_id'])}.json", helper)
    rejected = copy.deepcopy(candidate)
    rejected["status"] = "rejected"
    rejected["rejected_at"] = utc_now_iso()
    rejected["rejection_reason"] = "Converted to helper work item."
    rejected["refinement_action"] = "helper_work_item"
    validate_candidate(rejected)
    _write_json(knowledge_root(outputs) / "rejected-lessons" / f"{candidate_id}.json", rejected)
    _write_candidate_markdown_in_dir(outputs, "rejected-lessons", rejected)
    _move_candidate_to_status(outputs, candidate_id, "pending-lessons", delete_only=True)
    write_decision_artifact(
        outputs,
        issue_key="__global__",
        decision_type="pending_lesson_converted_to_helper",
        belief="Pending lesson represents mechanical helper/code work rather than active prompt knowledge.",
        evidence=[f"candidate_id={candidate_id}", f"work_item_id={helper['work_item_id']}"],
        action_or_refusal="Created helper work item and closed pending lesson lifecycle.",
        next_need="Developer reviews helper work item.",
        failure_class=str(helper.get("failure_class") or "missing_helper"),
        source="knowledge_review",
        related_artifacts=[
            f"org-knowledge/helper-work-items/{helper_work_filename(helper['work_item_id'])}.json",
            f"org-knowledge/rejected-lessons/{candidate_id}.json",
        ],
    )
    return helper


def update_helper_work_item_status(
    outputs: Path,
    work_item_id: str,
    status: str,
    *,
    reference: str = "",
    reason: str = "",
) -> dict[str, Any]:
    clean_status = str(status or "").strip().lower()
    if clean_status not in HELPER_WORK_STATUSES:
        raise ValueError("Invalid helper work item status")

    item = _load_helper_work_item(outputs, work_item_id)
    current_status = str(item.get("status") or "pending")
    if current_status not in HELPER_WORK_STATUSES:
        current_status = "pending"
    if clean_status != current_status and clean_status not in HELPER_WORK_TRANSITIONS[current_status]:
        raise ValueError(f"Invalid helper work item transition: {current_status} -> {clean_status}")

    updated = copy.deepcopy(item)
    now = utc_now_iso()
    updated["status"] = clean_status
    if clean_status == "accepted_for_work":
        updated["accepted_for_work_at"] = now
        if reason:
            updated["acceptance_note"] = redact_text(reason)
    elif clean_status == "implemented":
        clean_reference = redact_text(reference.strip())
        if not clean_reference:
            raise ValueError("implementation_reference is required")
        updated["implemented_at"] = now
        updated["implementation_reference"] = clean_reference
    elif clean_status == "verified":
        clean_reference = redact_text(reference.strip())
        if not clean_reference:
            raise ValueError("verification_reference is required")
        updated["verified_at"] = now
        updated["verification_reference"] = clean_reference
    elif clean_status == "retired":
        clean_reason = redact_text(reason.strip())
        if not clean_reason:
            raise ValueError("retirement_reason is required")
        updated["retired_at"] = now
        updated["retirement_reason"] = clean_reason

    validate_helper_work_item(updated)
    _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(work_item_id)}.json", updated)
    write_decision_artifact(
        outputs,
        issue_key="__global__",
        decision_type="helper_work_item_status_changed",
        belief="Helper work item lifecycle changed.",
        evidence=[
            f"work_item_id={work_item_id}",
            f"from={current_status}",
            f"to={clean_status}",
            f"reference={reference}" if reference else "",
            f"reason={reason}" if reason else "",
        ],
        action_or_refusal=f"Updated helper work item status from {current_status} to {clean_status}.",
        next_need=_helper_work_item_next_need(clean_status),
        failure_class=str(updated.get("failure_class") or "missing_helper"),
        source="knowledge_review",
        related_artifacts=[f"org-knowledge/helper-work-items/{helper_work_filename(work_item_id)}.json"],
    )
    return updated


def _helper_work_item_next_need(status: str) -> str:
    if status == "accepted_for_work":
        return "Developer implements the referenced helper or guardrail fix."
    if status == "implemented":
        return "Operator verifies with a test, NAS audit, or observed run."
    if status == "verified":
        return "No further action unless the weakness recurs."
    if status == "retired":
        return "No further action."
    return "Operator decides whether to accept for work, retire, or leave pending."


def _load_helper_work_item(outputs: Path, work_item_id: str) -> dict[str, Any]:
    path = knowledge_root(outputs) / "helper-work-items" / f"{helper_work_filename(work_item_id)}.json"
    data = _load_json(path, {})
    if not isinstance(data, dict) or not data:
        raise FileNotFoundError(f"Helper work item not found: {work_item_id}")
    if data.get("status") not in HELPER_WORK_STATUSES:
        data["status"] = "pending"
    validate_helper_work_item(data)
    return data


def _load_candidate(outputs: Path, directory: str, candidate_id: str) -> dict[str, Any]:
    candidate_path = knowledge_root(outputs) / directory / f"{safe_slug(candidate_id)}.json"
    data = _load_json(candidate_path, {})
    if not isinstance(data, dict) or not data:
        raise FileNotFoundError(f"Candidate not found: {candidate_id}")
    return data


def _move_candidate_to_status(outputs: Path, candidate_id: str, source_dir: str, *, delete_only: bool = False) -> None:
    root = knowledge_root(outputs)
    for ext in (".json", ".md"):
        source = root / source_dir / f"{safe_slug(candidate_id)}{ext}"
        if source.exists() and delete_only:
            source.unlink()


def _write_candidate_markdown_in_dir(outputs: Path, directory: str, candidate: dict[str, Any]) -> None:
    target = knowledge_root(outputs) / directory / f"{candidate['candidate_id']}.md"
    lines = [
        f"# {candidate.get('status', 'lesson').title()} Lesson: {candidate['candidate_id']}",
        "",
        f"- Topic: {candidate['topic']}",
        f"- Type: {candidate['knowledge_type']}",
        f"- Confidence: {candidate['confidence']}",
        f"- Recurrence: {candidate['recurrence_count']}",
        "",
        "## Lesson",
        "",
        str(candidate["lesson"]),
        "",
        "## Evidence",
        "",
    ]
    for item in candidate.get("evidence") or []:
        lines.append(f"- {item}")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def classify_guardrail_command(command: str, *, production_approved: bool = False) -> dict[str, Any]:
    lower = (command or "").lower()
    findings: list[dict[str, Any]] = []
    if "sfdx force:" in lower:
        findings.append({
            "rule": "legacy_sfdx_force",
            "severity": "block",
            "message": "Use modern sf CLI commands instead of legacy sfdx force:* commands.",
            "next_action": "Use scripts/sf_caseops_helper.py or equivalent sf command.",
        })
    if ("package.xml" in lower or "--manifest" in lower) and "operator approved" not in lower:
        findings.append({
            "rule": "routine_manifest_deploy",
            "severity": "warn",
            "message": "Routine CaseOps retrieve/deploy should avoid package.xml/--manifest unless an exception is approved.",
            "next_action": "Use --metadata, --source-dir, --metadata-dir, or CaseOps deploy helpers.",
        })
    if "sf project retrieve" in lower and "sf_caseops_helper.py" not in lower:
        findings.append({
            "rule": "raw_project_retrieve_without_helper",
            "severity": "block",
            "message": "Raw sf project retrieve is workspace-sensitive and has repeatedly failed outside valid SFDX projects.",
            "next_action": "Use `python scripts/sf_caseops_helper.py retrieve-metadata ...`; it creates an issue-scoped SFDX workspace and returns structured failure_class/next_action.",
        })
    if re.search(r"\bsf\s+project\s+deploy\s+start\b", lower) and "sf_caseops_helper.py" not in lower:
        findings.append({
            "rule": "raw_project_deploy_without_helper",
            "severity": "block",
            "message": "Raw sf project deploy is workspace-sensitive and bypasses CaseOps deploy summaries.",
            "next_action": "Use `python scripts/sf_caseops_helper.py deploy-source ...` or `deploy-mdapi ...` from an issue-scoped attempt workspace.",
        })
    if "sf data query" in lower and "sf_caseops_helper.py" not in lower:
        findings.append({
            "rule": "raw_soql_without_helper",
            "severity": "block",
            "message": "Raw sf data query bypasses CaseOps object/field prechecks and structured INVALID_TYPE handling.",
            "next_action": "Use `python scripts/sf_caseops_helper.py query-data ...` or `query-tooling ...`; verify unfamiliar objects first.",
        })
    raw_api_request = re.search(r"\bsf\s+api\s+request\s+rest\b", lower) and "sf_caseops_helper.py" not in lower
    api_method_match = re.search(r"(?:--method(?:=|\s+)|\s-x\s+)([a-z]+)", lower)
    api_method = api_method_match.group(1).upper() if api_method_match else "GET"
    if raw_api_request and api_method == "GET":
        findings.append({
            "rule": "raw_api_request_without_helper",
            "severity": "block",
            "message": "Raw sf API output can include warnings that break ad hoc JSON parsing.",
            "next_action": "Use `python scripts/sf_caseops_helper.py api-request ...` for read-only REST requests.",
        })
    if re.search(r"\b(project\s+deploy|deploy\s+start|data\s+(?:update|delete|upsert|create)|apex\s+run)\b", lower) and "production" in lower and not production_approved:
        findings.append({
            "rule": "production_write_without_approval",
            "severity": "block",
            "message": "Production writes require issue-scoped approval.",
            "next_action": "Add approved production marker for this issue or run only against Sandbox.",
        })
    if re.search(r"\bfrom\s+usershare\b", lower) and re.search(r"\bname\b", lower):
        findings.append({
            "rule": "unsafe_usershare_name_query",
            "severity": "block",
            "message": "UserShare does not expose a top-level Name field.",
            "next_action": "Run sobject-fields first and query only returned fields.",
        })
    return {
        "ok": not any(item["severity"] == "block" for item in findings),
        "findings": findings,
    }


def _candidate_lesson_text(signal_type: str, topic: str, summaries: list[str]) -> str:
    if signal_type == "helper_failure":
        return f"When {topic} helper failures recur, inspect the helper failure_class and next_action before retrying ad hoc commands."
    if signal_type == "invalid_query_field":
        return f"When querying {topic} metadata or data, describe or verify fields first and use only returned fields."
    if signal_type == "helper_available_not_used":
        return f"When a deterministic helper exists for {topic}, use it before equivalent raw Salesforce commands."
    if summaries:
        return summaries[0]
    return f"Repeated {signal_type.replace('_', ' ')} pattern observed for {topic}."


def _recommended_file(signal_type: str, topic: str) -> str:
    if "deploy" in topic or "deploy" in signal_type:
        return "local-gotchas/deploy-and-sandbox.md"
    if "query" in signal_type or "field" in signal_type:
        return "local-gotchas/access-and-visibility.md"
    return "lessons-learned/general.md"


def _candidate_type(signal_type: str) -> str:
    if signal_type == "helper_available_not_used":
        return "helper_contract"
    if "deploy" in signal_type:
        return "deploy_pattern"
    if "query" in signal_type or "field" in signal_type:
        return "query_pattern"
    return "lesson_learned"


def _write_candidate_markdown(outputs: Path, candidate: dict[str, Any]) -> None:
    lines = [
        f"# Pending Lesson Candidate: {candidate['candidate_id']}",
        "",
        f"- Topic: {candidate['topic']}",
        f"- Type: {candidate['knowledge_type']}",
        f"- Confidence: {candidate['confidence']}",
        f"- Recurrence: {candidate['recurrence_count']}",
        f"- Recommended file: {candidate.get('recommended_file', '')}",
        "",
        "## Lesson",
        "",
        str(candidate["lesson"]),
        "",
        "## Evidence",
        "",
    ]
    for item in candidate.get("evidence") or []:
        lines.append(f"- {item}")
    (knowledge_root(outputs) / "pending-lessons" / f"{candidate['candidate_id']}.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def _helper_work_item_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    helper = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "work_item_id": f"helper-{candidate['candidate_id']}",
        "source_candidate_id": candidate["candidate_id"],
        "source_signal_ids": candidate.get("source_signal_ids") or [],
        "affected_issue_keys": candidate.get("affected_issue_keys") or [],
        "topic": candidate["topic"],
        "signal_type": candidate.get("signal_type") or "helper_work_item",
        "semantic_key": _semantic_key(
            str(candidate.get("signal_type") or "helper_work_item"),
            str(candidate.get("topic") or "general"),
            "helper_work_item",
        ),
        "summary": f"Evaluate helper/guardrail support for: {candidate['trigger']}",
        "lesson": candidate.get("lesson") or "",
        "evidence": candidate.get("evidence") or [],
        "failure_class": candidate.get("failure_class") or classify_failure_class(str(candidate.get("knowledge_type") or ""), str(candidate.get("topic") or ""), str(candidate.get("lesson") or "")),
        "route": "helper_work_item",
        "quality": candidate.get("quality") or "medium",
        "quality_reason": candidate.get("quality_reason") or "Mechanical lesson converted to helper work item.",
        "eligibility_reason": candidate.get("eligibility_reason") or "",
        "redaction_status": candidate.get("redaction_status") or redaction_status_for_payload(candidate),
        "status": "pending",
        "created_at": utc_now_iso(),
    }
    validate_helper_work_item(helper)
    return helper


def _write_audit_markdown(
    outputs: Path,
    audit_id: str,
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    helper_items: list[dict[str, Any]],
) -> None:
    lines = [
        f"# CaseOps Knowledge Audit {audit_id}",
        "",
        "## Scope",
        "",
        f"- Issue logs scanned: {summary.get('issue_logs_scanned', 0)}",
        f"- Global logs scanned: {summary.get('global_logs_scanned', 0)}",
        f"- Global logs excluded reason: {summary.get('global_logs_excluded_reason') or 'None'}",
        f"- Signals considered: {summary.get('signals_considered', 0)}",
        f"- Signals skipped: {summary.get('signals_skipped', 0)}",
        f"- Signals normalized: {summary.get('signals_normalized', 0)}",
        f"- Signal normalization blocked: {summary.get('signals_normalization_blocked', 0)}",
        f"- Redaction status: {summary.get('redaction_status', 'not_needed')}",
        "",
        "## Summary",
        "",
        f"- Signals reviewed: {summary['signals_reviewed']}",
        f"- Pending lesson candidates created: {summary['candidates_created']}",
        f"- Helper work items created: {summary['helper_work_items_created']}",
        f"- Below-threshold groups: {summary.get('below_threshold_groups', 0)}",
        f"- Helper-only groups: {summary.get('helper_only_groups', 0)}",
        f"- Suppressed noisy groups: {summary.get('suppressed_groups', 0)}",
        f"- Existing pending lessons refined: {summary.get('pending_lessons_refined', 0)}",
        f"- Existing pending lessons converted to helper work: {summary.get('pending_lessons_converted_to_helper', 0)}",
        f"- Existing pending lessons suppressed: {summary.get('pending_lessons_suppressed', 0)}",
        f"- Existing accepted lessons refined: {summary.get('accepted_lessons_refined', 0)}",
        f"- Existing accepted lessons retired: {summary.get('accepted_lessons_retired', 0)}",
        f"- Existing helper work items normalized: {summary.get('helper_work_items_refined', 0)}",
        f"- Semantic helper groups consolidated: {summary.get('helper_work_item_groups_consolidated', 0)}",
        f"- Duplicate helper records retired: {summary.get('helper_work_item_duplicates_retired', 0)}",
        "",
        "## Pending Lesson Candidates",
        "",
    ]
    if candidates:
        for candidate in candidates:
            lines.append(
                f"- {candidate['candidate_id']}: {candidate['trigger']} "
                f"(route={candidate.get('route', '')}, quality={candidate.get('quality', '')}, failure_class={candidate.get('failure_class', '')})"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Helper Work Items", ""])
    if helper_items:
        for item in helper_items:
            lines.append(f"- {item['work_item_id']}: {item['summary']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Groups Not Promoted", ""])
    below = summary.get("below_threshold_details") or []
    helper_only = summary.get("helper_only_group_details") or []
    suppressed = summary.get("suppressed_group_details") or []
    if not below and not helper_only and not suppressed:
        lines.append("- None")
    for item in below[:20]:
        lines.append(
            f"- Below threshold: {item.get('signal_type')} / {item.get('topic')} "
            f"(count={item.get('count')}, reason={item.get('reason')})"
        )
    for item in helper_only[:20]:
        lines.append(
            f"- Helper work: {item.get('signal_type')} / {item.get('topic')} "
            f"(count={item.get('count')}, reason={item.get('reason')})"
        )
    for item in suppressed[:20]:
        lines.append(
            f"- Suppressed: {item.get('signal_type')} / {item.get('topic')} "
            f"(count={item.get('count')}, reason={item.get('reason')})"
        )
    (knowledge_root(outputs) / "audit-reports" / f"audit-summary-{audit_id}.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )
