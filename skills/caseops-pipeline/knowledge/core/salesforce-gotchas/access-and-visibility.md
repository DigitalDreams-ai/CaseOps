# Salesforce Gotchas: Access And Visibility

Use these checks before concluding an access issue is fixed or escalated.

- Object CRUD, field-level security, record sharing, app visibility, tab visibility, page layout, and Lightning component visibility are separate gates.
- Permission sets and permission set groups can combine access. Missing access may be caused by absent assignment, muted permission, or group-level behavior.
- FieldPermissions rows can include profile-owned permission sets. CaseOps should not modify Profile metadata; use permission sets or document admin steps.
- Permission Set Groups can mute permissions. Granting access in an underlying permission set may not be enough if the group mutes it.
- A user can have object access but still fail record access because sharing, ownership, role hierarchy, criteria sharing, teams, territories, or restriction rules block the record.
- Share objects do not all expose the same fields. Do not assume `Name`, `Description`, or `SharingType` exist on `UserShare`, `AccountShare`, `OpportunityShare`, or `Object__Share`; use `sf sobject describe` or query only documented fields such as `Id`, `UserOrGroupId`, `<Object>AccessLevel`, `RowCause`, and parent relationship fields valid for that share object.
- A field can be editable in metadata but effectively read-only because the page uses a formula, validation rule, automation overwrite, approval lock, or record type process.
- Login as / UI inspection can prove visibility symptoms, but `sf data query`, `sf org`, and metadata retrieve are the source for API-level investigation.
- Always map the affected user/persona to exact PermissionSetAssignment, PermissionSetGroup, Profile, UserRole, and record ownership facts before proposing access changes.
- For share-object investigation, run the `query-patterns/share-objects.md` describe pattern first. Never query `UserShare.Name`; `UserShare` is not a user record and does not expose that field.
