---
name: investigation-finalization
description: Analyzes Salesforce issues for diagnosis. Produces investigation record with problem analysis, Salesforce configuration, and due diligence findings. Does not produce solution plan or internal notes.
---

# Investigation Finalization Skill

This skill analyzes a Salesforce support issue in depth and produces the investigation record (diagnosis artifact).

## When to Use

- You have a Jira issue with summary and you need to diagnose the problem
- You need to understand what is broken, why, and what similar existing Salesforce config exists
- You want to enforce due diligence: finding similar existing items and ensuring consistency

## When NOT to Use

- You''re drafting a solution (use Notes & Escalation skill)
- You''re testing a fix (use Test Report skill)
- You''re writing customer communication (use Jira Response skill)

## Output

Produces: `outputs/investigations/<KEY>.md`

Contains:
- Issue Understanding (what customer reported, what should happen, acceptance criteria)
- Salesforce Problem Analysis (confirmed facts, hypotheses, affected metadata)
- Similar Items Analysis (due diligence: similar existing items and their configuration)
- Production Metadata Retrieved (if applicable)

## Usage

```bash
python investigation_finalization_agent.py --key HEAL-33150
```

## Input Files Required

- `outputs/jira/summary/<KEY>.md` (Jira issue summary from sync)

## Configuration

- `.env.jira`: ANTHROPIC_API_KEY, CASEOPS_ANTHROPIC_MODEL (optional), CASEOPS_ANTHROPIC_MAX_TOKENS (optional)

## Architecture Note

This is Step 5B in the CaseOps pipeline, separating problem diagnosis from solution planning.

Related skills:
- Step 3: jira-issue-analysis
- Step 5: salesforce-production-metadata-investigation
- Step 5B: investigation-finalization (THIS SKILL)
- Step 8B: notes-and-escalation
- Step 9: jira-response-drafting
- Step 8D: test-report-drafting
