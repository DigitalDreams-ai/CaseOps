---
name: salesforce-sandbox-deploy-test
description: Mandatory for jira-salesforce-fix-pipeline after a proposed solution is prepared. Deploys only to the single allowlisted Sandbox from CASEOPS_SANDBOX_TARGET_ORG, tests against Jira acceptance criteria, records results, preserves baseline/candidate/revert metadata, and reverts failed attempts. Refuse any deploy or data write to any other org.
---

# Salesforce Sandbox Deploy Test

## Hard requirements (non-negotiable)

1. **Mandatory** when `jira-salesforce-fix-pipeline` has prepared a proposed solution in Step 8. This applies to Support-owned fixes and Engineering proposal validation.
2. **Single writable org:** Read **`CASEOPS_SANDBOX_TARGET_ORG`** from the active env file, preferably `CASEOPS_ENV_FILE`. That value is the **only** Salesforce org (alias or username) that may receive **deploys, metadata writes, or mutating data/API operations** for this skill. Treat it as the org allowlist.
3. If **`CASEOPS_SANDBOX_TARGET_ORG`** is missing or empty, **STOP** — do not deploy; tell the operator to set it.
4. Before any deploy or write, confirm the CLI/API target (e.g. `sf` `--target-org`, org picker, or session) **exactly matches** that allowlisted value. If it does not match, **STOP** — do not “pick the closest sandbox” or override in chat.
5. **Production and all other orgs:** No deploy and no mutating operations unless the org is exactly the allowlisted sandbox value. Production remains **read-only** for investigation only (separate skills/prompts).

## Use This Skill When

- `jira-salesforce-fix-pipeline` Step 8 invokes you after implementation, **or**
- Another workflow explicitly assigns Sandbox validation with the same allowlist rules.

## Do Not Use This Skill When

- The implementation is not ready (no changes to deploy).
- **`CASEOPS_SANDBOX_TARGET_ORG`** is not set.
- The only available org target does not match **`CASEOPS_SANDBOX_TARGET_ORG`**.

## Workflow

**Verify allowlist before any mutating command.**

1. Read **`CASEOPS_SANDBOX_TARGET_ORG`** from the active env. Record it in the test report.
2. Create an attempt directory under `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/`.
3. Retrieve Sandbox baseline metadata for every component that may change.
4. Review changed metadata and expected deployment scope.
5. Deploy **only** to the allowlisted Sandbox (target must match step 1). Prefer `python scripts/sf_caseops_helper.py deploy-mdapi ...` for issue-scoped candidate metadata.
6. Run automated tests when available.
7. Run manual or data-driven validation against Jira acceptance criteria.
8. Record results in `outputs/test-reports/<KEY>.md` using `assets/test-report-template.md` (paths per parent pipeline). Fill the required **Validation Verdict** block exactly:
   - `Validation Status: passed | failed | blocked | not-run`
   - `Fixed?: yes | no | unknown`
   - `Production deploy required: yes | no | n/a | unknown`
   - `Evidence:` one concise sentence or artifact path supporting the verdict.
   Fill **Production deployment state** (Sandbox vs Production; whether **Gearset** or other promote is required).
9. If the issue is not fixed, revert the attempt from the captured baseline, verify the revert, record failure evidence, and return control to the pipeline for another iteration.

## References

- `references/deploy-test-guide.md`: Deployment and testing guidance.

## Assets

- `assets/test-report-template.md`: Sandbox test report format.

## Quality Checks

- Deploy and mutating operations targeted **only** the org value in **`CASEOPS_SANDBOX_TARGET_ORG`**.
- Target was verified against `CASEOPS_SANDBOX_TARGET_ORG` from the active env file before deploy, not assumed from memory or defaults.
- Engineering proposal packages are clearly marked as Sandbox-only proposals, not Production changes.
- Deployment command and result are recorded.
- Deployment uses modern `sf project deploy start --source-dir` or `--metadata-dir`. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest`.
- Deploys use deterministic MDAPI helper flow before repeated source-tracking variants.
- Tests map to Jira acceptance criteria.
- Failure evidence is preserved.
- Failed or abandoned attempts were reverted and verified.
- **Validation Verdict** is explicit and uses the exact canonical field names and values.
- **Production deployment state** is explicit in the test report (not implied).
