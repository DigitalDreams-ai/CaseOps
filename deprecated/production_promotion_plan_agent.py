#!/usr/bin/env python3
"""Production Promotion Plan Agent (Week 3 Skill).

CRITICAL: Proposal-only. This skill NEVER executes Production changes.
Reads solution plan and test report, proposes safe Production promotion plan.
All Production access is read-only. Only the operator can authorize execution via explicit request.

Input:
  - outputs/solution-plans/{KEY}.md (required, affected components)
  - outputs/test-reports/{KEY}.md (required, validation proof)
  - outputs/internal-notes/{KEY}.md (optional, deployment notes)

Output:
  - outputs/promotion-plans/{KEY}.md (proposal only, never executes)

Usage:
    python production_promotion_plan_agent.py --key HEAL-33150

SAFETY GUARANTEE:
- No sf deploy, sfdx deploy, or any Production write capability
- Output is markdown proposal only
- Operator executes manually after the operator's explicit "proceed" request
- All steps are concrete (exact CLI commands, not vague instructions)
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
        description="Production Promotion Plan: propose safe Production deployment plan (PROPOSAL ONLY, requires explicit operator approval)"
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
    promotion_plan_path = outputs_dir / "promotion-plans" / f"{key}.md"
    if promotion_plan_path.exists():
        print(f"  [{key}] promotion plan already exists, skipping")
        return 0

    # Read inputs
    solution_plan_path = outputs_dir / "solution-plans" / f"{key}.md"
    test_report_path = outputs_dir / "test-reports" / f"{key}.md"
    internal_notes_path = outputs_dir / "internal-notes" / f"{key}.md"

    if not solution_plan_path.exists():
        print(
            f"  [{key}] ERROR: solution plan not found at {solution_plan_path}",
            file=sys.stderr,
        )
        return 1

    if not test_report_path.exists():
        print(
            f"  [{key}] ERROR: test report not found at {test_report_path}",
            file=sys.stderr,
        )
        return 1

    solution_plan = solution_plan_path.read_text(encoding="utf-8")
    test_report = test_report_path.read_text(encoding="utf-8")

    # Internal notes are optional but helpful
    internal_notes = ""
    if internal_notes_path.exists():
        internal_notes = internal_notes_path.read_text(encoding="utf-8")

    # Load environment deployment method preference
    deploy_method = os.environ.get("CASEOPS_DEPLOY_METHOD", "sf-project-deploy").lower()
    sandbox_target = os.environ.get("CASEOPS_SANDBOX_TARGET_ORG", "sandbox")

    # Build prompt (CRITICAL: proposal-only, no execution)
    prompt = f"""You are CaseOps Production promotion specialist.

## CRITICAL SAFETY NOTE

This skill PROPOSES a promotion plan only. It NEVER executes any Production changes.
- CaseOps has ZERO authority to write to Production
- Only the operator can authorize Production deployment via explicit request
- You MUST state on every plan: "Awaiting the operator's explicit authorization. Do not execute without approval."

## Issue: {key}

### Solution Plan (what changes in Production)
{solution_plan}

### Test Report (proof of Sandbox validation)
{test_report}

{f'### Internal Notes (deployment context)' + chr(10) + internal_notes if internal_notes else ''}

---

## Task: Produce Production Promotion Plan (PROPOSAL ONLY)

Analyze the solution plan and test report. Propose a safe, concrete Production promotion plan.

The plan must have 6 sections:

### 1. Summary
What metadata will change in Production? List: objects, fields, flows, validation rules, etc.

### 2. Pre-Deployment Checklist
Verify BEFORE deploying to Production:
- Current Production state (does field exist, is flow active, etc.)
- Sandbox validation results (from test report)
- No conflicting pending changes
- Backup/rollback readiness

Provide exact CLI commands to verify each item in Production.
Example: `sf org display --verbose --target-org prod | grep -A5 "API version"`

### 3. Promotion Steps (EXACT CLI COMMANDS)
Provide the exact CLI commands operator will execute. NO vague instructions.

Current deployment method: {deploy_method}
Target sandbox: {sandbox_target}

Supported methods:
- "sf-project-deploy": Use 'sf project deploy' with specific metadata items
  Example: sf project deploy start --metadata "CustomObject__c,CustomField__c" --target-org prod --json
- "sf-cli-retrieve-deploy": Retrieve from sandbox, deploy to Production
  Example: sf retrieve --metadata "CustomObject__c" --target-org {sandbox_target}

For each step:
1. Exact command to run
2. What it does
3. Expected output indicators (what "success" looks like)

### 4. Post-Deployment Validation Steps
How to verify in Production after deploy:
- Check field exists and has correct type
- Check flow is active and running
- Check validation rules fire correctly
- Run sample test case from original issue

Provide exact CLI or manual verification steps. Examples:
- "sf data query --query 'SELECT Id, Field__c FROM Object__c LIMIT 1' --target-org prod"
- "In Setup > Flows, verify 'Flow Name' shows 'Active' status"

### 5. Rollback Plan
If validation fails, how to undo (with exact steps):
- Remove metadata deployed
- Restore previous field/flow values
- Verify rollback complete

Exact CLI commands for rollback. Example:
- sf project deploy start --metadata "CustomObject__c" --target-org prod --delete

### 6. Sign-Off Criteria
When is Production safe? Measurable criteria:
- Field exists with correct type/length ✓
- Flow is active and executing ✓
- Validation rule fires on test case ✓
- Customer confirmation: [specific test case re-run]

---

## RESPONSE FORMAT

Return ONLY a JSON code block (no preamble, no explanation):

```json
{{
  "promotion_plan": "CRITICAL: Awaiting the operator's explicit authorization. Do not execute without approval.\\n\\n# Production Promotion Plan: {key}\\n\\n..."
}}
```

CRITICAL RULES:
1. Start with "⚠️ Awaiting the operator's explicit authorization. Do not execute without approval."
2. Every step must be concrete (exact command, not "use Gearset" or "contact admin")
3. Rollback must be as detailed as promotion
4. All double quotes in markdown escaped as \", all newlines as \\n
5. Zero auto-execution code (this is proposal only)

NEVER include: commands that execute automatically, direct Production changes, or assumptions.
Always include: exact CLI commands, validation steps, and explicit approval requirement.
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

        promotion_plan_text = response_data.get("promotion_plan", "").strip()
        if not promotion_plan_text:
            print(f"  [{key}] ERROR: promotion_plan field empty", file=sys.stderr)
            return 1

        # SAFETY CHECK: verify authorization statement is present
        if "awaiting" not in promotion_plan_text.lower() or "authorization" not in promotion_plan_text.lower():
            print(
                f"  [{key}] WARNING: promotion plan missing explicit authorization statement, prepending",
                file=sys.stderr,
            )
            promotion_plan_text = (
                "⚠️ Awaiting the operator's explicit authorization. Do not execute without approval.\n\n"
                + promotion_plan_text
            )

    except json.JSONDecodeError as e:
        print(f"  [{key}] ERROR: invalid JSON: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write output
    try:
        promotion_plan_path.parent.mkdir(parents=True, exist_ok=True)
        promotion_plan_path.write_text(promotion_plan_text, encoding="utf-8")
        print(f"  [{key}] OK: promotion plan written")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
