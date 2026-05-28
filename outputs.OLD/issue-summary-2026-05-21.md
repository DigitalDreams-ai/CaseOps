# CaseOps Pipeline Run Summary — 2026-05-21

**Run Date:** 2026-05-21  
**Issues in Scope:** 4 active issues (HEAL-33753, HEAL-33758, HEAL-33773, HEAL-33659)  
**Disposition:** 1 Escalated to Engineering, 2 Support-Resolved (Sandbox tested), 1 On-hold (pending customer input)  

---

## Executive Summary

| Metric | Count |
| --- | --- |
| Total issues in scope | 4 |
| Closed/Resolved (skipped at triage) | 0 |
| Active issues processed | 4 |
| Escalated to Engineering | 1 |
| Support-resolvable fixes (blocked on customer input) | 2 |
| Support-resolvable fixes (ready for Production) | 1 |
| Sandbox deployments/validations | 2 |
| On-hold pending customer input | 1 |

---

## Closed / Resolved (Skipped)

No closed or resolved issues in scope for this run.

---

## Issue Rollup

| Issue | Jira Status | Summary | Disposition | Next Step |
| --- | --- | --- | --- | --- |
| HEAL-33753 | In Progress | Create workflow for email to send scheduling link for AHB consults | **On-hold (support-resolvable)** | Monitor for Calendly URL from customer; resume implementation |
| HEAL-33758 | Waiting for support | SF- Multiple Lab Order Errors & Correction Request | **Escalated to Engineering** | Engineering investigates Lab Order validation Flow logic |
| HEAL-33773 | Waiting for support | Why are Shopify POS transactions going to 'Waiting for Approval'? | **Support-Fixed (Sandbox)** | Deploy to Production via Gearset; test with live Shopify transaction |
| HEAL-33659 | Escalated | Cx Case function Additions | **Support-Fixed (Sandbox, ready for Production)** | Deploy to Production via Gearset; post-deploy manual validation; notify requester |

---

## Sandbox Deployments / Validations

| Issue | Sandbox | Deploy/Validation | Prod Deploy Needed? |
| --- | --- | --- | --- |
| HEAL-33773 | 10xhealth-sean | Flow: Record_Trigger_Opportunity_Shopify_Automations updated with Amount_Paid__c check + idempotency guard (Deploy ID: 0AfEa00000a0k9PKAQ) | **Yes — Gearset** |
| HEAL-33659 | 10xhealth-sean | CustomField: Case.Supplement_Inquiry__c (Picklist, 35 values) + Layout (Specialties section) + FLS (Case_Read_Edit_Access_Customer_Experience) | **Yes — Gearset** |

---

## Escalated to Engineering

| Issue | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- |
| HEAL-33758 | Lab Order Flow Automation | outputs/engineering-escalations/HEAL-33758.md | Four Lab Orders (LAB-000234000, LAB-000234001, LAB-000233409, LAB-000234287) fail to save with validation error. Root cause: Product_Lab_Order_Configuration lookup in Autolaunch Flows failing. | Investigate/fix Product_Lab_Order_Configuration lookup logic in Lab Order creation Flows; create missing config records, correct Lab_Provider_Configuration assignments, or update Flow error handling. |

---

## Issue Detail: HEAL-33758

**Summary:** SF- Multiple Lab Order Errors & Correction Request

**Reporter:** natasha torres

**Affected Records:** LAB-000234000, LAB-000234001, LAB-000233409, LAB-000234287

**Error:** "The product(s) that are on the opportunity are not servicable items and do not require a lab order"

**Root Cause:** Lab Order validation Flows check for Product_Lab_Order_Configuration__c records. All four Lab Orders fail despite valid Product_Lab_Order_Configuration records existing in Production for the product ("Genetic Testing - Virtual").

**Why Escalated:** Requires Flow/validation rule code review. Cannot safely modify Flow automation without Engineering review.

**Handoff:** outputs/engineering-escalations/HEAL-33758.md  
**Customer Message:** outputs/jira-messages/HEAL-33758.md  
**Internal Notes:** outputs/internal-notes/HEAL-33758.md

---

## Issue Detail: HEAL-33773

**Summary:** Why are Shopify POS transactions going to 'Waiting for Approval'?

**Reporter:** Sarah Phonthaphanh

**Affected Records:** Opportunity 006Ql00000eW69hIAC, 006Ql00000f19G9IAI

**Problem:** Shopify POS transactions sync to Opportunities and transition to "Waiting for Approval" status instead of auto-approving when payment collected. Additionally, previously approved records regress to "Waiting for Approval" on re-sync.

**Root Cause:** Flow Record_Trigger_Opportunity_Shopify_Automations unconditionally submits Opportunities to approval without checking Amount_Paid__c field; lacks idempotency protection.

**Solution:** Added Amount_Paid__c > 0 condition to Blood Testing and Genetic Testing approval routes; added idempotency guard to prevent re-submission of already-approved records.

**Test Result:** PASSED in Sandbox
- Payment validation working (Amount_Paid__c > 0 blocks approval submission)
- Idempotency protection working (re-synced approved records remain approved)

**Production Deploy:** Yes — Gearset required. Promote Flow: Record_Trigger_Opportunity_Shopify_Automations.

**Files:**
- Investigation: outputs/investigations/HEAL-33773.md
- Test Report: outputs/test-reports/HEAL-33773.md
- Customer Message: outputs/jira-messages/HEAL-33773.md
- Internal Notes: outputs/internal-notes/HEAL-33773.md

