# CaseOps Salesforce Helper Scripts

Use deterministic helpers before improvising Salesforce CLI/SOQL/curl commands.

Helper entrypoint:

```bash
python scripts/sf_caseops_helper.py --help
```

Available helpers:

```bash
python scripts/sf_caseops_helper.py custom-field --org "$ORG" --object Case --field Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py layout --org "$ORG" --object Case --contains "Customer Experience" --field Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py fls --org "$ORG" --field Case.Supplement_Inquiry__c --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py verify-sobject --org "$ORG" --sobject OpportunityShare --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject OpportunityShare --contains "AccessLevel" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py query-data --org "$ORG" --soql "SELECT Id FROM Account LIMIT 1" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id FROM FlowDefinition LIMIT 1" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py api-request --org "$ORG" --endpoint "/services/data/v66.0/limits" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py deploy-mdapi --sandbox-org "$SANDBOX_ORG" --candidate "$CANDIDATE" --attempt "$ATTEMPT"
```

Rules:

- Run helpers first for custom field, picklist, layout, FLS, and custom-field MDAPI deploy work.
- Run `verify-sobject` before first-query attempts against unfamiliar or optional objects. If it fails, record the absence and replan instead of retrying broad SOQL variants.
- `query-data` and `query-tooling` precheck the primary object before running the requested SOQL unless `--skip-existence-check` is explicit. Treat missing objects as investigation evidence, not as a reason to repeat broad query variants.
- `deploy-mdapi` packages the MDAPI directory into an issue-scoped zip before deploy. Do not bypass this with raw directory deploys when Salesforce reports package or source-tracking ambiguity.
- Helpers write compact JSON summaries into the issue-scoped directory and avoid raw access-token output.
- If a helper fails, inspect the helper summary/error and replan. Do not try many ad hoc variants of the same query.
- Raw `sf data query`, `sf project retrieve start`, `sf project deploy start`, and read-only `sf api request rest` are blocked. Use the corresponding helper so failures are structured and workspace/safety rules are applied.
- Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps work.
- Before querying setup/share objects with unfamiliar fields, run `sobject-fields` and use only fields returned by describe.
