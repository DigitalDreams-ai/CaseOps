"""Deterministic artifact gates for CaseOps pipeline progression."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MIN_ARTIFACT_BYTES = 400
HYPOTHESIS_HEADINGS = (
    "Problem Hypothesis",
    "Smallest Viable Fix",
    "Sandbox Validation Plan",
)
HYPOTHESIS_PLACEHOLDERS = (
    "[One-sentence statement",
    "[Fact 1:",
    "[Exact component",
    "[Test scenario 1:",
    "<KEY>",
    "<YYYY-MM-DD>",
)
_HEADING_LINE_RE = re.compile(r"(?m)^\s*(?P<marks>#{1,6}\s*)?(?P<text>[^\r\n]+?)\s*$")


@dataclass(frozen=True)
class GateResult:
    passed: bool
    gate: str
    reason: str
    details: dict[str, bool]


def _read_artifact(path: Path, gate: str) -> tuple[str, GateResult | None]:
    if not path.is_file():
        return "", GateResult(False, gate, f"Artifact is missing: {path.name}", {"exists": False})
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return "", GateResult(False, gate, f"Artifact cannot be read: {exc}", {"exists": True, "readable": False})
    if len(raw) < MIN_ARTIFACT_BYTES:
        return "", GateResult(
            False,
            gate,
            f"Artifact is too short ({len(raw)} bytes; minimum {MIN_ARTIFACT_BYTES})",
            {"exists": True, "readable": True, "minimum_size": False},
        )
    return raw.decode("utf-8", errors="replace"), None


def _normalized_heading(value: str) -> str:
    value = re.sub(r"[*_`:#]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def _heading_positions(text: str) -> list[tuple[int, int, str]]:
    positions: list[tuple[int, int, str]] = []
    known_plain_headings = {
        _normalized_heading(value)
        for value in (*HYPOTHESIS_HEADINGS, "Open Questions")
    }
    for match in _HEADING_LINE_RE.finditer(text):
        heading = _normalized_heading(match.group("text"))
        if heading and (match.group("marks") or heading in known_plain_headings):
            positions.append((match.start(), match.end(), heading))
    return positions


def _has_heading(text: str, expected: str) -> bool:
    wanted = _normalized_heading(expected)
    return any(heading == wanted for _, _, heading in _heading_positions(text))


def _section_text(text: str, heading: str) -> str:
    wanted = _normalized_heading(heading)
    positions = _heading_positions(text)
    candidates: list[str] = []
    for index, (_start, end, current) in enumerate(positions):
        if current != wanted:
            continue
        next_start = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        candidates.append(text[end:next_start])
    return max(candidates, key=_plain_markdown_length) if candidates else ""


def _plain_markdown_length(value: str) -> int:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"[*_`#>\[\]()]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return len(value.strip())


def validate_hypothesis_artifact(outputs: Path, key: str) -> GateResult:
    gate = "step4_hypothesis"
    path = Path(outputs) / "hypothesis" / f"{key}.md"
    text, failure = _read_artifact(path, gate)
    if failure:
        return failure

    details: dict[str, bool] = {"exists": True, "readable": True, "minimum_size": True}
    missing_headings = [heading for heading in HYPOTHESIS_HEADINGS if not _has_heading(text, heading)]
    details["required_headings"] = not missing_headings
    if missing_headings:
        return GateResult(False, gate, f"Missing required heading(s): {', '.join(missing_headings)}", details)

    remaining = [placeholder for placeholder in HYPOTHESIS_PLACEHOLDERS if placeholder.casefold() in text.casefold()]
    details["placeholders_removed"] = not remaining
    if remaining:
        return GateResult(False, gate, f"Template placeholder remains: {remaining[0]}", details)

    hypothesis_section = _section_text(text, "Problem Hypothesis")
    root_match = re.search(r"(?is)(?:\*\*)?Root cause hypothesis(?:\*\*)?\s*:\s*(.+)", hypothesis_section)
    root_text = root_match.group(1) if root_match else ""
    if root_match:
        next_label = re.search(r"(?m)^\s*(?:\*\*)?[A-Za-z][^\r\n:]{1,60}(?:\*\*)?\s*:\s*", root_text)
        if next_label:
            root_text = root_text[: next_label.start()]
    details["root_cause_substantive"] = _plain_markdown_length(root_text) >= 40
    if not details["root_cause_substantive"]:
        return GateResult(False, gate, "Root cause hypothesis must contain at least 40 characters of substantive text", details)

    fix_section = _section_text(text, "Smallest Viable Fix")
    artifact_match = re.search(r"(?im)^\s*[-*]?\s*(?:\*\*)?Artifact\s*:\s*(?:\*\*)?\s*(.+?)\s*$", fix_section)
    artifact = artifact_match.group(1).strip().strip("*_").strip() if artifact_match else ""
    artifact_is_placeholder = artifact.startswith("[") or artifact.startswith("<")
    details["artifact_named"] = len(artifact) >= 4 and not artifact_is_placeholder
    if not details["artifact_named"]:
        return GateResult(False, gate, "Smallest Viable Fix must name a concrete Artifact", details)

    return GateResult(True, gate, "", details)
