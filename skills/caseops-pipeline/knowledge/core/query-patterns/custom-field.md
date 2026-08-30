# Custom Field Query Pattern

Use these patterns before experimenting.

## Find a custom field

FieldDefinition commonly uses DeveloperName without the `__c` suffix:

```bash
python scripts/sf_caseops_helper.py query-data --org "$ORG" --soql "SELECT Id, DeveloperName, Label, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = 'Case' AND DeveloperName = 'Field_Name'" --name field-definition --out-dir "$RAW_DIR"
```

Tooling `CustomField` is often better for metadata details:

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata FROM CustomField WHERE TableEnumOrId = 'Case' AND DeveloperName = 'Field_Name'" --name custom-field --out-dir "$RAW_DIR"
```

Notes:

- `CustomField.DeveloperName` usually omits `__c`; `FullName` includes `Object.Field__c`.
- Use the returned `00N...` Id for Salesforce artifact links.
- Save large JSON to the issue-scoped metadata directory and summarize it; do not paste full metadata into the operator log.
