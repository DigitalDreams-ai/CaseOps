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
)

LESSON_ACTIVE_STATUSES = {"accepted", "active"}
LESSON_INACTIVE_STATUSES = {"pending", "rejected", "retired"}

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str, default: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return cleaned or default


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


def contains_secret(text: str) -> bool:
    return redact_text(text) != (text or "")


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
) -> dict[str, Any]:
    issue = safe_slug(issue_key, "issue")
    signal = safe_slug(signal_type, "signal")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "signal_id": f"{issue}-{safe_slug(source_step, 'step')}-{timestamp}-{signal}",
        "issue_key": issue_key,
        "run_id": run_id,
        "source_step": source_step,
        "signal_type": signal_type,
        "topic": topic,
        "summary": redact_text(summary),
        "evidence": [redact_text(item) for item in evidence[:12]],
        "helper_available": helper_available,
        "knowledge_selected": knowledge_selected or [],
        "created_at": utc_now_iso(),
    }
    validate_signal(payload)
    path = knowledge_root(outputs) / "signals" / f"{payload['signal_id']}.json"
    _write_json(path, payload)
    return payload


def validate_signal(payload: dict[str, Any]) -> None:
    required = ("signal_id", "issue_key", "run_id", "source_step", "signal_type", "summary", "evidence", "created_at")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"Signal missing required fields: {', '.join(missing)}")
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
    if contains_secret(json.dumps(payload, ensure_ascii=False)):
        raise ValueError("Lesson candidate contains secret-like content")


def _read_signal_files(outputs: Path) -> list[dict[str, Any]]:
    return _read_json_files(knowledge_root(outputs) / "signals")


def _read_auditor_state(outputs: Path) -> dict[str, Any]:
    state_path = knowledge_root(outputs) / "audit-reports" / "knowledge-auditor-state.json"
    data = _load_json(state_path, {"processed_signal_ids": []})
    return data if isinstance(data, dict) else {"processed_signal_ids": []}


def _candidate_exists(outputs: Path, source_signal_ids: list[str]) -> bool:
    target = set(source_signal_ids)
    for path in (knowledge_root(outputs) / "pending-lessons").glob("*.json"):
        data = _load_json(path, {})
        if target == set(data.get("source_signal_ids") or []):
            return True
    return False


def run_manual_audit(outputs: Path, *, min_recurrence: int = 2) -> dict[str, Any]:
    """Review signal artifacts and create pending lesson/helper candidates."""
    ensure_knowledge_defaults(outputs)
    state = _read_auditor_state(outputs)
    processed = set(state.get("processed_signal_ids") or [])
    signals = [item for item in _read_signal_files(outputs) if item.get("signal_id") not in processed]

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[(str(signal.get("signal_type") or "unknown"), str(signal.get("topic") or "general"))].append(signal)

    candidates: list[dict[str, Any]] = []
    helper_items: list[dict[str, Any]] = []
    existing_candidate_groups = 0
    consumed_signal_ids: set[str] = set()
    for (signal_type, topic), group in grouped.items():
        if len(group) < min_recurrence:
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
        candidate = {
            "schema_version": KNOWLEDGE_SCHEMA_VERSION,
            "candidate_id": f"lesson-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{safe_slug(signal_type)}-{safe_slug(topic)}",
            "source_signal_ids": source_ids,
            "affected_issue_keys": issue_keys,
            "topic": topic,
            "trigger": f"Repeated {signal_type.replace('_', ' ')} signal for {topic}.",
            "lesson": _candidate_lesson_text(signal_type, topic, summaries),
            "evidence": evidence or summaries[:5],
            "recommended_file": _recommended_file(signal_type, topic),
            "knowledge_type": _candidate_type(signal_type),
            "org_specific": False,
            "confidence": "medium" if len(group) >= 2 else "low",
            "recurrence_count": len(group),
            "risk": "low",
            "created_at": utc_now_iso(),
            "status": "pending",
        }
        validate_candidate(candidate)
        _write_json(knowledge_root(outputs) / "pending-lessons" / f"{candidate['candidate_id']}.json", candidate)
        _write_candidate_markdown(outputs, candidate)
        candidates.append(candidate)
        consumed_signal_ids.update(source_ids)
        if signal_type in {"helper_failure", "helper_available_not_used", "invalid_command_pattern"}:
            helper = _helper_work_item_from_candidate(candidate)
            _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper['work_item_id']}.json", helper)
            helper_items.append(helper)

    processed.update(consumed_signal_ids)
    state_payload = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "last_run_at": utc_now_iso(),
        "processed_signal_ids": sorted(processed),
    }
    _write_json(knowledge_root(outputs) / "audit-reports" / "knowledge-auditor-state.json", state_payload)

    audit_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "audit_id": audit_id,
        "signals_reviewed": len(signals),
        "signals_consumed": len(consumed_signal_ids),
        "groups_considered": len(grouped),
        "below_threshold_groups": sum(1 for group in grouped.values() if len(group) < min_recurrence),
        "existing_candidate_groups": existing_candidate_groups,
        "candidates_created": len(candidates),
        "helper_work_items_created": len(helper_items),
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "helper_work_item_ids": [item["work_item_id"] for item in helper_items],
        "report_path": f"org-knowledge/audit-reports/audit-summary-{audit_id}.md",
    }
    _write_json(knowledge_root(outputs) / "audit-reports" / f"audit-summary-{audit_id}.json", summary)
    _write_audit_markdown(outputs, audit_id, summary, candidates, helper_items)
    return summary


def list_review_items(outputs: Path) -> dict[str, Any]:
    ensure_knowledge_defaults(outputs)
    root = knowledge_root(outputs)
    return {
        "pending_lessons": _public_items(_read_json_files(root / "pending-lessons")),
        "accepted_lessons": _public_items(_read_json_files(root / "accepted-lessons")),
        "rejected_lessons": _public_items(_read_json_files(root / "rejected-lessons")),
        "helper_work_items": _public_items(_read_json_files(root / "helper-work-items")),
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


def accept_lesson(outputs: Path, candidate_id: str, *, edit: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate = _load_candidate(outputs, "pending-lessons", candidate_id)
    updated = copy.deepcopy(candidate)
    if edit:
        for key in ("topic", "trigger", "lesson", "evidence", "knowledge_type", "org_specific", "confidence", "risk", "keywords"):
            if key in edit:
                updated[key] = edit[key]
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
    _write_json(knowledge_root(outputs) / "helper-work-items" / f"{helper['work_item_id']}.json", helper)
    return helper


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
    return {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "work_item_id": f"helper-{candidate['candidate_id']}",
        "source_candidate_id": candidate["candidate_id"],
        "topic": candidate["topic"],
        "summary": f"Evaluate helper/guardrail support for: {candidate['trigger']}",
        "evidence": candidate.get("evidence") or [],
        "status": "pending",
        "created_at": utc_now_iso(),
    }


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
        f"- Signals reviewed: {summary['signals_reviewed']}",
        f"- Pending lesson candidates created: {summary['candidates_created']}",
        f"- Helper work items created: {summary['helper_work_items_created']}",
        "",
        "## Pending Lesson Candidates",
        "",
    ]
    if candidates:
        for candidate in candidates:
            lines.append(f"- {candidate['candidate_id']}: {candidate['trigger']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Helper Work Items", ""])
    if helper_items:
        for item in helper_items:
            lines.append(f"- {item['work_item_id']}: {item['summary']}")
    else:
        lines.append("- None")
    (knowledge_root(outputs) / "audit-reports" / f"audit-summary-{audit_id}.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )
