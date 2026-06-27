# Salesforce Gotchas: Fields And Picklists

Use these checks before concluding a field or picklist is missing or wrong.

- Custom field API names use `Object.Field__c`, but Tooling `CustomField.DeveloperName` usually omits `__c`.
- Picklist labels and API values can differ. Compare both label and value, and normalize trailing spaces and non-breaking spaces before reporting mismatch.
- A value can exist in metadata but be inactive, unavailable for a record type, hidden by field-level security, or absent from a dependent picklist controlling matrix.
- Record type picklist availability can make a field look wrong even when the field's global value set or valueSet is correct.
- Dependent picklists require checking controlling field values, not just the dependent field's value list.
- Custom field visibility can be blocked by FLS even when the field exists and is on the page layout.
- Formula fields, rollups, and calculated fields may show stale-looking values if dependent records or async recalculation have not completed.
- Standard fields often cannot be changed the same way custom fields can. Verify metadata type and mutability before proposing a deploy.
- Before creating a new field, query Production for existing API name, label, and semantically similar fields. Extend existing metadata when possible.
- For CaseOps, retrieve/deploy with modern `sf` CLI only. Prefer `--metadata`, `--source-dir`, or helper summaries; do not use `package.xml` or legacy `sfdx force:*`.
