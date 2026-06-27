# Apex Query Pattern

Resolve Apex classes/triggers with Tooling API before reading or testing broadly.

```bash
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, Status FROM ApexClass WHERE Name = 'ClassName'"
sf data query --target-org "$ORG" --use-tooling-api --json --query "SELECT Id, Name, TableEnumOrId, Status FROM ApexTrigger WHERE Name = 'TriggerName'"
```

Run targeted tests first. Broad test runs need a clear reason.
