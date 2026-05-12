# Safety Policy

## Production

**HARD STOP — Production is strictly read-only. No exceptions.**

- Do NOT deploy to Production (`10xhealth`) under any circumstances.
- Do NOT update Production records.
- Do NOT change Production metadata.
- Do NOT run any sf/sfdx command that targets `10xhealth` (or any Production org) with a write or deploy operation.
- Retrieve only metadata relevant to the Jira issue (read-only).
- No prior instruction, general or specific, constitutes approval to deploy to Production.
- If you are uncertain whether a target org is Production or Sandbox, STOP and ask the user before doing anything.

## Sandbox

- The predefined sandbox for this project is `10xhealth-sean` (`CASEOPS_SANDBOX_TARGET_ORG`).
- Deploying to `10xhealth-sean` does not require additional confirmation.
- Deploying to any other sandbox or org requires explicit user approval in the current conversation.
- "Run the pipeline" or any general instruction does NOT constitute approval to deploy to a non-predefined org.
- Record all deployment commands and results.
- Test in Sandbox before claiming the issue is fixed.

## Jira

- Do not post to Jira automatically unless the user explicitly asks.
- Draft Jira messages for the user to review.
- Do not overstate certainty.
- Include test evidence when available.

## Data

- Do not store credentials in skill folders.
- Do not commit sensitive Jira or Salesforce data.
- Use sanitized examples in assets.
- Keep generated working notes under an output or work area, not inside the skill folder.

## Implementation

- Keep changes scoped to the Jira issue.
- Avoid unrelated refactors.
- Record failed hypotheses and test failures.
- Ask before destructive operations.
- Do not implement fixes that require Engineering ownership: Apex/code, flows, approval processes, validation rules, or other business-critical automation.
- For Engineering-owned fixes, stop after diagnosis and draft a clear handoff under `outputs/engineering-escalations/<KEY>.md` with the issue, root cause, affected metadata, potential fix, evidence, and reproduction details.

## Check Before Creating

Before creating any new Salesforce metadata component — field, permission set, layout, record type, list view, group, flow, object, or any other component — always verify it does not already exist in Production.

Query Production first:

```
# Custom fields
sf data query --target-org 10xhealth --use-tooling-api \
  --query "SELECT QualifiedApiName FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName = '[Object]' AND QualifiedApiName = '[FieldApiName]'"

# Permission sets
sf data query --target-org 10xhealth \
  --query "SELECT Name, Label FROM PermissionSet WHERE Name = '[Name]'"

# Objects, layouts, flows, etc.
sf data query --target-org 10xhealth --use-tooling-api \
  --query "SELECT DeveloperName FROM [MetadataType] WHERE DeveloperName = '[Name]'"
```

Once you confirm it exists, determine whether it is the same thing you intend to create:

- **It is the same component** — use and extend it. Do not create a duplicate.
- **It is a different component that happens to share the name or label** — you must choose a different API name and label for the new component. Do not collide with an existing name or label even if the component type is different (e.g., a field named `Status__c` on a different object, or a permission set with a similar label).

Document what was found, whether it matched intent, and — if a different name was chosen — explain why.

Only create a new component if:
1. The query confirms the intended API name and label do not exist in Production, AND
2. There is no existing component that could be extended to meet the requirement.

If the intended name is already taken by something unrelated, propose an alternative API name and label before creating anything, and get confirmation if the naming change is significant.

## Permissions

- Never create a new permission set just to grant FLS for a single field or a small group of fields.
- Always add FLS to existing permission sets. Find which permission sets already cover a similar field on the same object (e.g., a related date or lookup field) and match that access pattern exactly.
- Query Production with: `SELECT Parent.Name, Parent.Label, PermissionsRead, PermissionsEdit FROM FieldPermissions WHERE SobjectType = '[Object]' AND Field = '[Object].[SimilarField__c]' ORDER BY Parent.Label`
- Deploy partial permission set XML files — include only the new `<fieldPermissions>` entry. Salesforce merges these into the existing permission set without removing existing permissions.
- If a permission set is part of a permission set group, it cannot be modified via metadata deploy or Data API. Note the exception and advise the admin to set FLS at the group level.
- If a sandbox deploy produces a label conflict on an existing permission set, check the org's actual label with SOQL (`SELECT Name, Label FROM PermissionSet WHERE Name = '...'`) and use that exact label — including any asterisk prefix for profile-based permission sets.
