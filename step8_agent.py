#!/usr/bin/env python3
"""Step 8: Non-interactive agent for diagnosis, escalation gate, internal notes, Jira message.

Per issue: load context (Jira summary + investigation), call Claude,
parse response (---INTERNAL-NOTES---, ---JIRA-MESSAGE---), write outputs.

Usage:
    python step8_agent.py --key HEAL-33150
"""

from __future__ import annotations

import argparse
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


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code block markers (```) from text."""
    text = text.strip()  # Remove leading/trailing whitespace first
    lines = text.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 8 agent: diagnose, escalate gate, draft notes/message per issue."
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
    jira_dir = outputs_dir / "jira"

    # Load env
    load_env(Path(args.env_file))

    # Check if already processed (idempotent)
    internal_notes_path = outputs_dir / "internal-notes" / f"{key}.md"
    jira_message_path = outputs_dir / "jira-messages" / f"{key}.md"
    investigation_path = outputs_dir / "investigations" / f"{key}.md"
    if internal_notes_path.exists() and jira_message_path.exists() and investigation_path.exists():
        print(f"  [{key}] already processed, skipping")
        return 0

    # Read context
    jira_summary_path = jira_dir / "summary" / f"{key}.md"
    investigation_path = outputs_dir / "investigations" / f"{key}.md"

    if not jira_summary_path.exists():
        print(f"  [{key}] ERROR: jira summary not found at {jira_summary_path}", file=sys.stderr)
        return 1

    jira_summary = jira_summary_path.read_text(encoding="utf-8")
    investigation = (
        investigation_path.read_text(encoding="utf-8")
        if investigation_path.exists()
        else "(investigation record not yet created)"
    )

    # Load templates
    template_dir = PROJECT_ROOT / "skills" / "jira-salesforce-fix-pipeline" / "assets"
    internal_notes_template = (template_dir / "internal-notes-template.md").read_text(
        encoding="utf-8"
    )
    jira_message_template = (template_dir / "jira-message-template.md").read_text(
        encoding="utf-8"
    )
    investigation_template = (template_dir / "investigation-record-template.md").read_text(
        encoding="utf-8"
    )

    # Build prompt
    prompt = f"""You are CaseOps, a Salesforce Support agent AI.

## Issue: {key}

### Jira Summary
{jira_summary}

### Investigation Record (scaffold from pipeline Steps 1-7)
{investigation}

---

## Task

Analyze this Salesforce support issue and produce three outputs.

### Output A — Investigation Record (Issue Understanding + Salesforce Problem sections)

Fill in **ALL** subsections below by extracting or inferring from the Jira summary. Every section must have content—no section should be left blank. Use the Jira summary to populate:

**Issue Understanding:**
- Observed Behavior: what the customer reported seeing / what is broken / what does not work
- Expected Behavior: what should happen instead / the desired outcome
- Acceptance Criteria: acceptance criteria or requirements from the issue if present; if none listed, infer from context
- Attachments Or Evidence: any attachments or key evidence mentioned; if none, note "None provided"
- Unknowns: what information is still needed / ambiguities or gaps in the issue description; if none, note "N/A"

**Salesforce Problem:**
- Confirmed Facts: facts about the org, the field/object involved, the feature, the limitation, or the gap (do not leave blank)
- Hypotheses: potential root causes or likely explanations for the issue; if already clear, state the known cause
- Likely Affected Metadata: Salesforce components/fields/objects involved; reference the types and names from the Jira summary

```markdown
{investigation_template}
```

### Output B — Internal Notes

Fill in the following template with your diagnosis, root cause, escalation decision, and any fix notes. If escalating to Engineering, mark that clearly.

```markdown
{internal_notes_template}
```

### Output C — Jira Message

Fill in the appropriate block (Confirmed Fix OR Engineering Escalation — delete the other):

```markdown
{jira_message_template}
```

---

## Response Format

Return exactly:
```
---INVESTIGATION---
<filled investigation record markdown here>
---INTERNAL-NOTES---
<filled internal notes markdown here>
---JIRA-MESSAGE---
<filled jira message markdown here>
```

Do NOT include any other text before or after these markers.
"""

    # Call Claude
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"  [{key}] ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    model = os.environ.get("CASEOPS_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_tokens = int(os.environ.get("CASEOPS_ANTHROPIC_MAX_TOKENS", "16384"))
    max_tokens = min(max(max_tokens, 256), 64000)  # Clamp to [256, 64000]

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

    # Parse response
    if ("---INVESTIGATION---" not in response_text or
        "---INTERNAL-NOTES---" not in response_text or
        "---JIRA-MESSAGE---" not in response_text):
        print(
            f"  [{key}] ERROR: response missing required markers",
            file=sys.stderr,
        )
        return 1

    try:
        before, sep1, after_marker1 = response_text.partition("---INVESTIGATION---")
        if not sep1:
            raise ValueError("---INVESTIGATION--- marker not found")

        # Everything between INVESTIGATION and INTERNAL-NOTES
        investigation_part, sep2, after_marker2 = after_marker1.partition("---INTERNAL-NOTES---")
        if not sep2:
            raise ValueError("---INTERNAL-NOTES--- marker not found")

        # Everything between INTERNAL-NOTES and JIRA-MESSAGE
        internal_notes_part, sep3, after_marker3 = after_marker2.partition("---JIRA-MESSAGE---")
        if not sep3:
            raise ValueError("---JIRA-MESSAGE--- marker not found")

        # Everything after JIRA-MESSAGE until next marker or end
        jira_message_part = after_marker3.split("---")[0]  # Stop at next marker if exists

        investigation_text = strip_markdown_fences(investigation_part)
        internal_notes = strip_markdown_fences(internal_notes_part)
        jira_message = strip_markdown_fences(jira_message_part)

        if not investigation_text or not internal_notes or not jira_message:
            print(
                f"  [{key}] ERROR: parsed sections are empty",
                file=sys.stderr,
            )
            return 1
    except Exception as e:
        print(f"  [{key}] ERROR: response parsing failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    # Write outputs
    try:
        internal_notes_path.parent.mkdir(parents=True, exist_ok=True)
        jira_message_path.parent.mkdir(parents=True, exist_ok=True)
        investigation_path.parent.mkdir(parents=True, exist_ok=True)

        investigation_path.write_text(investigation_text, encoding="utf-8")
        internal_notes_path.write_text(internal_notes, encoding="utf-8")
        jira_message_path.write_text(jira_message, encoding="utf-8")

        # Check if this is a confirmed solution (not escalated to engineering)
        # Look for "Required?:" in Engineering Handoff section of investigation record
        is_escalated = False
        if "## Engineering Handoff" in investigation_text:
            for line in investigation_text.split("\n"):
                if "required?" in line.lower() and ":" in line:
                    # Extract the value after the colon (e.g., "YES" or "No")
                    value = line.split(":", 1)[1].strip().lower().strip("*").strip()
                    if value.startswith("yes"):
                        is_escalated = True
                    break
        has_solution = not is_escalated

        # Write solution marker if applicable
        if has_solution:
            solutions_dir = outputs_dir / "solutions"
            solutions_dir.mkdir(parents=True, exist_ok=True)
            (solutions_dir / f"{key}").write_text("", encoding="utf-8")
    except Exception as e:
        print(f"  [{key}] ERROR: write failed: {str(e)[:200]}", file=sys.stderr)
        return 1

    print(f"  [{key}] OK: internal notes + jira message written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
