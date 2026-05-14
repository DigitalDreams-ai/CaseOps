# Internal Notes

## Jira Issue

- Key:
- Summary:
- Reporter:

## Root Cause

## Solution Or Escalation

## Production vs deployment (required)

**Rule:** Never state or imply that Production was changed by this pipeline unless the operator explicitly deployed. Sandbox validation does **not** mean Production has the new metadata.

- **Verified in Production (read-only):** (What we confirmed exists or does not exist in Production.)
- **Changed or created only in Sandbox:** (Metadata/components deployed/tested in Sandbox only.)
- **Production metadata deploy required?** **Yes** — promote via Gearset (or org standard) / **No** — solution uses what is already in Production / **N/A** — no metadata change.
- **Operator action:** (Concrete next step, e.g. “Package Permission Set `Foo` in Gearset from Sandbox → Production” vs “Assign existing permission set in Production — no deploy”.)

## Engineering Handoff

- Required?:
- Reason:
- Affected metadata/component:
- Potential fix:
- Evidence:
- Reproduction details:

## Metadata Or Code Changed

## Sandbox Deployment

- Sandbox:
- Deployment result:

## Testing Performed

## Result

## Risks Or Follow-Up

## Remaining Actions
