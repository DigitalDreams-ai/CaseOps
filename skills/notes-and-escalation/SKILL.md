---
name: notes-and-escalation
description: Analyzes investigation, decides solution path, produces internal notes and conditional engineering escalation. Focuses on root cause, deployment plan, and escalation criteria.
---

# Notes and Escalation Skill

This skill analyzes a completed investigation and makes the critical decision: solve in Sandbox or escalate to Engineering. Produces internal notes and engineering handoff details.

## When to Use

- You have a completed investigation record and need to decide solution path
- You need to diagnose root cause and create internal notes for the team
- You need to determine if Engineering involvement is required and create escalation brief

## When NOT to Use

- You're diagnosing the problem (use Investigation Finalization skill)
- You're testing a fix (use Test Report skill)
- You're writing customer communication (use Jira Response skill)

## Output

Produces:
- `outputs/internal-notes/<KEY>.md` (always)
- `outputs/engineering-escalations/<KEY>.md` (conditional — only if escalating)

Contains (Internal Notes):
- Root Cause Analysis
- Solution Path or Escalation Decision
- Production vs Sandbox Deployment Plan
- Engineering Handoff Details (if escalating)
- Metadata Changes and Testing Plan

Contains (Engineering Escalation — if needed):
- Engineering Message (issue + problem + potential fix)
- Steps to Reproduce
- Root Cause and Affected Component
- Production Deploy Context
- Evidence and References

## Usage

```bash
python notes_and_escalation_agent.py --key HEAL-33150
```

## Input Files Required

- `outputs/investigations/<KEY>.md` (from Investigation Finalization skill)
- `outputs/jira/summary/<KEY>.md` (Jira issue summary)

## Configuration

- `.env.jira`: ANTHROPIC_API_KEY, CASEOPS_ANTHROPIC_MODEL (optional), CASEOPS_ANTHROPIC_MAX_TOKENS (optional)

## Architecture Note

This is Step 8B in the CaseOps pipeline, handling root cause analysis and escalation decision.

Related skills:
- Step 5B: investigation-finalization
- Step 8B: notes-and-escalation (THIS SKILL)
- Step 8D: test-report-drafting
- Step 9: jira-response-drafting
