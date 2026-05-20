# HEAL-33116 Sandbox Validation

## Scope

Sandbox validation for `Opportunity.Scheduled_By__c` field and FLS via existing permission sets.

## Sandbox

- Alias: `10xhealth-sean`
- Deploy ID (field + layouts): from prior pipeline run
- Deploy ID (FLS batch 1 — Admin_Team, Nursing_Staff, Operations_Team, Medical_Coordinator): `0AfEa00000ZnSdLKAV`
- Deploy ID (FLS — Operations_Manager fix): `0AfEa00000Znc6PKAR`

## Components Deployed

### Field
- `CustomField:Opportunity.Scheduled_By__c` — restricted picklist, label "Scheduled by", no static default

### Layouts (prior deploy)
- `Opportunity-Operations Hormone Evaluation Page Layout`
- `Opportunity-Operations Medical Consultation Page Layout`
- `Opportunity-Retention Hormone Eval Opportunity Layout`
- `Opportunity-Retention Medical Consultation Opportunity Layout`
- `Opportunity-Sales - Retention Hormone Evaluation Page Layout`
- `Opportunity-Sales - Retention Medical Consultation Page Layout`

### FLS — Partial updates to existing permission sets (read/edit)
- `PermissionSet:Admin_Team`
- `PermissionSet:Nursing_Staff`
- `PermissionSet:Operations_Team`
- `PermissionSet:Operations_Manager`
- `PermissionSet:Medical_Coordinator`

## Validation

FLS read-back via SOQL confirmed all 5 target permission sets have `PermissionsRead=true` and `PermissionsEdit=true` for `Opportunity.Scheduled_By__c`.

Stale `Opportunity_Scheduled_By_Field_Access` permission set deleted from sandbox (record `0PSEa0000074tY9OAI`).

### Exception
`Scheduling_Coordinator` is a component of a permission set group. It cannot be deployed via metadata API or modified via the Data API. FLS for that PS must be set at the permission set group level by an admin in Production.

## Approach Note

FLS was added to existing permission sets whose access pattern matches `Medical_Consultation_Scheduled_Date__c` (the comparable consultation scheduling field in Production). No new permission sets were created. Each PS file is a partial update — Salesforce merges the new field permission without affecting existing permissions on those sets.

## Outcome

Pass. Field and layouts are deployed. FLS is confirmed on 5 existing permission sets. Package is clean — no dedicated single-field permission set.
