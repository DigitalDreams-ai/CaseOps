#!/usr/bin/env python3
"""Test Report Agent (Skill Step 8D).

Produces test report documenting test execution, results, and validation
after Sandbox deployment.

Usage:
    python test_report_agent.py --key HEAL-33150
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
        description="Test Report: document test execution and validation after Sandbox deployment."
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
    test_report_path = outputs_dir / "test-reports" / f"{key}.md"
    if test_report_path.exists():
        print(f"  [{key}] test report already exists, skipping")
        return 0

    # Read inputs
    internal_notes_path = outputs_dir / "internal-notes" / f"{key}.md"
    jira_dir = outputs_dir / "jira"
    jira_summary_path = jira_dir / "summary" / f"{key}.md"

    if not internal_notes_path.exists():
        print(
            f"  [{key}] ERROR: internal notes not found at {internal_notes_path}",
            file=sys.stderr,
        )
        return 1

    if not jira_summary_path.exists():
        print(f"  [{key}] ERROR: jira summary not found at {jira_summary_path}", file=sys.stderr)
        return 1

    internal_notes = internal_notes_path.read_text(encoding="utf-8")
    jira_summary = jira_summary_path.read_text(encoding="utf-8")

    # Load template
    template_dir = PROJECT_ROOT / "skills" / "jira-salesforce-fix-pipeline" / "assets"
    test_report_template = (template_dir / "test-report-template.md").read_text(
        encoding="utf-8"
    )

    # Build prompt
    prompt = f"""You are CaseOps quality assurance analyst.

## Issue: {key}

### Jira Summary
{jira_summary}

### Internal Notes (solution executed in Sandbox)
{internal_notes}

---

## Task: Produce Test Report

Document test execution, results, and validation. Use the internal notes to understand:
1. What was deployed to Sandbox
2. What testing is mentioned
3. What acceptance criteria exist

Create a comprehensive test report that:
- Lists test environment and deployment details
- Documents all test cases executed
- Shows results: pass/fail/blocked
- Validates against issue acceptance criteria
- Provides sign-off readiness statement

```markdown
{test_report_template}
```

---

## Response Format

Return ONLY a JSON code block with one field (no preamble or explanation):

```json
{{
  "test_report": "<filled markdown here>"
}}
```
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
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                response_data = json.loads(match.group(1))
            else:
                raise json.JSONDecodeError("No JSON found", response_text, 0)

        test_report_text = response_data.get("test_report", "").strip()
        if not test_report_text:
            print(f"  [{key}] ERROR: test_report field empty", file=sys.stderr)
            return 1
    except json.JSONDecodeError as e:
        print(f"  [{key}] ERROR: invalid JSON: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write output
    try:
        test_report_path.parent.mkdir(parents=True, exist_ok=True)
        test_report_path.write_text(test_report_text, encoding="utf-8")
        print(f"  [{key}] OK: test report written")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
