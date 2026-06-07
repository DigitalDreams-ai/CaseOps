#!/usr/bin/env python3
"""Deterministic issue clustering state for CaseOps.

Phase 1 scope:
- deterministic fingerprint + candidate retrieval
- automatic high-confidence cluster materialization
- cluster index and public-safe markdown outputs under OUTPUTS/issue-clusters/
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

CLUSTER_DIR_NAME = "issue-clusters"
CLUSTER_INDEX_FILE = "clusters.json"
ISSUE_INDEX_FILE = "issue-index.jsonl"
CORRECTIONS_FILE = "corrections.jsonl"
CLUSTER_FILE_PREFIX = "cluster-"
CLUSTER_SCHEMA_VERSION = 1
CORRECTION_SCHEMA_VERSION = 1

DEFAULT_CANDIDATE_LIMIT = 15
DEFAULT_LOOKBACK_DAYS = 180
MIN_CANDIDATE_SCORE = 0.22
MIN_AUTO_CLUSTER_SCORE = 0.82

MIN_TEXT_SCORE = 0.3

CLOSED_STATUSES = {"closed", "resolved", "canceled", "cancelled"}

_CLOSED_STATUS_RE = re.compile(r"^(?:closed|resolved|canceled|cancelled)$", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+|[a-z0-9._-]+)?", re.IGNORECASE)
_FIELD_RE = re.compile(r"\b([a-z][a-z0-9_]*__c)\b", re.IGNORECASE)
_OBJ_FIELD_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*__c)\b")
_MANAGED_PREFIX_RE = re.compile(r"\b([a-z][a-z0-9_]*)__c\b", re.IGNORECASE)
_FILE_IDENTIFIER_RE = re.compile(r"\b[A-Za-z0-9]{15,18}\b")
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
_SF_TOKEN_RE = re.compile(r"\b00D[a-z0-9]{12,18}![A-Za-z0-9._~=-]+\b", re.IGNORECASE)
_FRONTDOOR_RE = re.compile(r"(?i)([?&]sid=)[^\\s&\"'<>]+")
_SFDX_AUTH_RE = re.compile(r"force://[^\"'<>\\s]+")
_LOCAL_PATH_RE = re.compile(r"(?:(?:[a-zA-Z]:\\|/)(?:[\\w.-]+[/\\\\])+[\\w.-]+)")
_ASSIGNEE_TOKEN_RE = re.compile(r"\s*[;,]\\s*")

CORRECTION_ACTIONS = {
    "mark_same_root_cause",
    "mark_not_related",
    "detach_from_cluster",
    "make_canonical",
}

_STOP_WORDS = {
    "a", "an", "and", "are", "at", "be", "by", "case", "customer", "error", "for",
    "from", "has", "have", "if", "in", "is", "it", "issue", "issues", "of", "on",
    "or", "request", "resolved", "salesforce", "status", "support", "summary", "system",
    "team", "the", "to", "unable", "user", "using", "when", "with", "your",
}


def _safe_text(value: Any) -> str:
    return ("" if value is None else str(value)).strip()


def _safe_filename(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]", "-", _safe_text(value).lower().strip())
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized or "cluster"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_iso_ts(raw: str) -> float:
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(_safe_text(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path, max_chars: int | None = None) -> str:
    if not path.exists():
        return ""
    try:
        payload = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if max_chars and len(payload) > max_chars:
        return payload[:max_chars]
    return payload


def _cluster_root(outputs_dir: Path) -> Path:
    return outputs_dir / CLUSTER_DIR_NAME


def _corrections_path(outputs_dir: Path) -> Path:
    return _cluster_root(outputs_dir) / CORRECTIONS_FILE


@dataclass(frozen=True)
class SimilarityCorrection:
    issue: str
    action: str
    cluster_id: str
    reference_issue: str = ""
    canonical_issue: str = ""
    created_at: str = ""
    reason: str = ""


def _now_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_correction(action: str | None, issue: str, cluster_id: str) -> bool:
    return bool(action in CORRECTION_ACTIONS and issue and cluster_id)


def _read_manifest_rows(outputs_dir: Path) -> list[dict[str, str]]:
    manifest_path = outputs_dir / "jira" / "manifest.csv"
    if not manifest_path.exists():
        return []
    try:
        with manifest_path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _pair_key(a: str, b: str) -> tuple[str, str]:
    a_value = _safe_text(a).lower()
    b_value = _safe_text(b).lower()
    if not a_value:
        return ("", b_value)
    if not b_value:
        return (a_value, "")
    return tuple(sorted((a_value, b_value)))  # type: ignore[return-value]


def _read_similarity_corrections(outputs_dir: Path) -> list[SimilarityCorrection]:
    path = _corrections_path(outputs_dir)
    if not path.exists():
        return []
    results: list[SimilarityCorrection] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            action = _safe_text(row.get("action"))
            issue = _safe_text(row.get("issue"))
            cluster_id = _safe_text(row.get("cluster_id"))
            reference_issue = _safe_text(row.get("reference_issue"))
            canonical_issue = _safe_text(row.get("canonical_issue"))
            if not _safe_correction(action, issue, cluster_id):
                continue
            if action in {"mark_not_related", "mark_same_root_cause"} and not reference_issue:
                continue
            if action == "make_canonical" and not canonical_issue:
                continue
            results.append(
                SimilarityCorrection(
                    issue=issue,
                    action=action,
                    cluster_id=cluster_id,
                    reference_issue=reference_issue,
                    canonical_issue=canonical_issue,
                    created_at=_safe_text(row.get("created_at")),
                    reason=_safe_text(row.get("reason")),
                )
            )
    except Exception:
        return []
    return results


def write_similarity_correction(
    outputs_dir: Path,
    issue: str,
    action: str,
    *,
    cluster_id: str = "",
    reference_issue: str = "",
    canonical_issue: str = "",
    reason: str = "",
) -> dict[str, Any]:
    correction = SimilarityCorrection(
        issue=_safe_text(issue),
        action=_safe_text(action),
        cluster_id=_safe_text(cluster_id),
        reference_issue=_safe_text(reference_issue),
        canonical_issue=_safe_text(canonical_issue),
        reason=_safe_text(reason),
    )
    if not _safe_correction(correction.action, correction.issue, correction.cluster_id):
        return {"error": "invalid_correction"}
    if correction.action in {"mark_not_related", "mark_same_root_cause"} and not correction.reference_issue:
        return {"error": f"{correction.action} requires reference_issue"}
    if correction.action == "make_canonical" and not correction.canonical_issue:
        return {"error": "make_canonical requires canonical_issue"}
    if correction.action == "make_canonical":
        correction = SimilarityCorrection(
            issue=correction.issue,
            action=correction.action,
            cluster_id=correction.cluster_id,
            reference_issue="",
            canonical_issue=correction.canonical_issue,
            reason=correction.reason,
            created_at=correction.created_at,
        )

    payload = {
        "schema_version": CORRECTION_SCHEMA_VERSION,
        "issue": correction.issue,
        "action": correction.action,
        "cluster_id": correction.cluster_id,
        "reference_issue": correction.reference_issue,
        "canonical_issue": correction.canonical_issue,
        "reason": correction.reason,
        "created_at": _now_timestamp(),
    }
    _cluster_root(outputs_dir).mkdir(parents=True, exist_ok=True)
    with _corrections_path(outputs_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return {"ok": True, "action": correction.action, "issue": correction.issue, "cluster_id": correction.cluster_id}


def _iter_raw_issue_keys(outputs_dir: Path) -> list[str]:
    raw_dir = outputs_dir / "jira" / "raw"
    if not raw_dir.exists():
        return []
    try:
        return sorted({p.stem for p in raw_dir.glob("*.json") if p.is_file() and p.stem})
    except Exception:
        return []


def _collect_issue_rows(outputs_dir: Path, manifest_rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    rows = manifest_rows if manifest_rows is not None else _read_manifest_rows(outputs_dir)
    by_key: dict[str, dict[str, str]] = {}
    for row in rows:
        key = _safe_text(row.get("Key"))
        if key:
            by_key[key] = {k: _safe_text(v) for k, v in row.items() if isinstance(v, (str, int, float, bool))}
    for key in _iter_raw_issue_keys(outputs_dir):
        by_key.setdefault(key, {"Key": key})
    return [by_key[key] for key in sorted(by_key)]


def _adf_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return " ".join(_adf_to_text(item) for item in value)
    if not isinstance(value, dict):
        return ""

    if "value" in value and isinstance(value["value"], str):
        return " ".join(value["value"].split())
    if value.get("type") == "text" and isinstance(value.get("text"), str):
        return " ".join(value["text"].split())
    content = value.get("content")
    if isinstance(content, list):
        return " ".join(_adf_to_text(item) for item in content)
    return ""


def _extract_labels_and_components(fields: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    components = fields.get("components", [])
    if isinstance(components, list):
        for item in components:
            values.add(_safe_text(item.get("name") if isinstance(item, dict) else item).lower())
    labels = fields.get("labels", [])
    if isinstance(labels, list):
        for item in labels:
            values.add(_safe_text(item).lower())
    return {value for value in values if value}


def _extract_comments(fields: dict[str, Any], limit: int = 6) -> str:
    lines: list[str] = []

    comments_payload = fields.get("comment", {})
    if isinstance(comments_payload, dict):
        comments = comments_payload.get("comments", [])
    else:
        comments = comments_payload
    if not isinstance(comments, list):
        comments = fields.get("comments", [])
    if not isinstance(comments, list):
        return ""

    for item in comments[:limit]:
        if not isinstance(item, dict):
            continue
        author = item.get("author", {})
        author_text = ""
        if isinstance(author, dict):
            author_text = _safe_text(author.get("displayName"))
        elif isinstance(author, str):
            author_text = _safe_text(author)
        body = _adf_to_text(item.get("body")) if isinstance(item.get("body"), (dict, list, str)) else ""
        if author_text:
            lines.append(f"{author_text}: {body}".strip())
        elif body:
            lines.append(body)
    return " ".join(line for line in lines if line)


def _tokenize(value: str, min_len: int = 3) -> set[str]:
    tokens: set[str] = set()
    for token in _WORD_RE.findall(_safe_text(value).lower()):
        if len(token) >= min_len and token not in _STOP_WORDS:
            tokens.add(token)
    return tokens


def _overlap_ratio(left: set[str], right: set[str]) -> tuple[set[str], float]:
    left_set = set(left)
    right_set = set(right)
    shared = left_set & right_set
    union = left_set | right_set
    score = len(shared) / len(union) if union else 0.0
    return shared, score


def _extract_terms(raw_issue: dict[str, Any], row: dict[str, str]) -> dict[str, set[str]]:
    fields: dict[str, Any] = {}
    issue = raw_issue.get("issue", {})
    if isinstance(issue, dict):
        raw_fields = issue.get("fields", {})
        if isinstance(raw_fields, dict):
            fields = raw_fields

    summary = _safe_text(row.get("Summary") or fields.get("summary", ""))
    description = fields.get("description", "")
    if isinstance(description, dict):
        description = _adf_to_text(description)
    else:
        description = _safe_text(description)

    resolution = fields.get("resolution", "")
    if isinstance(resolution, dict):
        resolution = _safe_text(resolution.get("name", ""))
    else:
        resolution = _safe_text(resolution)

    component_terms = _extract_labels_and_components(fields)
    comments_text = _extract_comments(fields)
    text = " ".join(part for part in [summary, description, resolution, comments_text] if part)
    feature_tokens = set().union(_tokenize(text, min_len=3), _tokenize(summary, min_len=2), _tokenize(description, min_len=2))
    object_field_pairs = {_safe_text(v).lower() for v in _OBJ_FIELD_RE.findall(f"{summary} {description}")}
    fields_terms = {_safe_text(v).lower() for v in _FIELD_RE.findall(f"{summary} {description}")}
    managed_prefixes = {_safe_text(v).split("__")[0].lower() for v in _MANAGED_PREFIX_RE.findall(f"{text}")}
    error_terms = {_safe_text(v) for v in feature_tokens if _safe_text(v) in {
        "error", "exception", "failed", "failure", "permission", "denied",
        "access", "null", "invalid", "timeout",
    }}

    return {
        "summary_tokens": _tokenize(summary, min_len=2),
        "component_terms": {value.lower() for value in component_terms if value and value != "null"},
        "object_field_pairs": object_field_pairs,
        "field_terms": fields_terms,
        "managed_packages": managed_prefixes,
        "error_terms": error_terms,
        "feature_tokens": feature_tokens,
    }


def _artifact_text(outputs_dir: Path, key: str) -> str:
    return " ".join(
        _read_text(path)
        for path in (
            outputs_dir / "jira" / "summary" / f"{key}.md",
            outputs_dir / "investigations" / f"{key}.md",
            outputs_dir / "hypothesis" / f"{key}.md",
            outputs_dir / "test-reports" / f"{key}.md",
            outputs_dir / "internal-notes" / f"{key}.md",
        )
    ).strip()


def _artifact_signature(outputs_dir: Path, key: str) -> str:
    paths = (
        outputs_dir / "jira" / "raw" / f"{key}.json",
        outputs_dir / "jira" / "summary" / f"{key}.md",
        outputs_dir / "investigations" / f"{key}.md",
        outputs_dir / "hypothesis" / f"{key}.md",
        outputs_dir / "test-reports" / f"{key}.md",
        outputs_dir / "internal-notes" / f"{key}.md",
    )
    h = hashlib.sha256()
    for path in paths:
        if not path.exists():
            continue
        try:
            h.update(path.read_bytes())
            h.update(b"|")
        except OSError:
            continue
    return f"sha256:{h.hexdigest()}"


@dataclass(frozen=True)
class IssueFingerprint:
    key: str
    status: str
    assignee: str
    assignee_email: str
    reporter: str
    request_type: str
    updated: str
    summary: str
    summary_tokens: list[str]
    component_terms: list[str]
    object_field_pairs: list[str]
    field_terms: list[str]
    managed_packages: list[str]
    error_terms: list[str]
    feature_tokens: list[str]
    artifact_signature: str
    source_signature: str

    @classmethod
    def from_issue(cls, key: str, row: dict[str, str], raw: dict[str, Any], outputs_dir: Path) -> "IssueFingerprint | None":
        if not key:
            return None
        issue = raw.get("issue", {})
        fields = issue.get("fields", {}) if isinstance(issue, dict) else {}
        if not isinstance(fields, dict):
            fields = {}

        status = fields.get("status", "")
        status_name = status.get("name") if isinstance(status, dict) else status
        assignee = fields.get("assignee", {})
        reporter = fields.get("reporter", {})
        terms = _extract_terms(raw, row)
        summary = _safe_text(row.get("Summary") or fields.get("summary", ""))
        request_type = fields.get("customfield_10010", "")
        if not isinstance(request_type, str):
            request_type = _safe_text(request_type)

        assignee_name = ""
        assignee_email = ""
        if isinstance(assignee, dict):
            assignee_name = _safe_text(assignee.get("displayName") or assignee.get("name"))
            assignee_email = _safe_text(assignee.get("emailAddress"))
        elif isinstance(assignee, str):
            assignee_name = _safe_text(assignee)

        reporter_name = ""
        if isinstance(reporter, dict):
            reporter_name = _safe_text(reporter.get("displayName") or reporter.get("name"))
        elif isinstance(reporter, str):
            reporter_name = reporter

        return cls(
            key=_safe_text(key),
            status=_safe_text(status_name).lower(),
            assignee=assignee_name,
            assignee_email=assignee_email,
            reporter=reporter_name,
            request_type=request_type,
            updated=_safe_text(row.get("Updated") or fields.get("updated", "")),
            summary=summary,
            summary_tokens=sorted(terms["summary_tokens"]),
            component_terms=sorted(terms["component_terms"]),
            object_field_pairs=sorted(terms["object_field_pairs"]),
            field_terms=sorted(terms["field_terms"]),
            managed_packages=sorted(terms["managed_packages"]),
            error_terms=sorted(terms["error_terms"]),
            feature_tokens=sorted(terms["feature_tokens"]),
            artifact_signature=_artifact_signature(outputs_dir, key),
            source_signature=_sha256(_artifact_text(outputs_dir, key)),
        )

    def is_closed(self) -> bool:
        return bool(_CLOSED_STATUS_RE.fullmatch(_safe_text(self.status)))

    def assignee_tokens(self) -> set[str]:
        values = set()
        if self.assignee:
            values.add(self.assignee.lower())
        if self.assignee_email:
            values.add(self.assignee_email.lower())
        return values

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateMatch:
    key: str
    score: float
    classification: str
    reasons: list[str]
    terms: list[str]


def _score_pair(base: IssueFingerprint, other: IssueFingerprint, *, lookback_days: int) -> CandidateMatch:
    score = 0.0
    reasons: list[str] = []
    evidence: set[str] = set()

    shared_obj, obj_ratio = _overlap_ratio(set(base.object_field_pairs), set(other.object_field_pairs))
    if shared_obj:
        score += min(0.52, 0.14 + (0.18 * min(len(shared_obj), 2)))
        reasons.append("shared_object_and_field_pair")
        evidence.update(shared_obj)

    shared_components, comp_ratio = _overlap_ratio(set(base.component_terms), set(other.component_terms))
    if shared_components:
        score += min(0.36, 0.05 + (0.12 * min(len(shared_components), 5)))
        reasons.append("shared_jira_component_or_label")
        evidence.update(shared_components)

    shared_fields, _field_ratio = _overlap_ratio(set(base.field_terms), set(other.field_terms))
    if shared_fields:
        score += min(0.28, 0.06 + (0.07 * min(len(shared_fields), 3)))
        reasons.append("shared_salesforce_field")
        evidence.update(shared_fields)

    shared_errors = set(base.error_terms) & set(other.error_terms)
    if shared_errors:
        score += min(0.34, 0.14 * min(len(shared_errors), 3))
        reasons.append("shared_error_term")
        evidence.update(shared_errors)

    shared_pkg = set(base.managed_packages) & set(other.managed_packages)
    if shared_pkg:
        score += 0.10
        reasons.append("shared_managed_package_prefix")
        evidence.update(shared_pkg)

    base_obj_terms = set(base.summary_tokens)
    other_obj_terms = set(other.summary_tokens)
    if base_obj_terms and other_obj_terms:
        title_similarity = SequenceMatcher(None, " ".join(sorted(base_obj_terms)), " ".join(sorted(other_obj_terms))).ratio()
        if title_similarity >= MIN_TEXT_SCORE:
            score += 0.10
            reasons.append("title_similarity")
            evidence.update({
                term for term in base_obj_terms & other_obj_terms if term
            })

    shared_feature_terms = set(base.feature_tokens) & set(other.feature_tokens)
    if shared_feature_terms:
        score += min(0.2, 0.02 + 0.02 * min(len(shared_feature_terms), 5))
        reasons.append("shared_feature_terms")
        evidence.update(sorted(shared_feature_terms)[:5])

    if base.assignee and other.assignee and base.assignee.lower() == other.assignee.lower():
        score += 0.04
        reasons.append("assignee_match")

    if base.request_type and other.request_type and base.request_type.lower() == other.request_type.lower():
        score += 0.03
        reasons.append("request_type_match")

    base_ts = _parse_iso_ts(base.updated)
    other_ts = _parse_iso_ts(other.updated)
    if base_ts and other_ts:
        lookback_seconds = max(86400.0, lookback_days * 86400.0)
        delta = abs(base_ts - other_ts)
        if delta <= lookback_seconds:
            score += 0.03 if delta <= (lookback_seconds * 0.5) else 0.015
            reasons.append("recent_update_window")

    if comp_ratio > 0.7:
        reasons.append("component_pattern_match")
        evidence.add("component-pattern")
        score += 0.02

    if score < MIN_CANDIDATE_SCORE:
        return CandidateMatch(other.key, 0.0, "unrelated", [], [])

    if shared_obj and shared_errors:
        classification = "same_problem_same_fix"
    elif shared_obj or shared_errors:
        classification = "same_problem_needs_record_validation"
    elif shared_components:
        classification = "same_symptom_different_possible_cause"
    elif obj_ratio >= 0.45 or shared_feature_terms:
        classification = "related_context_only"
    else:
        classification = "related_context_only"

    return CandidateMatch(
        key=other.key,
        score=round(score, 4),
        classification=classification,
        reasons=sorted(reasons),
        terms=sorted(evidence)[:24],
    )


def _find_candidates(
    base: IssueFingerprint,
    pool: list[IssueFingerprint],
    *,
    candidate_limit: int,
    lookback_days: int,
) -> list[CandidateMatch]:
    if candidate_limit < 1:
        candidate_limit = DEFAULT_CANDIDATE_LIMIT

    scored: list[CandidateMatch] = []
    for other in pool:
        if other.key == base.key:
            continue
        match = _score_pair(base, other, lookback_days=lookback_days)
        if match.classification == "unrelated" or match.score < MIN_CANDIDATE_SCORE:
            continue
        scored.append(match)

    scored.sort(key=lambda match: (-match.score, match.key))
    return scored[:candidate_limit]


def _safe_cluster_id(value: str) -> str:
    return f"{CLUSTER_FILE_PREFIX}{_safe_filename(value)}"


def _sanitize_public_summary(text: str, org_aliases: set[str] | None = None) -> str:
    aliases = {_safe_text(item).lower() for item in (org_aliases or set()) if _safe_text(item)}
    sanitized = _SF_TOKEN_RE.sub("[REDACTED_SF_ACCESS_TOKEN]", text)
    sanitized = _FRONTDOOR_RE.sub(r"\1[REDACTED_FRONTDOOR_SID]", sanitized)
    sanitized = _SFDX_AUTH_RE.sub("[REDACTED_SFDX_AUTH_URL]", sanitized)
    sanitized = _LOCAL_PATH_RE.sub("[REDACTED_LOCAL_PATH]", sanitized)
    sanitized = _FILE_IDENTIFIER_RE.sub("[REDACTED_SALESFORCE_ID]", sanitized)

    for match in re.findall(r"[\w.\-+]+@[\w.\-]+\.\w+", sanitized):
        if _EMAIL_RE.fullmatch(match):
            sanitized = sanitized.replace(match, "[REDACTED_EMAIL]")
    for alias in aliases:
        sanitized = sanitized.replace(alias, "[REDACTED_ORG_ALIAS]")
    return sanitized


def _build_cluster_payload(
    cluster_id: str,
    canonical_issue: str,
    members: list[IssueFingerprint],
    best_hits: dict[str, CandidateMatch],
    generated_at: str,
) -> dict[str, Any]:
    shared_components = sorted(set().union(*[set(member.component_terms) for member in members]))
    shared_objects = sorted(set().union(*[set(member.object_field_pairs) for member in members]))
    shared_fields = sorted(set().union(*[set(member.field_terms) for member in members]))
    shared_errors = sorted(set().union(*[set(member.error_terms) for member in members]))
    shared_prefixes = sorted(set().union(*[set(member.managed_packages) for member in members]))

    requires_delta_validation = any(
        hit.classification in {"same_problem_same_fix", "same_problem_needs_record_validation"}
        for hit in best_hits.values()
    )

    member_payload = []
    for member in members:
        hit = best_hits.get(member.key)
        if hit is None:
            hit = CandidateMatch(member.key, 1.0 if member.key == canonical_issue else 0.0, "canonical" if member.key == canonical_issue else "related", ["self"], [])
        member_payload.append({
            "key": member.key,
            "jira_updated": member.updated,
            "relationship": "canonical" if member.key == canonical_issue else "related",
            "classification": hit.classification,
            "artifact_signature": member.artifact_signature,
            "source_signature": member.source_signature,
            "evidence_terms": hit.terms[:12],
            "reasons": hit.reasons[:6],
            "score": hit.score,
        })

    return {
        "schema_version": CLUSTER_SCHEMA_VERSION,
        "cluster_id": cluster_id,
        "title": f"Issue similarity cluster for {canonical_issue}",
        "canonical_issue": canonical_issue,
        "status": "active",
        "created_at": generated_at,
        "updated_at": generated_at,
        "members": member_payload,
        "shared_findings": {
            "components": shared_components,
            "objects": sorted(set(shared_objects) | set(shared_fields)),
            "error_terms": shared_errors,
            "managed_prefixes": shared_prefixes,
        },
        "safety": {
            "requires_delta_validation": bool(requires_delta_validation),
            "reuse_allowed": False,
            "reuse_reason": "Deterministic clustering only; pipeline safety controls govern reuse.",
            "updated_by": "issue_clusters.py",
        },
        "evidence_summary": {
            "member_count": len(members),
            "auto_created": True,
            "candidate_count": max(0, len(member_payload) - 1),
        },
    }


def _apply_similarity_corrections(
    issue_key: str,
    cluster_payload: dict[str, Any],
    *,
    corrections: list[SimilarityCorrection],
) -> dict[str, Any]:
    if not corrections:
        return cluster_payload

    normalized_issue = _safe_text(issue_key).lower()
    if not normalized_issue:
        return cluster_payload

    detaching = {_safe_text(item.issue).lower() for item in corrections if item.action == "detach_from_cluster"}
    if normalized_issue in detaching:
        # Detach from cluster is absolute for this issue view.
        return {"detached": True, **cluster_payload}

    same_root_pairs = {_pair_key(item.issue, item.reference_issue) for item in corrections if item.action == "mark_same_root_cause"}
    not_related_pairs = {_pair_key(item.issue, item.reference_issue) for item in corrections if item.action == "mark_not_related"}
    canonical = ""
    for item in corrections:
        if item.action == "make_canonical" and item.cluster_id == _safe_text(cluster_payload.get("cluster_id")):
            canonical = item.canonical_issue

    if canonical:
        cluster_payload["canonical_issue"] = canonical

    members = []
    for member in cluster_payload.get("members", []):
        member_key = _safe_text(member.get("key"))
        p = _pair_key(normalized_issue, member_key)
        if p in not_related_pairs:
            continue
        if p in same_root_pairs:
            member["classification"] = "same_problem_same_fix"
        members.append(member)

    cluster_payload["members"] = members
    return cluster_payload


def _cluster_summary_markdown(cluster: dict[str, Any], sanitize: bool = True) -> str:
    body = f"""# Issue Similarity Cluster: {cluster.get("canonical_issue", "unknown")}

