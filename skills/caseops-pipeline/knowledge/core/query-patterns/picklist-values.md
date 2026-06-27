# Picklist Value Query Pattern

Avoid repeated `PicklistValueInfo` experiments. In this org it can fail with unsupported fields, complicated filters, or zero rows depending on endpoint and filter shape.

Preferred path for custom picklist truth:

1. Resolve the field through Tooling `CustomField`.
2. Inspect `CustomField.Metadata.valueSet.valueSetDefinition.value`.
3. If active/default behavior is ambiguous, perform Metadata API retrieve or a UI/API describe check and record which source was authoritative.

Example:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, DeveloperName, TableEnumOrId, FullName, Metadata FROM CustomField WHERE TableEnumOrId = 'Case' AND DeveloperName = 'Field_Name'" > "$RAW_DIR/Case.Field_Name__c.json"
```

Comparison guidance:

- Compare requested labels after trimming whitespace and normalizing non-breaking spaces.
- Detect merged values by comparing requested count vs actual count and by checking adjacent requested labels.
- Do not assume one source is definitive when it conflicts with user-visible behavior; verify with a second source and summarize.
