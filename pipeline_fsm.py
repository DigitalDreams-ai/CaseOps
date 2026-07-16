"""Validated CaseOps pipeline step transitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


STEPS = set(range(1, 13))
ALLOWED = {
    1: {2},
    2: {3, 11},
    3: {4},
    4: {5},
    5: {6},
    6: {5, 7},
    7: {8, 10},
    8: {9},
    9: {5, 10},
    10: {11},
    11: {12},
    12: set(),
}
LOOP_CAPS = {(6, 5): 3, (9, 5): 3}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    violation: str = ""


def _loop_key(from_step: int, to_step: int) -> str:
    return f"{from_step}->{to_step}"


def _counter_value(counts: dict[str, Any], key: str) -> int:
    try:
        return max(0, int(counts.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def validate_transition(state: dict[str, Any], from_step: int | None, to_step: int) -> TransitionResult:
    if to_step not in STEPS:
        return TransitionResult(False, "illegal_transition")
    if from_step is None or from_step == to_step:
        return TransitionResult(True)
    if from_step not in STEPS or to_step not in ALLOWED.get(from_step, set()):
        return TransitionResult(False, "illegal_transition")
    cap = LOOP_CAPS.get((from_step, to_step))
    if cap is not None:
        counts = state.get("loop_counts") if isinstance(state.get("loop_counts"), dict) else {}
        if _counter_value(counts, _loop_key(from_step, to_step)) >= cap:
            return TransitionResult(False, "loop_cap_exceeded")
    return TransitionResult(True)


def record_transition(state: dict[str, Any], to_step: int, at: str) -> dict[str, Any]:
    updated = deepcopy(state)
    transitions = updated.get("transitions") if isinstance(updated.get("transitions"), list) else []
    transitions = [item for item in transitions if isinstance(item, dict)]
    from_step = transitions[-1].get("step") if transitions else None
    try:
        from_step = int(from_step) if from_step is not None else None
    except (TypeError, ValueError):
        from_step = None
    result = validate_transition(updated, from_step, to_step)
    transitions.append({
        "step": int(to_step),
        "at": str(at),
        "violation": result.violation or None,
    })
    updated["transitions"] = transitions

    counts = dict(updated.get("loop_counts") or {}) if isinstance(updated.get("loop_counts"), dict) else {}
    if from_step is not None and from_step != to_step and (from_step, to_step) in LOOP_CAPS:
        key = _loop_key(from_step, to_step)
        counts[key] = _counter_value(counts, key) + 1
    updated["loop_counts"] = counts
    return updated


def latest_violation(state: dict[str, Any], violation: str | None = None) -> dict[str, Any] | None:
    transitions = state.get("transitions") if isinstance(state.get("transitions"), list) else []
    for item in reversed(transitions):
        if not isinstance(item, dict) or not item.get("violation"):
            continue
        if violation is None or item.get("violation") == violation:
            return item
    return None
