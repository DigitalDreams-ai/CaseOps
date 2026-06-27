# Salesforce Gotchas: Deploy And Sandbox

Use these checks before trying repeated deploy variants.

- CaseOps deploys only to the allowlisted Sandbox from `CASEOPS_SANDBOX_TARGET_ORG`; Production is read-only.
- Use modern `sf project deploy start --source-dir` or `--metadata-dir`. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps work.
- Sandbox source tracking can produce `NothingToDeploy` even when candidate metadata exists. Prefer deterministic metadata-dir deploy via the CaseOps helper before inspecting `.sf` internals.
- Always retrieve a Sandbox baseline for every component before deploying a candidate. The baseline is the rollback anchor.
- Failed or abandoned attempts must be reverted before a new attempt starts. Verify revert by retrieve/diff, not by assumption.
- Some metadata deploys merge partial XML, while others replace larger structures. Confirm metadata type behavior before deploying partial files.
- Permission set field permissions can be deployed as narrow partial entries. Profile metadata must not be modified by the Support-owned pipeline.
- Record type, picklist, layout, and FLS changes often need to be tested together because each can block the same user-visible outcome.
- A successful deploy is not proof of a fixed issue. Validate the Jira acceptance criteria and record actual evidence.
