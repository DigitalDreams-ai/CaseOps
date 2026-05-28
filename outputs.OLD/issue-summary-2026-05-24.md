# CaseOps Issue Summary - 2026-05-24

Generated: 2026-05-24
Last updated: 2026-05-24

## Executive Summary

- Total issues in scope: 1
- Escalated to Engineering (Jira status): 0
- Active issues processed: 1 (HEAL-33744)
- Engineering handoffs raised during processing: 0
- Sandbox-deployed and validated: 1 (HEAL-33744)
- Operational / data / access follow-up (no metadata deploy): 1 (HEAL-33744 — permission set assignment in Production)

**Issue Status:** HEAL-33744 (Pt agreement not getting sent) — **Support-Resolvable** — **Sandbox validated** — **Ready for Production operator assignment**

## Closed / Resolved (Skipped)

No issues were in Closed or Resolved status at sync.

| Issue | Jira Status | Summary |
| --- | --- | --- |

## Issue Rollup

Active issues that entered the pipeline.

| Issue | Jira Status At Sync | Summary | Disposition | Prod deploy? | Next Step |
| --- | --- | --- | --- | --- | --- |
| HEAL-33744 | In Progress | Pt agreement not getting sent | Support-fixed in Sandbox; awaiting operator assignment in Production | No (data operation) | Operator assigns Manage_Patient_Agreement_Configurations permission set to user 005Rh000001Jfq5IAC in Production |

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox.

| Issue | Sandbox | Deploy / Validation | Prod deploy needed? |
| --- | --- | --- | --- |
| HEAL-33744 | 10xhealth-sean (Full Copy) | **Permission Set Assignment:** Assigned Manage_Patient_Agreement_Configurations (ID: 0PSRh0000000YGDOA2) to user Jon Jasper Garing (005Rh000001Jfq5IAC). Created PermissionSetAssignment record (ID: 0PaEa00000bNl49KAC). All acceptance criteria verified. | YES — Manual assignment in Production (no Gearset). Operator must replicate assignment using same method. |

## Escalated to Engineering

No issues were escalated to Engineering.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |

## Root Cause & Fix Summary

### HEAL-33744: Pt agreement not getting sent

**Root Cause:** User Jon Jasper Garing (jgaring@10xhealthsystem.com, ID: 005Rh000001Jfq5IAC) lacks CRUD:Create permission on Patient_Agreement__c object. The Patient Agreement creation flow (Screenflow_Send_Patient_Agreement_Forms) runs in SystemModeWithoutSharing but delegates record creation to subflow Autolaunch_Send_Patient_Agreements_to_Patient. The subflow executes DML CREATE on Patient_Agreement__c without system-mode overrides. Without the permission set assignment, CREATE silently fails at the field-level security layer, and user sees no agreement on Account related list.

**Fix:** Assign Manage_Patient_Agreement_Configurations permission set to user Jon Jasper Garing. This grants CRUD:Create, Read, Edit, Delete and FLS on all Patient_Agreement__c fields.

**Scope:** Single user, single permission set assignment (data operation, not metadata).

**Evidence:**
- Production metadata investigation (Step 5): Confirmed Patient_Agreement__c object, Manage_Patient_Agreement_Configurations permission set, and Screenflow_Send_Patient_Agreement_Forms flow all exist and are active in Production
- Problem location identification (Step 6): Jon Jasper Garing has 18 permission set assignments but NONE for Patient Agreement access
- Sandbox validation (Step 9): Successfully assigned permission set to same user in Sandbox; user now has full CRUD + FLS access to Patient_Agreement__c

**Production vs Sandbox:**
- Production: User lacks permission set assignment (verified read-only in Step 5)
- Sandbox: Permission set assigned successfully; all acceptance criteria met
- Production deploy required: YES — Operator must manually assign permission set in Production (data operation, not code/metadata)

## Artifact Index

- Jira summary: `outputs/jira/summary/HEAL-33744.md`
- Investigation record: `outputs/investigations/HEAL-33744.md`
- Internal notes: `outputs/internal-notes/HEAL-33744.md`
- Jira message draft: `outputs/jira-messages/HEAL-33744.md`
- Test report: `outputs/test-reports/HEAL-33744.md`

## Operator Instructions

### Step 1: Assign Permission Set in Production

**User:** Jon Jasper Garing (jgaring@10xhealthsystem.com, ID: 005Rh000001Jfq5IAC)  
**Permission Set:** Manage_Patient_Agreement_Configurations (ID: 0PSRh0000000YGDOA2)

**Method A — Setup UI (recommended):**
1. Log in to Production as admin
2. Navigate to Setup > Permission Sets > Manage_Patient_Agreement_Configurations
3. Click Manage Assignments
4. Click Add Assignment
5. Select Jon Jasper Garing
6. Click Assign
7. Confirm assignment in user's permission set list

**Method B — Data API:**
```
POST /services/data/v67.0/sobjects/PermissionSetAssignment
{
  "PermissionSetId": "0PSRh0000000YGDOA2",
  "AssigneeId": "005Rh000001Jfq5IAC"
}
```

### Step 2: Verify Fix in Production

1. Notify Jon Jasper Garing permission assigned
2. User navigates to Patient Account record
3. User triggers patient agreement send action
4. Verify Patient Agreement record created and visible on Account related list
5. Confirm agreement contains expected data

### Step 3: Post Jira Response

Post customer-facing message: `outputs/jira-messages/HEAL-33744.md` to HEAL-33744 and mark Resolved.

## Summary Maintenance

Generated for HEAL-33744 on 2026-05-24. Operator actions complete final step.
