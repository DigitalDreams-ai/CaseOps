#!/usr/bin/env python3
"""Solution Planning Agent (Week 1 Skill).

Analyzes investigation record and internal notes, then proposes minimal viable fix.
Focuses on solution planning: what is the smallest fix that solves the problem?

Input:
  - outputs/investigations/{KEY}.md (required)
  - outputs/internal-notes/{KEY}.md (required, for escalation decision)

Output:
  - outputs/solution-plans/{KEY}.md

Usage:
    python solution_planning_agent.py --key HEAL-33150
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
        description="Solution Planning: analyze investigation and notes, propose minimal viable fix."
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
    solution_plan_path = outputs_dir / "solution-plans" / f"{key}.md"
    if solution_plan_path.exists():
        print(f"  [{key}] already has solution plan, skipping")
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

    # Build prompt
    prompt = f"""You are CaseOps solution architect. Your job: propose the MINIMAL VIABLE FIX.

## Issue: {key}

### Investigation
{investigation}

### Internal Notes (includes escalation decision)
{internal_notes}

---

## Task: Produce Solution Plan

Analyze the investigation and notes. Based on the escalation decision in the notes:
- If Support-Resolvable: propose the smallest fix that solves the problem
- If Escalated to Engineering: briefly describe what Engineering should investigate

Create a solution plan with 6 sections:

1. **Problem Statement** (from investigation) — what is broken, who is affected
2. **Escalation Decision** (from notes) — Support or Engineering, why
3. **Proposed Fix** (minimal viable) — exact steps, metadata changes, field values
4. **Affected Components** — list: fields, flows, validation rules, record types, layouts
5. **Dependencies** — what else must be true or change if this change happens
6. **Sandbox Plan + Risk + Rollback**
   - How to deploy to Sandbox
   - What could break (risk assessment)
   - How to undo if needed (rollback steps)

### Key Constraint: Justify "Minimal Viable Fix"

The most important part: explain WHY you chose this fix over bigger alternatives. Examples:
- "We could redesign the entire flow, but the customer only needs X field populated, which requires Y change."
- "Instead of creating new object, we reuse existing field Z because it serves the same purpose."
- "Skip the approval process because the current rule already validates this scenario."

Do NOT over-engineer. Do NOT propose changes that aren't necessary to solve the stated problem.

---

## Response Format

Return ONLY a JSON code block with one field (no preamble or explanation).
The markdown content must be valid JSON: escape double quotes as \" and newlines as \n:

```json
{{
  "solution_plan": "# Solution Plan\\n\\n## 1. Problem Statement\\n..."
}}
```

IMPORTANT: Every double quote in the markdown must be escaped as \". Every newline must be \n.
This ensures the JSON parses correctly.
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
        import re

        # Try direct JSON parsing first
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from code block markers
            # Find ``` markers and extract content between them
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
            if match:
                json_text = match.group(1).strip()
                # Remove leading { and trailing } if present
                if json_text.startswith("{"):
                    json_text = json_text
                try:
                    response_data = json.loads(json_text)
                except json.JSONDecodeError:
                    # Try to manually find the JSON object by counting braces
                    brace_start = response_text.find("{")
                    if brace_start >= 0:
                        # Find matching closing brace
                        depth = 0
                        brace_end = brace_start
                        in_string = False
                        escaped = False
                        for i in range(brace_start, len(response_text)):
                            c = response_text[i]
                            if escaped:
                                escaped = False
                                continue
                            if c == "\\":
                                escaped = True
                                continue
                            if c == '"' and not escaped:
                                in_string = not in_string
                                continue
                            if not in_string:
                                if c == "{":
                                    depth += 1
                                elif c == "}":
                                    depth -= 1
                                    if depth == 0:
                                        brace_end = i + 1
                                        break
                        if depth == 0:
                            json_text = response_text[brace_start:brace_end]
                            response_data = json.loads(json_text)
                        else:
                            raise json.JSONDecodeError("Unbalanced braces", response_text, brace_start)
                    else:
                        raise json.JSONDecodeError("No JSON found", response_text, 0)
            else:
                raise json.JSONDecodeError("No code block found", response_text, 0)

        solution_plan_text = response_data.get("solution_plan", "").strip()
        if not solution_plan_text:
            print(f"  [{key}] ERROR: solution_plan field empty", file=sys.stderr)
            return 1
    except json.JSONDecodeError as e:
        print(f"  [{key}] ERROR: invalid JSON: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write output
    try:
        solution_plan_path.parent.mkdir(parents=True, exist_ok=True)
        solution_plan_path.write_text(solution_plan_text, encoding="utf-8")
        print(f"  [{key}] OK: solution plan written")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
