# Metadata Investigation Guide

Investigate only metadata that could plausibly affect the Jira issue.

## Workspace rules

- Store Production retrievals under `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/`.
- Treat this directory as read-only evidence. Never edit retrieved Production files in place.
- Use focused retrieve commands with `--output-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"`.
- Retrieve with `python scripts/sf_caseops_helper.py retrieve-metadata ...` first. If the helper does not cover the case, use modern `sf project retrieve start --metadata` or `--source-dir`. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest`.
- Do not use root-level `temp*`, `retrieve*`, `deploy*`, or `metadata*` directories.
- If a later step needs to test a modified version, copy only the required files into that step's Sandbox attempt directory.
- Use `python scripts/sf_caseops_helper.py ...` helpers first for custom fields, picklists, layouts, FLS, SOQL checks, field/Flow verification, and targeted metadata retrieval. They write compact JSON summaries, classify failures, and avoid noisy or secret-bearing CLI output.

Known helper commands:

```bash
python scripts/sf_caseops_helper.py custom-field --org "$ORG" --object Case --field Field_Name__c --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py layout --org "$ORG" --object Case --contains "Layout Name Fragment" --field Field_Name__c --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py fls --org "$ORG" --field Case.Field_Name__c --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py verify-field --org "$ORG" --sobject Case --field Field_Name__c --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py verify-flow --org "$ORG" --flow Flow_API_Name --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py query-data --org "$ORG" --soql "SELECT Id FROM Case LIMIT 1" --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, DeveloperName FROM FlowDefinition LIMIT 1" --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
python scripts/sf_caseops_helper.py retrieve-metadata --org "$ORG" --metadata "Flow:Flow_API_Name" --out-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
```

If a helper fails, inspect `failure_class`, `retryable`, and `next_action`. If `retryable=false`, replan. Do not run many variants of the same SOQL or retrieve command.

Common metadata targets:

- Objects and fields.
- Record types.
- Validation rules.
- Flows and process automation.
- Apex classes and triggers.
- Permission sets and profiles.
- Assignment rules.
- Queues.
- Page layouts and Lightning pages.
- Custom metadata and custom settings.

For each retrieved item, record:

- Metadata name.
- Why it was retrieved.
- Relevant behavior found.
- Whether it confirms or rejects a hypothesis.

Do not retrieve the entire Production org unless the user explicitly asks and the scope justifies it.
