# Flow Query Pattern

Use Tooling queries to resolve FlowDefinition and active versions before retrieving full XML.

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, DeveloperName, ActiveVersionId, LatestVersionId FROM FlowDefinition WHERE DeveloperName = 'Flow_API_Name'" --name flow-definition --out-dir "$RAW_DIR"
```

Retrieve full metadata only for the flow(s) implicated by the issue. Do not retrieve every flow unless the issue is explicitly broad.

QuickActionDefinition Tooling API fields can vary by API version. Do not assume `Name` exists. If a query with `Name` fails, describe the object or query conservative fields first:

```bash
python scripts/sf_caseops_helper.py query-tooling --org "$ORG" --soql "SELECT Id, DeveloperName, MasterLabel, ActionType FROM QuickActionDefinition WHERE MasterLabel LIKE '%Keyword%' OR DeveloperName LIKE '%Keyword%'" --name quick-actions --out-dir "$RAW_DIR"
```