- **Cluster ID:** `{cluster.get("cluster_id", "")}`
- **Canonical Issue:** `{cluster.get("canonical_issue", "")}`
- **Status:** {cluster.get("status", "active")}
- **Generated At:** {cluster.get("updated_at", "")}

## Members
"""
    for member in cluster.get("members", []):
        body += (
            f"- `{_safe_text(member.get('key', ''))}` · {member.get('relationship', 'member')} · "
            f"{member.get('classification', '')}\n"
        )

    shared = cluster.get("shared_findings", {})
    body += f"""
## Shared Findings
- Shared components/labels: {", ".join(shared.get("components", [])[:12]) or "none"}
- Shared objects/fields: {", ".join(shared.get("objects", [])[:12]) or "none"}
- Shared error terms: {", ".join(shared.get("error_terms", [])[:12]) or "none"}
- Shared managed package prefixes: {", ".join(shared.get("managed_prefixes", [])[:12]) or "none"}

## Safety Notes
- Deterministic retrieval only. This summary is public-safe and does not include tokens, frontdoor links, or local paths.
- Reuse decisions are not made from this cluster file alone.
"""

    return _sanitize_public_summary(body) if sanitize else body


def _ensure_cluster_dir(outputs_dir: Path) -> None:
    (outputs_dir / CLUSTER_DIR_NAME).mkdir(parents=True, exist_ok=True)


def _derive_current_user_tokens(current_user: str) -> set[str]:
    tokens = {_safe_text(token).lower() for token in _ASSIGNEE_TOKEN_RE.split(current_user or "") if _safe_text(token)}
    if not tokens:
        for value in (
            os.environ.get("CASEOPS_SIMILAR_ISSUES_CURRENT_USER", ""),
            os.environ.get("CASEOPS_DEFAULT_ASSIGNEE", ""),
            os.environ.get("JIRA_EMAIL", ""),
        ):
            if not value:
                continue
            tokens.update(_safe_text(token).lower() for token in _ASSIGNEE_TOKEN_RE.split(value) if _safe_text(token))
    return {token for token in tokens if token}


def _matches_current_user(fp: IssueFingerprint, user_tokens: set[str], *, current_user_only: bool) -> bool:
    if not current_user_only:
        return True
    if not user_tokens:
        return False
    return bool(fp.assignee_tokens() & user_tokens)


def _candidate_graph(
    fingerprints: list[IssueFingerprint],
    *,
    candidate_limit: int,
    lookback_days: int,
) -> dict[str, list[CandidateMatch]]:
    """Build deterministic candidate hits for each issue key.

    Returns a keyed list of all candidate matches sorted by score desc + key.
    """
    candidates: dict[str, list[CandidateMatch]] = {}
    for index, base in enumerate(fingerprints):
        pool = fingerprints[:index] + fingerprints[index + 1 :]
        base_hits = _find_candidates(base, pool, candidate_limit=candidate_limit, lookback_days=lookback_days)
        candidates[base.key] = base_hits
    return candidates


def _build_dsu(edges: list[tuple[str, str, CandidateMatch]], keys: list[str]) -> dict[str, str]:
    parent = {key: key for key in keys}

    def find(value: str) -> str:
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(left: str, right: str) -> None:
        left_parent = find(left)
        right_parent = find(right)
        if left_parent == right_parent:
            return
        if left_parent < right_parent:
            parent[right_parent] = left_parent
        else:
            parent[left_parent] = right_parent

    for left, right, match in edges:
        if match.classification not in {"same_problem_same_fix", "same_problem_needs_record_validation"}:
            continue
        if match.score < MIN_AUTO_CLUSTER_SCORE:
            continue
        union(left, right)

    components: dict[str, list[str]] = {}
    for key in keys:
        root = find(key)
        components.setdefault(root, []).append(key)
    return components


def rebuild_issue_clusters(
    *,
    outputs_dir: Path,
    manifest_rows: list[dict[str, str]] | None = None,
    include_closed: bool = True,
    current_user_only: bool = True,
    auto_cluster: bool = True,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    current_user: str = "",
    public_safe_summaries: bool = True,
    log: Callable[[str], None] | None = None,
    org_aliases: set[str] | None = None,
    read_raw: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if candidate_limit < 1:
        candidate_limit = DEFAULT_CANDIDATE_LIMIT
    if lookback_days < 1:
        lookback_days = DEFAULT_LOOKBACK_DAYS

    if log is None:
        log = lambda _message: None

    read_raw_fn = read_raw or (lambda key: _read_json(outputs_dir / "jira" / "raw" / f"{key}.json"))
    issue_rows = _collect_issue_rows(outputs_dir, manifest_rows=manifest_rows)
    _ensure_cluster_dir(outputs_dir)
    cluster_root = outputs_dir / CLUSTER_DIR_NAME

    user_tokens = _derive_current_user_tokens(current_user)
    if current_user_only and not user_tokens:
        log("Similarity clustering skipped: current-user identifier missing for current-user-only mode.")

    fingerprints: list[IssueFingerprint] = []
    for row in issue_rows:
        key = _safe_text(row.get("Key"))
        fp = IssueFingerprint.from_issue(key, row, read_raw_fn(key), outputs_dir)
        if fp is None:
            continue
        if not include_closed and fp.is_closed():
            continue
        if not _matches_current_user(fp, user_tokens, current_user_only=current_user_only):
            continue
        fingerprints.append(fp)

    fingerprints.sort(key=lambda item: (_parse_iso_ts(item.updated), item.key))
    by_key = {fp.key: fp for fp in fingerprints}
    all_keys = [fp.key for fp in fingerprints]

    generated_at = _now_iso()
    if not fingerprints:
        (cluster_root / ISSUE_INDEX_FILE).write_text("", encoding="utf-8")
        (cluster_root / CLUSTER_INDEX_FILE).write_text(
            json.dumps({
                "schema_version": CLUSTER_SCHEMA_VERSION,
                "generated_at": generated_at,
                "clusters": [],
                "generated_summary": "0 cluster(s) built from 0 issue fingerprints",
            }, indent=2),
            encoding="utf-8",
        )
        return {
            "clusters": 0,
            "issues": 0,
            "generated_at": generated_at,
            "cluster_root": str(cluster_root),
            "cluster_index": str(cluster_root / CLUSTER_INDEX_FILE),
            "issue_index": str(cluster_root / ISSUE_INDEX_FILE),
            "enabled": True,
        }

    candidates = _candidate_graph(
        fingerprints,
        candidate_limit=candidate_limit,
        lookback_days=lookback_days,
    )

    # Build deterministic cluster edges.
    edges: list[tuple[str, str, CandidateMatch]] = []
    for key, hits in candidates.items():
        for match in hits:
            if match.score < MIN_AUTO_CLUSTER_SCORE:
                continue
            if match.classification not in {"same_problem_same_fix", "same_problem_needs_record_validation"}:
                continue
            left, right = sorted((key, match.key))
            edges.append((left, right, match))
    edges.sort(key=lambda item: (-item[2].score, item[0], item[1]))

    clusters_map = _build_dsu(edges, all_keys) if auto_cluster else {_key: [_key] for _key in all_keys}
    best_edge_per_member: dict[str, CandidateMatch] = {}
    for key, hits in candidates.items():
        for hit in hits:
            prev = best_edge_per_member.get(key)
            if prev is None or (hit.classification in {"same_problem_same_fix", "same_problem_needs_record_validation"} and hit.score > prev.score):
                best_edge_per_member[key] = hit

    cluster_payloads: list[dict[str, Any]] = []
    active_clusters: set[str] = set()
    member_cluster_id: dict[str, str] = {}
    for root, members in clusters_map.items():
        unique_members = sorted(set(members))
        if len(unique_members) < 2:
            continue
        canonical = unique_members[0]
        cluster_id = _safe_cluster_id(canonical)
        active_clusters.add(cluster_id)
        cluster_fps = [by_key[key] for key in unique_members if key in by_key]
        if not cluster_fps:
            continue

        cluster_payload = _build_cluster_payload(
            cluster_id=cluster_id,
            canonical_issue=canonical,
            members=cluster_fps,
            best_hits={member: best_edge_per_member.get(member, CandidateMatch(member, 1.0, "canonical", ["self"], [])) for member in unique_members},
            generated_at=generated_at,
        )
        (cluster_root / f"{cluster_id}.json").write_text(json.dumps(cluster_payload, indent=2), encoding="utf-8")
        (cluster_root / f"{cluster_id}.md").write_text(_cluster_summary_markdown(cluster_payload, sanitize=public_safe_summaries), encoding="utf-8")
        for member in unique_members:
            member_cluster_id[member] = cluster_id
        cluster_payloads.append({
            "cluster_id": cluster_id,
            "canonical_issue": canonical,
            "status": cluster_payload["status"],
            "member_count": len(unique_members),
            "members": unique_members,
            "cluster_file": f"{cluster_id}.json",
            "summary_file": f"{cluster_id}.md",
            "updated_at": generated_at,
        })

    # Remove stale cluster files no longer present.
    for existing in sorted(cluster_root.glob("cluster-*.json")):
        stem = existing.stem
        if stem not in active_clusters:
            existing.unlink(missing_ok=True)
            (cluster_root / f"{stem}.md").unlink(missing_ok=True)

    cluster_index = {
        "schema_version": CLUSTER_SCHEMA_VERSION,
        "generated_at": generated_at,
        "clusters": cluster_payloads,
        "generated_summary": f"{len(cluster_payloads)} cluster(s) built from {len(fingerprints)} issue fingerprints",
        "settings": {
            "candidate_limit": candidate_limit,
            "lookback_days": lookback_days,
            "include_closed": bool(include_closed),
            "current_user_only": bool(current_user_only),
            "auto_cluster": bool(auto_cluster),
            "public_safe_summaries": bool(public_safe_summaries),
        },
    }
    (cluster_root / CLUSTER_INDEX_FILE).write_text(json.dumps(cluster_index, indent=2), encoding="utf-8")

    issue_rows_payload: list[str] = []
    for fp in fingerprints:
        key = fp.key
        issue_cluster = _safe_cluster_id(key)
        if auto_cluster:
            issue_cluster = member_cluster_id.get(key, issue_cluster)
        row = {
            "key": key,
            "status": fp.status,
            "assignee": fp.assignee,
            "updated": fp.updated,
            "summary": fp.summary[:300],
            "cluster_id": issue_cluster if issue_cluster in active_clusters else "",
            "cluster_type": best_edge_per_member.get(key, CandidateMatch(key, 1.0, "canonical", ["self"], [])).classification,
            "fingerprint": {
                "summary_tokens": fp.summary_tokens,
                "feature_tokens": fp.feature_tokens[:80],
                "component_terms": fp.component_terms,
                "object_field_pairs": fp.object_field_pairs,
                "field_terms": fp.field_terms,
                "managed_packages": fp.managed_packages,
                "artifact_signature": fp.artifact_signature,
                "source_signature": fp.source_signature,
            },
            "notes": {
                "is_closed": fp.is_closed(),
            },
        }
        issue_rows_payload.append(json.dumps(row, ensure_ascii=False, sort_keys=True))

    (cluster_root / ISSUE_INDEX_FILE).write_text(
        "\n".join(issue_rows_payload) + ("\n" if issue_rows_payload else ""),
        encoding="utf-8",
    )

    log(
        f"Similarity clusters rebuilt: {len(cluster_payloads)} cluster(s), {len(fingerprints)} issue fingerprint(s), {len(active_clusters)} active cluster file(s)."
    )
    return {
        "clusters": len(cluster_payloads),
        "issues": len(fingerprints),
        "generated_at": generated_at,
        "cluster_root": str(cluster_root),
        "cluster_index": str(cluster_root / CLUSTER_INDEX_FILE),
        "issue_index": str(cluster_root / ISSUE_INDEX_FILE),
        "enabled": True,
    }


def read_issue_cluster_context(*, outputs_dir: Path, issue_key: str) -> dict[str, Any]:
    root = outputs_dir / CLUSTER_DIR_NAME
    if not root.is_dir():
        return {"issue": issue_key, "cluster_id": ""}

    def _ensure_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [_safe_text(item) for item in value if _safe_text(item)]
        return []

    def _is_open_status(status: str) -> bool:
        return _safe_text(status).lower() not in CLOSED_STATUSES

    def _member_block(member: dict[str, Any], *, output_root: dict[str, Any]) -> dict[str, Any]:
        member_key = _safe_text(member.get("key", ""))
        if not member_key:
            return {}
        current_status = _safe_text(issue_rows.get(member_key, {}).get("status", "")).lower()
        current_sig = _artifact_signature(outputs_dir, member_key)
        stored_sig = _safe_text(member.get("artifact_signature", ""))
        stale = bool(stored_sig and current_sig and stored_sig != current_sig)
        result = {
            "key": member_key,
            "status": current_status,
            "relationship": _safe_text(member.get("relationship", "")),
            "classification": _safe_text(member.get("classification", "")),
            "evidence_terms": _ensure_str_list(member.get("evidence_terms"))[:10],
            "reasons": _ensure_str_list(member.get("reasons"))[:8],
            "jira_updated": _safe_text(member.get("jira_updated", "")),
            "artifact_signature": stored_sig,
            "source_signature": _safe_text(member.get("source_signature", "")),
            "is_open": _is_open_status(current_status),
            "is_stale": stale,
            "cluster_context": output_root.get("cluster_id"),
        }
        return result

    issue_rows: dict[str, dict[str, Any]] = {}
    issue_index = root / ISSUE_INDEX_FILE
    if issue_index.exists():
        try:
            for line in issue_index.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict) and payload.get("key"):
                    issue_rows[_safe_text(payload["key"])] = payload
        except Exception:
            issue_rows = {}

    issue_row = issue_rows.get(_safe_text(issue_key), {})
    if not issue_row:
        return {"issue": issue_key, "cluster_id": ""}

    cluster_id = _safe_text(issue_row.get("cluster_id", ""))
    if not cluster_id:
        return {
            "issue": issue_key,
            "cluster_id": "",
            "cluster_type": issue_row.get("cluster_type", ""),
            "cluster": None,
            "members": [],
            "open_matches": [],
            "closed_matches": [],
            "status": issue_row.get("status", ""),
            "corrections_applied": [],
        }

    cluster_path = root / f"{cluster_id}.json"
    if not cluster_path.exists():
        return {
            "issue": issue_key,
            "cluster_id": cluster_id,
            "cluster_type": issue_row.get("cluster_type", ""),
            "cluster": None,
            "members": [],
            "open_matches": [],
            "closed_matches": [],
            "status": issue_row.get("status", ""),
            "corrections_applied": [],
        }

    try:
        cluster_payload = json.loads(cluster_path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "issue": issue_key,
            "cluster_id": cluster_id,
            "cluster_type": issue_row.get("cluster_type", ""),
            "cluster": None,
            "members": [],
            "open_matches": [],
            "closed_matches": [],
            "status": issue_row.get("status", ""),
            "corrections_applied": [],
        }

    corrections = _read_similarity_corrections(outputs_dir)
    cluster_payload = _apply_similarity_corrections(issue_key, cluster_payload, corrections=corrections)
    if cluster_payload.get("detached"):
        return {
            "issue": issue_key,
            "cluster_id": cluster_id,
            "cluster_type": issue_row.get("cluster_type", ""),
            "cluster": {"cluster_id": cluster_id, "canonical_issue": cluster_payload.get("canonical_issue", ""), "status": cluster_payload.get("status")},
            "members": [],
            "open_matches": [],
            "closed_matches": [],
            "status": issue_row.get("status", ""),
            "cluster_state": "detached",
            "summary_url": cluster_payload.get("summary_file", f"{cluster_id}.md"),
            "summary_preview": "",
            "corrections_applied": ["detach_from_cluster"],
        }

    members_raw = [_member_block(item, output_root={"cluster_id": cluster_id}) for item in cluster_payload.get("members", [])]
    members = [member for member in members_raw if member]
    members.sort(key=lambda item: (item["relationship"] != "canonical", item["key"]))
    open_matches = [member for member in members if member["is_open"]]
    closed_matches = [member for member in members if not member["is_open"]]

    summary_file = _safe_text(cluster_payload.get("summary_file", f"{cluster_id}.md"))
    summary_url = ""
    summary_preview = ""
    if summary_file:
        summary_path = root / summary_file
        if summary_path.exists():
            try:
                summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
                summary_url = f"/files/issue-clusters/{summary_file}"
                summary_preview = _sanitize_public_summary(summary_text)[:320]
            except Exception:
                pass

    applied_corrections = []
    for correction in corrections:
        if correction.cluster_id != cluster_id:
            continue
        if correction.action in {"mark_same_root_cause", "mark_not_related"}:
            if _safe_text(correction.issue).lower() == _safe_text(issue_key).lower() or _safe_text(correction.reference_issue).lower() == _safe_text(issue_key).lower():
                applied_corrections.append(correction.action)
        elif correction.action in {"detach_from_cluster", "make_canonical"} and _safe_text(correction.issue).lower() == _safe_text(issue_key).lower():
            applied_corrections.append(correction.action)

    return {
        "issue": issue_key,
        "cluster_id": cluster_id,
        "cluster_type": issue_row.get("cluster_type", ""),
        "cluster": cluster_payload,
        "members": members,
        "open_matches": open_matches,
        "closed_matches": closed_matches,
        "status": issue_row.get("status", ""),
        "summary_url": summary_url,
        "summary_preview": summary_preview,
        "corrections_applied": sorted(set(applied_corrections)),
    }
