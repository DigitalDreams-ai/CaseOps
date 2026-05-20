#!/usr/bin/env python3
"""Notes and Escalation Agent (Skill Step 8B).

Analyzes investigation record and produces internal notes + engineering escalation.
Focuses on root cause diagnosis, solution vs escalation decision, deployment plan.

Usage:
    python notes_and_escalation_agent.py --key HEAL-33150
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
    """Load .env.jira into os.environ (non-destructive)."""
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
        description="Notes and Escalation: analyze investigation and produce internal notes + escalation."
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
        help="Jira env file (default: .env.jira)",
    )
    args = parser.parse_args()

    key = args.key.strip()
    outputs_dir = Path(args.outputs_dir)

    # Load env
    load_env(Path(args.env_file))

    # Check if already processed (idempotent)
    internal_notes_path = outputs_dir / "internal-notes" / f"{key}.md"
    if internal_notes_path.exists():
        print(f"  [{key}] already has notes, skipping")
        return 0

    # Read inputs
    investigation_path = outputs_dir / "investigations" / f"{key}.md"
    jira_dir = outputs_dir / "jira"
    jira_summary_path = jira_dir / "summary" / f"{key}.md"

    if not investigation_path.exists():
        print(
            f"  [{key}] ERROR: investigation not found at {investigation_path}",
            file=sys.stderr,
        )
        return 1

    if not jira_summary_path.exists():
        print(f"  [{key}] ERROR: jira summary not found at {jira_summary_path}", file=sys.stderr)
        return 1

    investigation = investigation_path.read_text(encoding="utf-8")
    jira_summary = jira_summary_path.read_text(encoding="utf-8")

    # Load templates
    template_dir = PROJECT_ROOT / "skills" / "jira-salesforce-fix-pipeline" / "assets"
    internal_notes_template = (template_dir / "internal-notes-template.md").read_text(
        encoding="utf-8"
    )
    engineering_handoff_template = (template_dir / "engineering-handoff-template.md").read_text(
        encoding="utf-8"
    )

    # Build prompt
    prompt = f"""You are CaseOps support analyst and decision maker.

## Issue: {key}

### Jira Summary
{jira_summary}

### Investigation Record (completed analysis)
{investigation}

---

## Task: Produce Internal Notes + Escalation Decision

Analyze the investigation and decide: solve in Sandbox or escalate to Engineering?

### Output A — Internal Notes

Fill in the internal notes template. Focus on:
1. Root cause (NEW diagnosis: WHY is this happening or resolved? NOT a replay of Investigation findings. Be terse.)
2. Decision: Support-Resolvable OR Escalate to Engineering (with confidence + evidence)
3. Actions Taken (if resolvable) OR Engineering Handoff details (if escalating)
4. Production vs Sandbox deployment clarity (required)

```markdown
{internal_notes_template}
```

### Output B — Engineering Handoff (if escalating only)

If escalating: Internal Notes gets brief "reason + evidence", and full handoff details go in engineering-escalations/<KEY>.md.

Fill the detailed engineering handoff template below (if escalating):

```markdown
{engineering_handoff_template}
```

If NOT escalating (support-resolvable), leave engineering_handoff empty string.

---

## Response Format

Return ONLY a JSON code block with two fields (no preamble or explanation).

**CRITICAL: Output MUST be valid JSON. Escape all special characters. Do not truncate.**

```json
{{
  "internal_notes": "<filled markdown here — escape quotes and backslashes>",
  "engineering_handoff": "<filled markdown if escalating, else empty string>"
}}
```

If investigation is incomplete/thin (mostly templates), output brief notes saying "Awaiting customer response" or "Insufficient data to diagnose" — do NOT attempt deep analysis with sparse data.
"""

    # Call Claude
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"  [{key}] ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    model = os.environ.get("CASEOPS_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_tokens = int(os.environ.get("CASEOPS_ANTHROPIC_MAX_TOKENS", "16384"))
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


    # Parse response (extract JSON from code blocks if needed)
    try:
        # Try direct JSON parsing first
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from code block markers
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                response_data = json.loads(match.group(1))
            else:
                raise json.JSONDecodeError("No JSON found", response_text, 0)

        internal_notes_text = response_data.get("internal_notes", "").strip()
        engineering_handoff_text = response_data.get("engineering_handoff", "").strip()

        if not internal_notes_text:
            print(f"  [{key}] ERROR: internal_notes field empty", file=sys.stderr)
            return 1
    except json.JSONDecodeError as e:
        print(f"  [{key}] ERROR: invalid JSON: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write outputs
    try:
        internal_notes_path.parent.mkdir(parents=True, exist_ok=True)
        internal_notes_path.write_text(internal_notes_text, encoding="utf-8")

        # Write engineering handoff only if escalating
        if engineering_handoff_text:
            eng_escalations_path = outputs_dir / "engineering-escalations" / f"{key}.md"
            eng_escalations_path.parent.mkdir(parents=True, exist_ok=True)
            eng_escalations_path.write_text(engineering_handoff_text, encoding="utf-8")
            print(f"  [{key}] OK: notes + engineering escalation written")
        else:
            print(f"  [{key}] OK: notes written (no escalation)")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
