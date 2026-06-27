# Permission Set and FLS Query Pattern

Resolve candidate permission sets first:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, Name, Label FROM PermissionSet WHERE Name LIKE '%Customer%' OR Label LIKE '%Customer%'"
```

Check FLS with parent details:

```bash
sf data query --target-org "$ORG" --json --query "SELECT Id, Field, PermissionsRead, PermissionsEdit, ParentId, Parent.Name, Parent.Type FROM FieldPermissions WHERE Field = 'Case.Field_Name__c'"
```

Guidance:

- Report Read+Edit vs Read-only separately.
- Ignore session/profile-like permission records only when they are not part of the requested audience, and say why.
- If the customer asked for a team, map labels to that team explicitly instead of assuming every matching permission set is in scope.
