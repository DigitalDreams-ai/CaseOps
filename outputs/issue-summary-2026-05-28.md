# CaseOps Issue Summary - 2026-05-28

Generated: 2026-05-28  
Last updated: 2026-05-28

---

## Executive Summary

- **Total issues in scope:** 2
- **Escalated to Engineering (Jira status):** 0 (pre-escalated at sync)
- **Active issues processed:** 2 (HEAL-30437, HEAL-33098)
- **Engineering handoffs raised during processing:** 1 (HEAL-30437)
- **Sandbox-deployed or sandbox-validated:** 1 (HEAL-33098)
- **Operational / data / access follow-up, no metadata deploy:** 1 (HEAL-33098 — vendor coordination)

**Run result:** HEAL-30437 escalated to Engineering (flow configuration). HEAL-33098 processed through investigation, permission deployment, and vendor escalation for SMS Magic trial license renewal.

---

## Closed / Resolved (Skipped)

No issues with Closed, Resolved, or Canceled status in scope.

---

## Issue Rollup

Support-resolvable issues processed (excluding pre-escalated or Engineering-only issues).

| Issue | Jira Status At Sync | Summary | Disposition | Prod deploy? | Next Step |
| --- | --- | --- | --- | --- | --- |
| HEAL-33098 | In Progress | SMS Magic in lower envs (UAT, QA, DEV) access and licenses | Vendor escalation — permissions assigned, awaiting SMS Magic vendor to activate sandbox trial license | No | Contact SMS Magic vendor to activate sandbox trial for org 10xhealth--sean.sandbox |

---

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox (excluding pre-escalated or Engineering-only issues).

| Issue | Sandbox | Deploy / Validation | Prod deploy needed? |
| --- | --- | --- | --- |
| HEAL-33098 | 10xhealth--sean.sandbox | Permission set assignments (SMS_Interact_Permission_Set + SMS_Magic_Converse_Custom_Permissions assigned to Ona Brazwell) — PASS. SMS send blocked by expired trial license — BLOCKER. | No |

---

## Escalated to Engineering

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-30437 | In Progress | Flow: Record_Trigger_Opportunity_Shopify_Automations | `outputs/engineering-escalations/HEAL-30437.md` | Flow entry filter on Record_Trigger_Opportunity_Shopify_Automations excludes Shopify Network order source ("Affiliate"). Condition checks only "POS" OR "Store", causing flow to never trigger for Shopify Network orders, blocking auto-population. | Update flow START filter to include Shopify Network Transaction_Source__c value: Add `\|\| TEXT({!$Record.Transaction_Source__c}) = 'Affiliate'` to condition. |

---

## Details: HEAL-30437

**Issue:** Automate Shopify Network Order Release Process  
**Reporter:** Lydia Turner  
**Requestor:** Michael Moffo (Supply Chain Analyst)  
**Priority:** Medium  
**Status at sync:** In Progress

### Investigation Summary

**Root Cause Confirmed:**
Order auto-population flow (Record_Trigger_Opportunity_Shopify_Automations, ID: 300Rh000002XrSdIAK) has an entry filter that only matches DTC (Main) Shopify orders (Transaction_Source__c = "POS" OR "Store"). Shopify Network orders with Transaction_Source__c = "Affiliate" are excluded by the filter, preventing flow execution and blocking auto-population.

**Exact Failure Point:**
Flow START filter (lines 1282-1283): `( TEXT({!$Record.Transaction_Source__c}) = 'POS' || TEXT({!$Record.Transaction_Source__c}) = 'Store' ) && TEXT({!$Record.Transaction_Type__c}) = 'Shopify'`

**Evidence:**
- Flow definition queried from Production (Tooling API)
- Entry filter XML retrieved and analyzed
- Transaction_Source__c picklist confirmed includes "Affiliate" (unused in current filter)
- DTC (Main) auto-population works; Shopify Network does not

### Escalation Rationale

**Why escalated:** 
Flow configuration changes are Engineering-owned. The CaseOps pipeline has read-only Production authority and no flow deployment capability. Per Jira comments (Danielle Cress, 2026-04-28), Help Desk is not permitted to make Salesforce configuration changes.

**Fix ownership:** Engineering team to update flow START filter and deploy via Gearset.

### Production vs Sandbox

- **Production status:** Issue confirmed in Production; no changes made
- **Sandbox:** No Sandbox testing performed (configuration issue, not data-driven)
- **Production deploy required:** Yes — Gearset (after Engineering updates flow)
- **Timeline:** Pending Engineering prioritization

---

## Details: HEAL-33098

**Issue:** SMS Magic in lower envs (UAT, QA, DEV) access and licenses  
**Reporter:** Ona Brazwell  
**Assignee:** Sean Bingham  
**Priority:** Medium  
**Status at sync:** In Progress

### Investigation Summary

