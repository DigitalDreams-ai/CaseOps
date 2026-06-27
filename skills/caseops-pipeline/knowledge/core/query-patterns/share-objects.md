# Share Object Query Pattern

Use this pattern before querying `UserShare`, `AccountShare`, `OpportunityShare`, or custom `Object__Share` rows.

## Describe first

Share-object fields vary by object. Do not assume fields such as `Name`, `Description`, or `SharingType`.

```bash
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject OpportunityShare --contains "AccessLevel" --out-dir "$RAW_DIR"
python scripts/sf_caseops_helper.py sobject-fields --org "$ORG" --sobject UserShare --out-dir "$RAW_DIR"
```

Use only fields returned in the helper output or by `sf sobject describe`.

## Safe common patterns

Opportunity share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserOrGroupId, UserOrGroup.Name, OpportunityId, OpportunityAccessLevel, RowCause FROM OpportunityShare WHERE UserOrGroup.Name = 'Tier 1 Tech Support' LIMIT 20"
```

Account share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserOrGroupId, UserOrGroup.Name, AccountId, AccountAccessLevel, RowCause FROM AccountShare WHERE UserOrGroup.Name = 'Tier 1 Tech Support' LIMIT 20"
```

User share rows:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, UserId, UserOrGroupId, RowCause, UserAccessLevel FROM UserShare WHERE UserId = '005...' LIMIT 20"
```

Rules:

- `UserShare` does not have a `Name` field. Query `User` separately for the user's name, or use a relationship field only if describe confirms it.
- For standard object share rows, the object-specific access field is usually `<Object>AccessLevel`, such as `OpportunityAccessLevel` or `AccountAccessLevel`.
- `UserOrGroup.Name` is useful for groups/users when the relationship is present, but it is not the same as a top-level `Name` field on the share row.
- If a share query fails once with `No such column`, stop and describe the sObject before trying another variant.
