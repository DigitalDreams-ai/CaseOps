# Layout Query Pattern

For layout section and field placement checks, Tooling `Layout.Metadata` is often faster and cleaner than repeated `sf project retrieve` attempts.

Find Case layouts:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, TableEnumOrId FROM Layout WHERE TableEnumOrId = 'Case'"
```

Fetch layout metadata:

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, Metadata FROM Layout WHERE Id = '00h...'" > "$RAW_DIR/Case-Customer_Experience_layout.json"
```

Then parse `Metadata.layoutSections[].layoutColumns[].layoutItems[].field`.

Rules:

- Distinguish a section label from a nearby field label. A field beside `Call_Details__c` is not automatically in a section named `Call Details`.
- If an acceptance criterion names a section that does not exist, document both the actual placement and the ambiguity.
