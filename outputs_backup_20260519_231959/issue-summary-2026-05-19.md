# Issue Summary — 2026-05-19

**Pipeline run date:** 2026-05-19  
**Issues processed:** 4  
**Escalations:** 1 (Engineering)  
**Support-resolved:** 2 (Sandbox validated, ready for Production promotion)  
**Operational follow-up:** 1 (awaiting customer clarification on scope)

---

## Summary

Four Jira issues processed on 2026-05-19:

1. **HEAL-33628 (Support-resolvable):** "Send Patient Agreements" SF feature not opening consents for numerous patients. Root cause: Portal users lacked READ permission on `Patient_Agreement__c` custom object. Fix: Added READ access to `Portal - Authenticated User` profile. Validated in Sandbox (deployment ID 0AfEa00000Zr1oDKAR). Ready for Production promotion via Gearset.

2. **HEAL-33659 (Support-resolvable):** Supplement Inquiry picklist field requested for Case object. Field created, configured with 36 product values, placed in Case-Customer Experience layout Call Details section, and validated in Sandbox (deployment ID 0AfEa00000ZxSFRKA3). Ready for Production promotion via Gearset.

3. **HEAL-33682 (Engineering escalation):** Novogenia API integration missing record-creation step for `#VRSF` (PGT Booklet) product code. SOQL audit confirmed three affected Lab Orders with no corresponding Salesforce records. Escalated to Engineering for code review and fix development.

4. **HEAL-33066 (Operational follow-up):** Price Book Creation — original scope (Quest and Evexia price books, 59 product activations) completed and approved on 2026-05-12. Reporter (Carlin French) on 2026-05-15 requested follow-up meeting to discuss additional adjustments. Scope of adjustments pending customer clarification. Responding with offer to schedule meeting and request detailed adjustment requirements.

---

## Issue Rollup

| Issue | Jira Status | Summary | Disposition | Root Cause | Prod Deploy? | Next Step |
|-------|-----------|---------|-----------|-----------|------------|-----------|
| HEAL-33066 | Waiting for support | Price Book Creation | Operational follow-up | Original scope complete (Quest + Evexia price books, 59 products activated). Reporter requesting meeting to scope follow-up adjustments (2026-05-15). | N/A (follow-up scope TBD) | Schedule meeting with Carlin French to clarify adjustment requirements; open new ticket(s) per her guidance |
| HEAL-33628 | Waiting for support | "Send Patient Agreements" SF feature not opening consents for numerous patients | Support-resolvable | Portal users lack READ permission on `Patient_Agreement__c` | **Yes — Gearset** | Deploy profile changes to Production; test end-to-end consent signing |
| HEAL-33659 | Escalated | Cx Case function Additions | Support-resolvable | Supplement_Inquiry__c picklist field missing from Case object and layout; field pre-exists but not accessible | **Yes — Gearset** | Promote layout + FLS to Production; verify post-deploy |
| HEAL-33682 | Waiting for support | Orphan PGT Booklets- No order on SF | Escalated to Engineering | Novogenia API includes `#VRSF` product code, but Salesforce record-creation logic is missing or broken | N/A (code fix required) | Engineering: review integration code; access Nebula Logger logs; implement fix in Sandbox; backfill affected records |

---

## Escalated to Engineering

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
|-------|-----------|-----------|------------|---------|---|
| HEAL-33682 | Waiting for support | Novogenia API integration + Lab_Order__c / Opportunity automation | `outputs/engineering-escalations/HEAL-33682.md` | Novogenia API includes `#VRSF` product code in outbound payloads; Salesforce has no corresponding Lab Order line item or child record; no `#VRSF` product mapping exists in Salesforce Product2. | Identify Salesforce code/Flow that includes `#VRSF` in payload; add or repair missing record-creation step; backfill records for three affected Lab Orders; audit for additional orphaned orders beyond scope |

---

## Sandbox Deployments / Validations

| Issue | Status | Sandbox | Deployment | Test Result | Prod Deploy Needed? |
|-------|--------|---------|-----------|------------|----------|
| HEAL-33628 | Support-resolvable | 10xhealth-sean | Deploy ID 0AfEa00000Zr1oDKAR; Profile + READ permissions on Patient_Agreement__c and Patient_Agreement_Configuration__c | Portal profile verified to have READ access; test records created and accessible; all tests passed | **Yes — Gearset** (profile only) |
| HEAL-33659 | Support-resolvable | 10xhealth-sean | Deploy ID 0AfEa00000ZxSFRKA3 (6.86s); 2/2 components (layout + FLS) | All 36 picklist values present; field visible/editable in layout; FLS correct; no breaking changes | **Yes — Gearset** (layout + FLS only) |
| HEAL-33682 | N/A — Engineering escalation | N/A | N/A | N/A | N/A (pending Engineering fix development) |

---

## Artifact Index

