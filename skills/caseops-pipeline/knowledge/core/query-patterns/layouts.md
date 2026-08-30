# Layout Query Pattern

For layout section and field placement checks, Tooling `Layout.Metadata` is often faster and cleaner than repeated `sf project retrieve` attempts.

Find Case layouts:

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, Name, TableEnumOrId FROM Layout WHERE TableEnumOrId = 'Case'" --name case-layouts --out-dir "$RAW_DIR"
```

Fetch layout metadata:

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, Name, Metadata FROM Layout WHERE Id = '00h...'" --name case-layout-metadata --out-dir "$RAW_DIR"
```

Then parse `Metadata.layoutSections[].layoutColumns[].layoutItems[].field`.

Rules:

- Distinguish a section label from a nearby field label. A field beside `Call_Details__c` is not automatically in a section named `Call Details`.
- If an acceptance criterion names a section that does not exist, document both the actual placement and the ambiguity.
