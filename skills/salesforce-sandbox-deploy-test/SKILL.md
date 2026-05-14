---
name: salesforce-sandbox-deploy-test
description: Mandatory for jira-salesforce-fix-pipeline after Support-owned implementation. Deploys only to the single allowlisted Sandbox from CASEOPS_SANDBOX_TARGET_ORG in .env.jira, tests against Jira acceptance criteria, and records results. Refuse any deploy or data write to any other org.
---

# Salesforce Sandbox Deploy Test

## Hard requirements (non-negotiable)

1. **Mandatory** when `jira-salesforce-fix-pipeline` has implemented a Support-resolvable fix (Step 7 complete). You must run deploy + validation before drafting customer-facing outcomes that claim a fix. Do not skip this skill on that path. The only skip is when the pipeline took the **Engineering escalation** branch (no implementation, no deploy).
2. **Single writable org:** Read **`CASEOPS_SANDBOX_TARGET_ORG`** from repo **`.env.jira`**. That value is the **only** Salesforce org (alias or username) that may receive **deploys, metadata writes, or mutating data/API operations** for this skill. Treat it as the org allowlist.
3. If **`CASEOPS_SANDBOX_TARGET_ORG`** is missing or empty in `.env.jira`, **STOP** — do not deploy; tell the operator to set it.
4. Before any deploy or write, confirm the CLI/API target (e.g. `sf` `--target-org`, org picker, or session) **exactly matches** that allowlisted value. If it does not match, **STOP** — do not “pick the closest sandbox” or override in chat.
5. **Production and all other orgs:** No deploy and no mutating operations unless the org is exactly the allowlisted sandbox value. Production remains **read-only** for investigation only (separate skills/prompts).

## Use This Skill When

- `jira-salesforce-fix-pipeline` Step 8 invokes you after implementation, **or**
- Another workflow explicitly assigns Sandbox validation with the same allowlist rules.

## Do Not Use This Skill When

- The pipeline classified the work as **Engineering escalation** (no Support implementation to deploy).
- The implementation is not ready (no changes to deploy).
- **`CASEOPS_SANDBOX_TARGET_ORG`** is not set in `.env.jira`.
- The only available org target does not match **`CASEOPS_SANDBOX_TARGET_ORG`**.

## Workflow

**Verify allowlist before any mutating command.**

1. Read **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira`. Record it in the test report.
2. Confirm the change passed the **Engineering escalation gate** (Support-resolvable only).
3. Review changed metadata and expected deployment scope.
4. Deploy **only** to the allowlisted Sandbox (target must match step 1).
5. Run automated tests when available.
6. Run manual or data-driven validation against Jira acceptance criteria.
7. Record results in `outputs/test-reports/<KEY>.md` using `assets/test-report-template.md` (paths per parent pipeline). Fill **Production deployment state** (Sandbox vs Production; whether **Gearset** or other promote is required).
8. If the issue is not fixed, record failure evidence and return control to the pipeline for another iteration.

## References

- `references/deploy-test-guide.md`: Deployment and testing guidance.

## Assets

- `assets/test-report-template.md`: Sandbox test report format.

## Quality Checks

- Deploy and mutating operations targeted **only** the org value in **`CASEOPS_SANDBOX_TARGET_ORG`**.
- Target was verified against `.env.jira` before deploy, not assumed from memory or defaults.
- Engineering escalation issues were not deployed by this skill.
- Deployment command and result are recorded.
- Tests map to Jira acceptance criteria.
- Failure evidence is preserved.
- **Production deployment state** is explicit in the test report (not implied).