### HEAL-33066 (Price Book Creation — Follow-up Scoping)
- **Jira summary:** `outputs/jira/summary/HEAL-33066.md`
- **Investigation:** `outputs/investigations/HEAL-33066.md` (Issue Understanding: original scope complete, follow-up scope pending)
- **Internal notes:** `outputs/internal-notes/HEAL-33066.md` (original work summary, follow-up requirements analysis)
- **Jira message:** `outputs/jira-messages/HEAL-33066.md` (customer-facing response offering meeting to clarify adjustments)
- **Test report:** `outputs/test-reports/HEAL-33066.md` (original scope: 6/6 tests passed, UAT outcome pending)

### HEAL-33628 (Send Patient Agreements — Consent Portal Access)
- **Jira summary:** `outputs/jira/summary/HEAL-33628.md`
- **Investigation:** `outputs/investigations/HEAL-33628.md` (root cause confirmed: missing Portal profile permissions on Patient_Agreement__c)
- **Internal notes:** `outputs/internal-notes/HEAL-33628.md` (Support-resolvable fix, deployment readiness)
- **Jira message:** `outputs/jira-messages/HEAL-33628.md` (customer-facing update with Sandbox validation results)
- **Test report:** `outputs/test-reports/HEAL-33628.md` (Sandbox deployment ID 0AfEa00000Zr1oDKAR, all tests passed)

### HEAL-33659 (Supplement Inquiry Picklist)
- **Jira summary:** `outputs/jira/summary/HEAL-33659.md`
- **Investigation:** `outputs/investigations/HEAL-33659.md` (root cause, solution plan, Sandbox deployment details)
- **Internal notes:** `outputs/internal-notes/HEAL-33659.md` (solution summary, production vs sandbox state)
- **Jira message:** `outputs/jira-messages/HEAL-33659.md` (customer-facing update with deployment readiness)
- **Test report:** `outputs/test-reports/HEAL-33659.md` (Sandbox validation results, deployment ID 0AfEa00000ZxSFRKA3)

### HEAL-33682 (Orphan PGT Booklets)
- **Jira summary:** `outputs/jira/summary/HEAL-33682.md`
- **Jira raw:** `outputs/jira/raw/HEAL-33682.json`
- **Investigation:** `outputs/investigations/HEAL-33682.md` (includes SOQL audit findings, confirmed facts, root cause analysis)
- **Engineering escalation:** `outputs/engineering-escalations/HEAL-33682.md` (detailed handoff with reproduction steps, affected components, potential fix)
- **Internal notes:** `outputs/internal-notes/HEAL-33682.md` (summary of findings and escalation rationale)
- **Jira message:** `outputs/jira-messages/HEAL-33682.md` (customer-facing and internal Jira comments with evidence)

---

## Data Audit Summary (2026-05-19)

**Queries executed:**
1. Lab_Order__c records for affected IDs — **3 confirmed** (LAB-000228814, LAB-000232068, LAB-000058193)
2. OpportunityLineItem records for affected Opportunities — **3 records found** (one per Opp, all for main PGT product, no booklet)
3. Product2 query for `#VRSF` product code — **0 results** (product code does not exist in Salesforce)
4. Product2 query for "Printed Report Books" — **1 found** (Product2 ID `01tRh000006VKS1IAO`, no ProductCode, unused)
5. Lab_Order_Product__c junction object query — **does not exist**
6. Novogenia integration code in local repo — **not found** (Production-only or managed package)

**Key findings:**
- All three Lab Orders linked to correct Opportunities ✓
- Each Opportunity has main PGT product (OpportunityLineItem) ✓
- **None have the "Printed Report Books" product or any `#VRSF` reference** ✗
- Novogenia Portal confirms `#VRSF` fulfilled on all three orders (external source of truth)
- Salesforce has the semantic equivalent product but it's not mapped to a ProductCode and not linked to these Opportunities
- No custom data model exists for multi-product Lab Orders

**Conclusion:** Silent data gap confirmed — Novogenia payload includes `#VRSF`, API call succeeds, but Salesforce record-creation step is missing or broken.

---

## Operational Notes

- **Reporter:** Jennifer Lara Ramirez (On Global)
- **Contact:** Courtney Marlin (Sr. Technical Support Analyst) — provided Novogenia Portal verification
- **Assignee:** Sean Bingham
- **Reporter's impact:** Moderate (workaround available; awaiting escalation resolution)
- **Engineering queue:** Currently processing high/critical priority items; expected delay on this investigation

---

## Follow-Up Actions

1. [ ] Engineering accesses historical Novogenia API logs (Nebula Logger UI or EventLogFile) for the three Lab Order IDs
2. [ ] Engineering reviews Novogenia integration code to identify record-creation step
3. [ ] Engineering develops and tests fix in Sandbox (10xhealth-sean)
4. [ ] Engineering conducts data audit to identify total scope of orphaned PGT Booklet orders
5. [ ] Engineering backfills or determines strategy for retroactive record creation
6. [ ] Support posts resolution update in Jira (HEAL-33682)
7. [ ] Operator promotes fix from Sandbox to Production via Gearset (if Engineering approves)
