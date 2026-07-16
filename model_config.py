"""Shared validation for drift-resistant CaseOps model configuration."""

from __future__ import annotations

import re


# Accepts fully versioned Claude model ids, including gateway-prefixed forms:
#   claude-sonnet-4-6, claude-opus-4-1-20250805        (current naming)
#   claude-3-5-sonnet-20241022                          (legacy naming)
#   us.anthropic.claude-sonnet-4-5-20250929-v1:0        (Bedrock)
#   anthropic.claude-3-5-sonnet-20241022-v2:0           (Bedrock, unprefixed region)
#   claude-3-5-sonnet-v2@20241022                       (Vertex)
# Rejects aliases with no version information (sonnet, claude-sonnet) and
# floating tags (…-latest), which drift.
PINNED_MODEL_RE = re.compile(
    r"^(?:[a-z]{2,5}\.)?(?:anthropic\.)?claude-(?=[a-z0-9.@:\-]*\d)[a-z0-9.@:\-]+$",
    re.IGNORECASE,
)


def validate_pinned_model(value: str) -> str:
    model_id = str(value or "").strip()
    if not model_id:
        raise ValueError(
            "CASEOPS_ANTHROPIC_MODEL is not set. Pin a full versioned Claude model id in Settings or .env."
        )
    if not PINNED_MODEL_RE.match(model_id) or "latest" in model_id.lower():
        raise ValueError(
            f"CASEOPS_ANTHROPIC_MODEL '{model_id}' is not a versioned model id. "
            "Use a full versioned id (e.g. claude-sonnet-4-6, claude-3-5-sonnet-20241022, "
            "or a Bedrock/Vertex id such as us.anthropic.claude-sonnet-4-5-20250929-v1:0). "
            "Aliases such as 'sonnet', 'claude-sonnet', or '-latest' tags are not allowed "
            "because they drift."
        )
    return model_id