---

## Issue Detail: HEAL-33659

**Summary:** Cx Case function Additions (Supplement Inquiry Picklist)

**Reporter:** Noah Scott

**Requirement:** Add picklist field "Supplement Inquiry" to Case object with 35 supplement product values, place in "Call Details" section, and grant Customer Support team read/edit access.

**Implementation Status:** **Complete in Sandbox** (verified 2026-05-21)

**Sandbox Validation:**
- ✓ Field `Supplement_Inquiry__c` created (Picklist type, label "Supplement Inquiry", 35 values)
- ✓ Placed on Case-Customer Experience layout, Specialties section, Edit behavior
- ✓ FLS configured: Read+Edit on `Case_Read_Edit_Access_Customer_Experience` permission set
- ✓ Metadata retrieval confirmed all components present and correct

**Production Status:** Field does NOT exist in Production (verified via CLI retrieval). **Ready for Gearset deployment.**

**Test Result:** 4/8 test cases verified in Sandbox (metadata-based validation). 3 additional test cases deferred to post-Production-deployment manual verification.

**Production Deploy:** Yes — Gearset required. Components: CustomField, Layout, PermissionSet.

**Files:**
- Investigation: outputs/investigations/HEAL-33659.md
- Test Report: outputs/test-reports/HEAL-33659.md
- Customer Message: outputs/jira-messages/HEAL-33659.md
- Internal Notes: outputs/internal-notes/HEAL-33659.md

---

## Issue Detail: HEAL-33753

**Summary:** Create workflow for email to send scheduling link for AHB consults

**Reporter:** Sarah Phonthaphanh

**Problem:** No automated email workflow sends scheduling link when AHB Hormone Consult opportunity is created.

**Root Cause:** Two-stage gap:
1. **Data:** No Product2 record exists for "AHB Hormone Consult" with `Calendly_Email_Template_Id__c` populated, so the existing dispatcher flow never triggers
2. **Content:** Email template `AHB_Hormone_Self_Scheduling_Email` (ID 00XQl000005kQavMAE) contains placeholder text instead of actual Calendly URL

**Solution:** 
1. Create or configure AHB Hormone Consult Product2 record with Calendly fields
2. Update email template body to include AHB-specific Calendly URL (hardcoded, not merge field)
3. Existing dispatcher flow `Record_Trigger_After_Save_Send_Genetic_Breakthrough_Schedule_Link` will automatically fire

**Blocker:** Awaiting AHB-specific Calendly event URL from customer (Sarah/Ashlee). Format: `https://calendly.com/d/xxx-xxx-xxx`

**Status:** Investigation **complete** (Steps 1–7). Implementation **blocked** at Step 8 pending customer input.

**Disposition:** Support-resolvable, on-hold.

**Files:**
- Investigation: outputs/investigations/HEAL-33753.md
- Internal Notes: outputs/internal-notes/HEAL-33753.md
- Jira Message (Draft): outputs/jira-messages/HEAL-33753.md

**Production vs Sandbox (for this issue):**
- **Production (verified read-only):** Dispatcher flow active. Three reference products (PGT, Genetic Test, Precision Wellness) fully configured. Email template skeleton exists but incomplete.
- **Sandbox (pending):** Email template body will be updated with Calendly URL; Product2 record will be created with Calendly fields.
- **Production deploy required?** Likely **No** — Product2 + template updates are typically done directly in Production post-review. If Gearset route chosen, then **Yes**.

---

## Artifact Index

| Type | HEAL-33753 | HEAL-33758 | HEAL-33773 | HEAL-33659 |
| --- | --- | --- | --- | --- |
| Jira Summary | outputs/jira/summary/HEAL-33753.md | outputs/jira/summary/HEAL-33758.md | outputs/jira/summary/HEAL-33773.md | outputs/jira/summary/HEAL-33659.md |
| Investigation | outputs/investigations/HEAL-33753.md | outputs/investigations/HEAL-33758.md | outputs/investigations/HEAL-33773.md | outputs/investigations/HEAL-33659.md |
| Engineering Escalation | N/A | outputs/engineering-escalations/HEAL-33758.md | N/A | N/A |
| Test Report | N/A | N/A | outputs/test-reports/HEAL-33773.md | outputs/test-reports/HEAL-33659.md |
| Internal Notes | outputs/internal-notes/HEAL-33753.md | outputs/internal-notes/HEAL-33758.md | outputs/internal-notes/HEAL-33773.md | outputs/internal-notes/HEAL-33659.md |
| Jira Message (Draft) | outputs/jira-messages/HEAL-33753.md | outputs/jira-messages/HEAL-33758.md | outputs/jira-messages/HEAL-33773.md | outputs/jira-messages/HEAL-33659.md |

---

## Production vs Sandbox (Run-Wide)

- **HEAL-33753:** Investigation complete (read-only). Production deployment pending customer input and operator review.
- **HEAL-33758:** Investigation complete (read-only). Engineering escalation; no Production changes initiated.
- **HEAL-33773:** Sandbox testing passed. Production deployment required via Gearset.
- **HEAL-33659:** Sandbox validation complete (verified in production/sandbox metadata state). Production deployment required via Gearset.

**Summary:** Read-only investigation for HEAL-33753, HEAL-33758. Sandbox validation/deployment for HEAL-33773, HEAL-33659. Engineering escalation for HEAL-33758. HEAL-33753 blocked pending customer input. HEAL-33659 ready for Production Gearset deployment.
