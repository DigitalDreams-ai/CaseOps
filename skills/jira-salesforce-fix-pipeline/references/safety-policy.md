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

**HARD REQUIREMENT — single writable org**

- The **only** Salesforce org that may receive **deploys, metadata writes, or mutating data/API operations** from the fix pipeline’s deploy/test step is the value of **`CASEOPS_SANDBOX_TARGET_ORG`** in **`.env.jira`** (username or CLI alias, as your team configures it).
- Read that value from the file **before** every deploy or write. The CLI target **must match it exactly**. If it does not match, **STOP** — do not deploy elsewhere, including another sandbox.
- If **`CASEOPS_SANDBOX_TARGET_ORG`** is unset or empty, **STOP** — do not deploy until the operator sets it.
- Changing the allowlisted org is done by editing **`.env.jira`**, not by choosing a different org in chat.
- `jira-salesforce-fix-pipeline` **always** invokes **`salesforce-sandbox-deploy-test`** after a Support-resolvable implementation (deploy + test are mandatory on that path).
- "Run the pipeline" or any general instruction does **not** authorize writes to Production or to any org other than **`CASEOPS_SANDBOX_TARGET_ORG`**.
- Record all deployment commands and results.
- Test in the allowlisted Sandbox before claiming the issue is fixed.

Examples in docs may show org aliases like `10xhealth-sean` — your environment’s allowlist is **only** what appears in **`CASEOPS_SANDBOX_TARGET_ORG`**.

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

## Wording: Production vs Sandbox

- **Never** describe a fix as if new or changed metadata already exists in **Production** when it was only deployed or validated in **Sandbox**, unless a **read-only Production check** confirms it.
- Every **confirmed** Support outcome must say whether the operator must **promote metadata to Production** (e.g. **Gearset**) or whether **no Production deploy** is needed because the relevant metadata **already exists in Production** (or the fix was data/config/access only).
- This pipeline **does not** deploy to or mutate **Production** unless the operator **explicitly** requests it. Phrases like “add a permission set” must clarify **Sandbox create** vs **already in Production** vs **deploy pending**.

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

- **Never modify Profile permissions** — do not deploy or edit Salesforce **Profile** metadata (including field-level security, tab visibility, app assignment, or any profile-level access changes). Use **permission sets** (or document admin steps). If the only valid fix is a profile change, stop and escalate; do not change profiles in Support-owned pipeline work.
- Never create a new permission set just to grant FLS for a single field or a small group of fields.
- Always add FLS to existing permission sets. Find which permission sets already cover a similar field on the same object (e.g., a related date or lookup field) and match that access pattern exactly.
- Query Production with: `SELECT Parent.Name, Parent.Label, PermissionsRead, PermissionsEdit FROM FieldPermissions WHERE SobjectType = '[Object]' AND Field = '[Object].[SimilarField__c]' ORDER BY Parent.Label`
- Deploy partial permission set XML files — include only the new `<fieldPermissions>` entry. Salesforce merges these into the existing permission set without removing existing permissions.
- If a permission set is part of a permission set group, it cannot be modified via metadata deploy or Data API. Note the exception and advise the admin to set FLS at the group level.
- If a sandbox deploy produces a label conflict on an existing permission set, check the org's actual label with SOQL (`SELECT Name, Label FROM PermissionSet WHERE Name = '...'`) and use that exact label — including any asterisk prefix for profile-based permission sets.
