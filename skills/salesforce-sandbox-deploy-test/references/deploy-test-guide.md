# Sandbox Deploy And Test Guide

Before deploying:

- Confirm the Sandbox alias or username.
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
