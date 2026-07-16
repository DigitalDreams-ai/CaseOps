"""Shared validation for drift-resistant CaseOps model configuration."""

from __future__ import annotations

import re


PINNED_MODEL_RE = re.compile(r"^claude-[a-z]+-[0-9]", re.IGNORECASE)


def validate_pinned_model(value: str) -> str:
    model_id = str(value or "").strip()
    if not model_id:
        raise ValueError(
            "CASEOPS_ANTHROPIC_MODEL is not set. Pin a full versioned Claude model id in Settings or .env."
        )
    if not PINNED_MODEL_RE.match(model_id):
        raise ValueError(
            f"CASEOPS_ANTHROPIC_MODEL '{model_id}' is not a versioned model id. "
            "Aliases such as 'sonnet' or 'claude-sonnet' are not allowed."
        )
    return model_id
