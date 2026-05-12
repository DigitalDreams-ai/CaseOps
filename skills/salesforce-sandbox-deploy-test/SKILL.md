---
name: salesforce-sandbox-deploy-test
description: Deploys a local Salesforce fix to an approved Sandbox and tests it against Jira acceptance criteria. Use after a solution has been implemented locally and needs Sandbox validation.
---

# Salesforce Sandbox Deploy Test

## Use This Skill When

- A Salesforce fix is ready for Sandbox deployment.
- The target Sandbox is known or can be confirmed.
- Tests need to prove whether the Jira problem is fixed.
- The `jira-salesforce-fix-pipeline` delegates deploy and test as Step 8. On test failure, control returns to the pipeline for re-diagnosis and re-implementation before this skill is re-invoked.

## Do Not Use This Skill When

- The target is Production.
- The implementation is not ready.
- The user has not approved or identified a Sandbox target.
- The solution requires Engineering ownership, including Apex/code, flow, approval process, or validation rule changes, unless the user explicitly overrides the escalation rule.

## Workflow

**DEPLOYMENT RULES — check before step 4.**

- The predefined sandbox for this project is `10xhealth-sean` (`CASEOPS_SANDBOX_TARGET_ORG`). Deploying here does not require additional confirmation.
- Deploying to Production (`10xhealth`) is NEVER permitted. If the target resolves to a Production org, STOP immediately and report the error to the user.
- Deploying to any other org requires explicit user approval in the current conversation before proceeding.
- The change must have passed the Engineering escalation gate.

If any rule is violated, do not deploy. Report the blocker to the user and wait.

1. Confirm the target Sandbox alias is `10xhealth-sean` (or another org the user has explicitly approved in this conversation).
2. Confirm the change has passed the Engineering escalation gate.
3. Review changed metadata and expected deployment scope.
4. Deploy to Sandbox only.
5. Run automated tests when available.
6. Run manual or data-driven validation against Jira acceptance criteria.
7. Record results in `assets/test-report-template.md`.
8. If the issue is not fixed, report the failed test evidence and return to diagnosis.

## References

- `references/deploy-test-guide.md`: Deployment and testing guidance.

## Assets

- `assets/test-report-template.md`: Sandbox test report format.

## Quality Checks

- Target org is not Production.
- Engineering-owned changes were not deployed by this skill unless explicitly approved as an override.
- Deployment command and result are recorded.
- Tests map to Jira acceptance criteria.
- Failure evidence is preserved.
