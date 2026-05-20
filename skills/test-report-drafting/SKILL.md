---
name: test-report-drafting
description: Documents test execution, results, and validation after Sandbox deployment. Produces comprehensive test report with sign-off readiness statement.
---

# Test Report Drafting Skill

This skill documents test execution and results after Sandbox deployment. Produces a comprehensive test report validating the fix against acceptance criteria.

## When to Use

- You have executed tests in Sandbox and need to document results
- You need to validate fix against acceptance criteria
- You need sign-off readiness statement for production deployment

## When NOT to Use

- You're diagnosing the problem (use Investigation Finalization skill)
- You're deciding solution path (use Notes & Escalation skill)
- You haven't executed tests yet

## Output

Produces: `outputs/test-reports/<KEY>.md`

Contains:
- Test Environment Details
- Test Cases Executed
- Test Results (pass/fail/blocked)
- Validation Against Acceptance Criteria
- Sign-Off and Readiness Statement

## Usage

```bash
python test_report_agent.py --key HEAL-33150
```

## Input Files Required

- `outputs/internal-notes/<KEY>.md` (from Notes & Escalation skill)
- `outputs/jira/summary/<KEY>.md` (Jira issue summary)

## Configuration

- `.env.jira`: ANTHROPIC_API_KEY, CASEOPS_ANTHROPIC_MODEL (optional), CASEOPS_ANTHROPIC_MAX_TOKENS (optional)

## Architecture Note

This is Step 8D in the CaseOps pipeline, handling quality assurance and sign-off validation.

Related skills:
- Step 5B: investigation-finalization
- Step 8B: notes-and-escalation
- Step 8D: test-report-drafting (THIS SKILL)
- Step 9: jira-response-drafting
