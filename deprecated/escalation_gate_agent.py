#!/usr/bin/env python3
"""Escalation Gate Agent (Skill Step 6).

Makes binary escalation decisions (Support-Resolvable OR Engineering-Required)
with confidence and evidence.

Reads investigation + internal notes, produces escalation gate decision.

Usage:
    python escalation_gate_agent.py --key HEAL-33150
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic

from caseops_paths import PROJECT_ROOT, default_jira_dir, default_jira_env_file


def load_env(env_file: Path) -> None:
    """Load .env into os.environ (non-destructive)."""
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not (value := value.strip().strip('"').strip("'")):
            continue
        if key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Escalation Gate: make binary escalation decision (Support-Resolvable OR Engineering-Required)."
    )
    parser.add_argument("--key", required=True, help="Jira issue key (e.g., HEAL-33150)")
    parser.add_argument(
        "--outputs-dir",
        default=str(PROJECT_ROOT / "outputs"),
        help="Outputs directory (default: PROJECT_ROOT/outputs)",
    )
    parser.add_argument(
        "--env-file",
        default=str(default_jira_env_file()),
        help="Jira env file (default: .env)",
    )
    args = parser.parse_args()

    key = args.key.strip()
    outputs_dir = Path(args.outputs_dir)

    # Load env
    load_env(Path(args.env_file))

    # Check if already processed (idempotent)
    escalation_gate_path = outputs_dir / "escalation-gates" / f"{key}.md"
    if escalation_gate_path.exists():
        print(f"  [{key}] escalation gate already exists, skipping")
        return 0

    # Read inputs
    investigation_path = outputs_dir / "investigations" / f"{key}.md"
    internal_notes_path = outputs_dir / "internal-notes" / f"{key}.md"

    if not investigation_path.exists():
        print(
            f"  [{key}] ERROR: investigation not found at {investigation_path}",
            file=sys.stderr,
        )
        return 1

    if not internal_notes_path.exists():
        print(
            f"  [{key}] ERROR: internal notes not found at {internal_notes_path}",
            file=sys.stderr,
        )
        return 1

    investigation = investigation_path.read_text(encoding="utf-8")
    internal_notes = internal_notes_path.read_text(encoding="utf-8")

    # Build prompt (focused escalation decision only)
    prompt = f"""You are CaseOps escalation gate analyst. Your job is to make a binary decision:
Support-Resolvable OR Engineering-Required.

## Issue: {key}

### Investigation Record
{investigation}

### Internal Notes (draft escalation decision)
{internal_notes}

---

## Task: Make Binary Escalation Decision with Confidence and Evidence

Based on the investigation and internal notes, determine:
1. **Decision**: Support-Resolvable OR Engineering-Required (binary, no maybe)
2. **Confidence**: High / Medium / Low (with 0-100% reasoning)
3. **Key Evidence**: 3-5 bullet points from investigation/notes that support decision
4. **Red Flags**: Any concerns that could cause human to review this decision
5. **Next Step**: Specific action (if Support: what fix to propose; if Engineering: handoff details)

---

## Response Format

Return ONLY a markdown document with these sections (no JSON, no preamble):

# Escalation Gate Decision — {key}

## Decision
[ONE of: "Support-Resolvable" or "Engineering-Required" — binary, clear]

## Confidence
[High / Medium / Low] — [0-100%] — [brief reasoning: why this confidence level]

## Key Evidence
- [Specific finding from investigation or internal notes]
- [Specific finding from investigation or internal notes]
- [Specific finding from investigation or internal notes]
- [Additional findings as needed]

## Red Flags
[If any concerns exist that warrant human review before proceeding, list them. If none, write: "None."]

## Next Step
[If Support-Resolvable: describe the minimal fix to propose.
If Engineering-Required: describe the engineering handoff or investigation needed.]

---

Generate ONLY the markdown document. No JSON. No code blocks. Pure markdown."""

    # Call Claude
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"  [{key}] ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    model = os.environ.get("CASEOPS_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_tokens = int(os.environ.get("CASEOPS_ANTHROPIC_MAX_TOKENS", "8192"))
    max_tokens = min(max(max_tokens, 256), 64000)

    try:
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text
    except Exception as e:
        print(f"  [{key}] ERROR: API call failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Validate response has required sections
    escalation_gate_text = response_text.strip()
    required_sections = ["Decision", "Confidence", "Key Evidence", "Red Flags", "Next Step"]
    missing_sections = [s for s in required_sections if f"## {s}" not in escalation_gate_text]
    if missing_sections:
        print(
            f"  [{key}] ERROR: missing sections: {', '.join(missing_sections)}",
            file=sys.stderr,
        )
        return 1

    # Validate binary decision
    if "Support-Resolvable" not in escalation_gate_text and "Engineering-Required" not in escalation_gate_text:
        print(
            f"  [{key}] ERROR: decision must be 'Support-Resolvable' or 'Engineering-Required'",
            file=sys.stderr,
        )
        return 1

    # Write output
    try:
        escalation_gate_path.parent.mkdir(parents=True, exist_ok=True)
        escalation_gate_path.write_text(escalation_gate_text, encoding="utf-8")
        print(f"  [{key}] OK: escalation gate written")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
