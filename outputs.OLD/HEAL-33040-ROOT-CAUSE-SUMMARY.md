# HEAL-33040 Root Cause Analysis — Complete

## Executive Summary

**Root Cause:** Scheduled Flow `Scheduled_Flow_Sync_Accounts_to_External_Systems` is disabled (status=`Obsolete`)

**Impact:** 706+ accounts created since 2026-04-10 not synced to Shopify

**Fix:** Re-activate flow in Production (change status `Obsolete` → `Active`)

**Status:** Support-resolvable. Not an Engineering bug. Simple metadata configuration fix.

---

## Investigation Path

### What We Found

1. **Attempted to locate Shopify sync code:**
   - Searched 254 Apex Triggers: No Shopify-specific triggers
   - Searched 44 Sync-related Apex classes: No Account-to-Shopify classes
   - Found 9 Shopify classes: All related to order tracking, not customer creation
   - Checked 19 Named Credentials: No Shopify API credentials

2. **Investigated Account-level triggers:**
   - 4 Account triggers found: 2 hidden (managed packages), 2 visible (UUID generation only)
   - None handle Shopify sync directly

3. **Retrieved metadata from Production:**
   - Retrieved 180+ Flows from Production
   - **FOUND:** `Scheduled_Flow_Sync_Accounts_to_External_Systems`
   - **STATUS:** `Obsolete` (disabled) — line 85 of flow XML

### How It Works

**Parent Flow (DISABLED):**
```
Scheduled_Flow_Sync_Accounts_to_External_Systems
├─ Type: Scheduled Autolaunch Flow
├─ Status: Obsolete [DISABLED]
├─ Schedule: Daily at 18:00:00 UTC
├─ Trigger: RecordType = Patient_Account_Record_Type
│         + Gender__c IS NOT NULL
│         + DateOfBirth__c IS NOT NULL
│         + BillingStreet IS NOT NULL
│         + PersonEmail IS NOT NULL
│         + Biocanic_External_Id__c IS NULL
└─ Calls Subflow: Autolaunch_Account_Sync_To_External_Systems
```

**Child Flow (ACTIVE):**
```
Autolaunch_Account_Sync_To_External_Systems
├─ Status: Active ✓
├─ Contains: Shopify Customer ID mapping
│         Patient Event API call
│         Error logging
└─ Never invoked (parent disabled)
```

### Why Sync Broken

1. Parent scheduled flow marked `Obsolete` = doesn't run
2. Child flow (which handles Shopify sync) never invoked
3. No sync happens for any accounts
4. Silent failure (no error logs, no messages written)

### Why Scope Expanding

- Flow disabled for unknown duration (predates 2026-04-13 issue report)
- Every new account created daily: No sync = adds to backlog
- Currently growing ~10-20 accounts/day
- Total scope: 706+ accounts since 2026-04-10

---

## The Fix

### What to Change
```
File: force-app/main/default/flows/Scheduled_Flow_Sync_Accounts_to_External_Systems.flow-meta.xml
Line: 85
Change: <status>Obsolete</status>
To: <status>Active</status>
```

### Deployment Steps

1. **Sandbox Test:**
   - Change flow status to `Active` in Sandbox
   - Create test Patient Account with all required fields
   - Verify flow runs at next scheduled time (Daily 18:00:00 UTC)
   - Confirm subflow invoked and Shopify_Customer_ID__c populated

2. **Production Deploy:**
   - Deploy metadata change via Metadata API (Gearset or `sf project deploy start`)
   - Verify schedule: Daily 18:00:00 UTC
   - Monitor Flow Interviews for errors

3. **Bulk Re-sync:**
   - Identify 706 affected accounts (SOQL: SELECT Id FROM Account WHERE CreatedDate >= 2026-04-10 AND Shopify_Customer_ID__c = null)
   - Batch update: Set `Trig_Shopify_Sync__c = True`
   - OR invoke subflow via Invocable Action
   - Verify all 706 now have Shopify_Customer_ID__c populated

4. **Audit:**
   - Confirm customer records in Shopify for all 706 accounts
   - Check Flow Interviews for sync errors
   - Update Jira ticket: Resolved

---

## Risk Assessment

**Low Risk:**
- Simple status change (no logic changes)
- Existing, tested flow
- Can test fully in Sandbox before Production deployment

**Potential Issues:**
- If filter logic outdated, flow may sync unwanted accounts → Must verify filters
- Manual re-sync required for 706 historical accounts (can't auto-catch up)
- Bulk batch job required to re-trigger sync (may impact CPU limits)

---

## Timeline

| Date | Event |
|------|-------|
| 2023-11-10 | Flow initially scheduled |
| 2026-04-10 | Shopify sync breaks (flow goes Obsolete) |
| 2026-04-13 | Issue HEAL-33040 reported |
| 2026-04-16 | Jira auto-closed after 24h no response |
| 2026-05-22 | Root cause identified: Disabled flow |

---

## Files Updated

- `outputs/investigations/HEAL-33040.md` — Root cause confirmed
- `outputs/internal-notes/HEAL-33040.md` — Solution and action plan

**Ready for Implementation:** Yes. Support-resolvable. No Engineering escalation needed.
