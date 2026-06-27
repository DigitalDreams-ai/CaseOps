# Sandbox Deploy And Test Guide

## Hard allowlist (read first)

- Read **`CASEOPS_SANDBOX_TARGET_ORG`** from the active env file identified by `CASEOPS_ENV_FILE`. Docker deployments normally mount this as `/data/.env`. That string is the **only** org allowed for deploys, metadata writes, and mutating Data/API operations in this skill.
- Compare your Salesforce CLI default org, `--target-org`, and any UI session to that value **before** any write. Mismatch → **STOP**; do not deploy to a different sandbox “temporarily.”
- If the variable is unset, **STOP** and ask the operator to add it in Settings or the active env file.
- Changing the allowlisted org is done in Settings or the active env file, not by improvising another target in chat.

## Before deploying

- Confirm the allowlisted Sandbox alias or username matches `CASEOPS_SANDBOX_TARGET_ORG`.
- Confirm the change is Support-resolvable. If it requires Apex/code, flow, approval process, or validation rule changes, stop and produce an Engineering handoff unless the user explicitly overrides the escalation rule.
- Create a new attempt directory: `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/`.
- Retrieve the current Sandbox baseline for every component you will change into `attempt-N/baseline-sandbox/`.
- Put candidate metadata in `attempt-N/candidate/`.
- Prepare rollback metadata in `attempt-N/revert/`. For updated components this is the captured baseline. For newly created components, prepare the correct destructive delete package if the metadata type supports deletion.
- Update `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/metadata-workspace.json` with attempt number, touched components, and paths.
- Review the local diff between `baseline-sandbox/` and `candidate/`.
- Confirm the deployment scope.
- Identify tests to run.
- Use `python scripts/sf_caseops_helper.py ...` helpers before equivalent raw `sf` commands. Helper failures return `failure_class`, `retryable`, and `next_action`; if `retryable=false`, stop and replan instead of trying small variants.
- Initialize missing attempt directories and metadata-workspace state with:

```bash
python scripts/sf_caseops_helper.py workspace-init --issue-key "<KEY>" --attempt attempt-N
```

- For source-format candidate metadata, use:

```bash
python scripts/sf_caseops_helper.py deploy-source --sandbox-org "$CASEOPS_SANDBOX_TARGET_ORG" --source-dir "${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/candidate/force-app" --attempt "${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N"
```

- For deterministic metadata-dir deploys or when source tracking causes `NothingToDeploy`, use:

```bash
python scripts/sf_caseops_helper.py deploy-mdapi --sandbox-org "$CASEOPS_SANDBOX_TARGET_ORG" --candidate "${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/candidate" --attempt "${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N"
```

- For deploy follow-up, use:

```bash
python scripts/sf_caseops_helper.py deploy-report --org "$CASEOPS_SANDBOX_TARGET_ORG" --deploy-id "<DEPLOY_ID>" --out-dir "${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N"
```

- If the helper or deploy pattern fails with `retryable=false`, stop and summarize the blocker. Do not inspect `.sf` internals or try many small deploy variants.
- If no helper covers the case, deploy with modern `sf project deploy start --source-dir` or `--metadata-dir`. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest`.

After deploying:

- Capture deployment command and result.
- Run Apex tests or relevant validation commands when available.
- Validate the Jira reproduction steps.
- Record actual results, not just pass/fail.

If validation fails:

- Record the failed case.
- Identify whether the implementation, hypothesis, test data, or metadata scope was wrong.
- Revert every Sandbox change from this attempt before returning to the main pipeline.
- Verify the revert by retrieving the changed components again and comparing them with `baseline-sandbox/`.
- Record the revert command, result, and verification in `outputs/test-reports/<KEY>.md`.
- Mark the attempt reverted in `metadata-workspace.json`.
- Return to the main pipeline for another iteration.

If validation passes:

- Copy the final deployable package to `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/support-owned/` for Support-owned fixes, or `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/engineering-proposal/` for Engineering handoff proposals.
- Record the confirmed package path in `outputs/test-reports/<KEY>.md`.
- Mark the confirmed package path in `metadata-workspace.json`.
