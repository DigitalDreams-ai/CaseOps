# Sandbox Deploy And Test Guide

## Hard allowlist (read first)

- Open **`.env.jira`** in the repo root and read **`CASEOPS_SANDBOX_TARGET_ORG`**. That string is the **only** org allowed for deploys, metadata writes, and mutating Data/API operations in this skill.
- Compare your Salesforce CLI default org, `--target-org`, and any UI session to that value **before** any write. Mismatch → **STOP**; do not deploy to a different sandbox “temporarily.”
- If the variable is unset, **STOP** and ask the operator to add it to `.env.jira`.
- Changing the allowlisted org is done by editing **`.env.jira`**, not by improvising another target in chat.

## Before deploying

- Confirm the allowlisted Sandbox alias or username matches `CASEOPS_SANDBOX_TARGET_ORG`.
- Confirm the change is Support-resolvable. If it requires Apex/code, flow, approval process, or validation rule changes, stop and produce an Engineering handoff unless the user explicitly overrides the escalation rule.
- Review the local diff.
- Confirm the deployment scope.
- Identify tests to run.

After deploying:

- Capture deployment command and result.
- Run Apex tests or relevant validation commands when available.
- Validate the Jira reproduction steps.
- Record actual results, not just pass/fail.

If validation fails:

- Record the failed case.
- Identify whether the implementation, hypothesis, test data, or metadata scope was wrong.
- Return to the main pipeline for another iteration.
