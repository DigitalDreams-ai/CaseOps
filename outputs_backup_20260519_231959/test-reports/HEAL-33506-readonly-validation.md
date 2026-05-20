# HEAL-33506 Read-Only Validation

## Scope

Read-only Production validation for round-robin access request.

## Checks

- Synced Jira issue `HEAL-33506`.
- Queried requester user `005Rh000002PMAfIAO`.
- Queried requester permission set assignments.
- Queried Janati round-robin objects.
- Queried object permissions for existing permission sets.
- Queried active round-robin assignment records.

## Results

- Ivelisse Santos is active.
- Ivelisse does not have `Manage_Round_Robin_package`.
- Existing permission set `Manage_Round_Robin_package` grants the relevant package object access.
- No metadata deployment was needed.

## Outcome

Pass for investigation. Recommended action is assigning the existing permission set and validating with the requester.