**Root Cause Confirmed:**
SMS Magic org-level trial license has expired in sandbox environments (QA, UAT, DEV) — independent from Production license cycle (30-day sandbox trial lifecycle). Secondary root cause: per-user permission assignments missing for engineering/QA team members in lower environments.

**Exact Failure Point:**
Org-level license check at SMS send time. When Ona Brazwell or team members attempt to send via SMS Magic in Sandbox, the system validates the org-level trial license first. Since the trial has expired, the system displays "trial expired" banner and blocks SMS send operations. Permission sets are now assigned (Sandbox deployment successful), but SMS functionality remains blocked until vendor activates the sandbox trial license.

**Evidence:**
- Production SMS Magic confirmed active with valid org-level license and 382 user assignments
- Sandbox SMS Magic package installed (v1.75.35.1) with 19 permission sets available
- Permission set assignments to Ona Brazwell successful (tested in Sandbox)
- "Trial expired" banner confirms sandbox trial license expiration
- SMS send blocked at org-level license validation (not a permission issue)

### Deployment Summary

**Sandbox Deployment (10xhealth--sean.sandbox):**
- SMS_Interact_Permission_Set assigned to Ona Brazwell (0PaEa00000bYBuzKAG) ✓
- SMS_Magic_Converse_Custom_Permissions assigned to Ona Brazwell (0PaEa00000bY8SXKA0) ✓
- SMS send tested: BLOCKED (expired trial license prevents send)

### Critical Blocker

**Vendor Escalation Required:**
SMS Magic trial license for org 10xhealth--sean.sandbox (00DEa00000RViur) has expired and must be renewed/activated by SMS Magic vendor. This is not self-serviceable via Salesforce Setup. The sandbox trial license requires vendor coordination (renewal or paid sandbox license add-on).

### Production vs Sandbox

- **Production status:** Fully functional. Org-level license valid. 382 user assignments active. No Production changes needed.
- **Sandbox status:** Permission assignments complete and tested. Awaiting vendor trial license activation for SMS send functionality.
- **Production deploy required:** No.
- **Next step:** Operator (Sean) must contact SMS Magic vendor to activate/renew sandbox trial license for org 10xhealth--sean.sandbox.

---

## Artifact Index

### HEAL-30437 (Engineering Escalation)
- **Jira summary:** `outputs/jira/summary/HEAL-30437.md`
- **Investigation:** `outputs/investigations/HEAL-30437.md`
- **Engineering handoff:** `outputs/engineering-escalations/HEAL-30437.md`
- **Internal notes:** `outputs/internal-notes/HEAL-30437.md`
- **Jira message draft:** `outputs/jira-messages/HEAL-30437.md`
- **Problem hypothesis (Step 4):** `outputs/step-4-hypothesis/HEAL-30437.md`

### HEAL-33098 (Vendor Escalation)
- **Jira summary:** `outputs/jira/summary/HEAL-33098.md`
- **Investigation:** `outputs/investigations/HEAL-33098.md`
- **Internal notes:** `outputs/internal-notes/HEAL-33098.md`
- **Jira message draft:** `outputs/jira-messages/HEAL-33098.md`
- **Test report:** `outputs/test-reports/HEAL-33098.md`

---

## Next Steps for Operator

### HEAL-30437 (Engineering Escalation)

1. **Review investigation and handoff**
   - Confirm problem identification: flow entry filter excludes Shopify Network
   - Review Engineering handoff: `outputs/engineering-escalations/HEAL-30437.md`

2. **Post Jira message (customer-facing)**
   - File: `outputs/jira-messages/HEAL-30437.md`
   - Target: Comment on Jira issue HEAL-30437 with customer-friendly explanation

3. **Coordinate with Engineering**
   - Provide Engineering handoff for flow update
   - Expected work: Update flow START filter to include Shopify Network source
   - Timeline: Await Engineering prioritization

4. **After Engineering deployment**
   - Verify Production fix (test with Shopify Network order)
   - Confirm DTC (Main) still auto-populates (regression test)
   - Update Jira issue with Production deploy completion

### HEAL-33098 (Vendor Escalation)

1. **Review investigation and test results**
   - Confirm permission set assignments successful: `outputs/test-reports/HEAL-33098.md`
   - Review internal notes: `outputs/internal-notes/HEAL-33098.md`

2. **Post Jira message (customer-facing)**
   - File: `outputs/jira-messages/HEAL-33098.md`
   - Target: Comment on Jira issue HEAL-33098 with findings and next steps

3. **Contact SMS Magic vendor**
   - Request: Activate/renew sandbox trial license for org 10xhealth--sean.sandbox (00DEa00000RViur)
   - Expected outcome: "Trial expired" banner removed, SMS Magic integration functional

4. **After vendor activation**
   - Verify Sandbox SMS send (test with Ona Brazwell account)
   - Confirm trial banner is gone
   - Update Jira issue with confirmation and timeline for UAT/QA/DEV environments
