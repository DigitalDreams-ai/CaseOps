# Apex Query Pattern

Resolve Apex classes/triggers with Tooling API before reading or testing broadly.

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, Name, Status FROM ApexClass WHERE Name = 'ClassName'" --name apex-class --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, Name, TableEnumOrId, Status FROM ApexTrigger WHERE Name = 'TriggerName'" --name apex-trigger --out-dir "$RAW_DIR"
```

Run targeted tests first. Broad test runs need a clear reason.
