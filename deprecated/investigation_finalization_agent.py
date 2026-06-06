#!/usr/bin/env python3
"""Investigation Finalization Agent (Skill Step 5B).

Analyzes Salesforce support issue and produces investigation record only.
Focuses on problem diagnosis: issue understanding, Salesforce configuration,
similar items analysis. Does NOT produce solution plan or internal notes.

Usage:
    python investigation_finalization_agent.py --key HEAL-33150
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
        description="Investigation Finalization: analyze issue and produce investigation record."
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
    jira_dir = outputs_dir / "jira"

    # Load env
    load_env(Path(args.env_file))

    # Check if already processed (idempotent)
    investigation_path = outputs_dir / "investigations" / f"{key}.md"
    if investigation_path.exists():
        print(f"  [{key}] already investigated, skipping")
        return 0

    # Read context
    jira_summary_path = jira_dir / "summary" / f"{key}.md"

    if not jira_summary_path.exists():
        print(f"  [{key}] ERROR: jira summary not found at {jira_summary_path}", file=sys.stderr)
        return 1

    jira_summary = jira_summary_path.read_text(encoding="utf-8")

    # Load template
    template_dir = PROJECT_ROOT / "skills" / "jira-salesforce-fix-pipeline" / "assets"
    investigation_template = (template_dir / "investigation-record-template.md").read_text(
        encoding="utf-8"
    )

    # Build prompt (focused on investigation only)
    prompt = f"""You are CaseOps investigation analyst.

## Issue: {key}

### Jira Summary
{jira_summary}

---

## Task: Produce Investigation Record Only

Analyze this issue and fill the investigation template. Focus on:
1. Issue understanding (what customer reported, what should happen)
2. Salesforce problem analysis (confirmed facts, similar items, configuration)
3. Due diligence (find similar existing items, document their config)

DO NOT include: escalation decision, solution plan, deployment steps, testing, or iterations.

```markdown
{investigation_template}
```

---

## Response Format

Return ONLY a JSON code block with one field (no preamble or explanation):

```json
{{
  "investigation": "<filled markdown here>"
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
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                response_data = json.loads(match.group(1))
            else:
                raise json.JSONDecodeError("No JSON found", response_text, 0)

        investigation_text = response_data.get("investigation", "").strip()
        if not investigation_text:
            print(f"  [{key}] ERROR: investigation field empty", file=sys.stderr)
            return 1
    except json.JSONDecodeError as e:
        print(f"  [{key}] ERROR: invalid JSON: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write output
    try:
        investigation_path.parent.mkdir(parents=True, exist_ok=True)
        investigation_path.write_text(investigation_text, encoding="utf-8")
        print(f"  [{key}] OK: investigation written")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
