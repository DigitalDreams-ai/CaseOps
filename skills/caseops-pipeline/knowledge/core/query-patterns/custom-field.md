# Custom Field Query Pattern

Use these patterns before experimenting.

## Find a custom field

FieldDefinition commonly uses DeveloperName without the `__c` suffix:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, DeveloperName, Label, DataType FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = 'Case' AND DeveloperName = 'Field_Name'"
```

Tooling `CustomField` is often better for metadata details:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata FROM CustomField WHERE TableEnumOrId = 'Case' AND DeveloperName = 'Field_Name'"
```

Notes:

- `CustomField.DeveloperName` usually omits `__c`; `FullName` includes `Object.Field__c`.
- Use the returned `00N...` Id for Salesforce artifact links.
- Save large JSON to the issue-scoped metadata directory and summarize it; do not paste full metadata into the operator log.
