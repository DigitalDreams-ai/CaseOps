# Lab Order Issues Analysis - 2026-05-18 Summary

## Overview

Processed 7 CaseOps issues using Lab Order documentation (Vendor Statuses, FAQ, Technical SOPs). Findings:

### Issue Disposition

**Total Issues: 7**
- Engineering Escalations: 3 (HEAL-32826, HEAL-33316, HEAL-33616)
- Likely Engineering: 2 (HEAL-33439, HEAL-33505)
- Support-Resolvable: 2 (HEAL-33391, HEAL-33569)

---

## Engineering Escalations (Completed Handoffs)

### 1. HEAL-32826 — PAM Informed Consent Cases for Shopify Orders
**Status:** On Hold | **Root Cause:** Shopify→SF sync failure (3/18–3/27); post-3/27 fix restored sync for new orders
**Lab Order Connection:** Consent workflow (Informed Consent field required on accounts)
**Handoff:** outputs/engineering-escalations/HEAL-32826.md
**Next Step:** Engineering audit Account/Opportunity creation flow; validate bulk backfill via "Assign patient agreements"

---

### 2. HEAL-33316 — Cannot Generate Pharmacy Order
**Status:** Waiting for Customer | **Root Cause:** Flow unhandled fault error ("An unhandled fault has occurred in this flow")
**Lab Order Connection:** Pharmacy order generation is parallel workflow to Lab Orders
**Handoff:** Pending (user retry status) | **Next Step:** Engineering diagnose flow error once customer confirms persistent issue

---

### 3. HEAL-33616 — Salesforce Lab Order Error: Update Order Flow
**Status:** In Progress | **Root Cause:** "Update Order" flow missing category/product in API payload to Novogenia
**Lab Order Connection:** DIRECT Lab Order issue (update demographics + resubmit to vendor)
**Handoff:** outputs/engineering-escalations/HEAL-33616.md
**Affected Lab Orders:** a47Ql000000O2NFIA0 (NG101969, Novogenia), a47Ql000000M5gzIAC
**Error:** "Please insert a category or a product!" (HTTP 400 from Novogenia)
**Next Step:** Engineering review "Update Order" flow field mappings; validate Product/Category presence before API call

---

## Likely Engineering Escalations (Require Further Analysis)

### 4. HEAL-33439 — Getting Error When Submitting Order to Wellvi
**Status:** In Progress | **Issue Type:** Pharmacy order submission error
**Lab Order Connection:** Vendor integration error (parallel to Lab Order vendor submissions)
**Evidence:** Screenshot of error attached (not yet reviewed in detail)
**Next Step:** Analyze error screenshot; likely flow/API integration issue; Engineering escalation probable

---

### 5. HEAL-33505 — Opportunity Field History for Order Notes Activity Tracking
**Status:** In Progress | **Issue Type:** Feature request
**Lab Order Connection:** Would improve tracking on Opportunity (Lab Orders link to Opportunities)
**Scope:** Requires Apex/flow to track specific field edits in field history
**Next Step:** Engineering; requires custom solution (not configurable)

---

## Support-Resolvable Issues (Access/Permission)

### 6. HEAL-33391 — Need Access to View All Orders in Salesforce
**Status:** In Progress | **Issue Type:** Access/permission
**Requester:** Sarah Phonthaphanh (order processing manager)
**Also needed by:** Kaci Krupnik, Sarah Courchia, Kristhal Valdez
**Lab Order Connection:** "All Orders" list view would include Lab Orders
**Next Step:** SUPPORT-RESOLVABLE
  - Assign permission set for Order object read/list view access, OR
  - Grant edit access to "All Orders" list view if already configured, OR
  - Create "All Orders" list view and assign to Permission Set for Ops team

---

### 7. HEAL-33569 — Access to Generate Supplement Order
**Status:** In Progress | **Issue Type:** Access issue + potential flow error
**Requester:** Marianne Sallo (request approved by Danielle)
**Lab Order Connection:** Supplement order generation may be parallel to Lab Orders (some vendors offer supplements)
**Details:** User can see button but encounters error when clicking
**Attachments:** 2 screenshots (error + button reference)
**Next Step:** CONDITIONAL
  - If error is access/permission: Support-resolvable (assign permission set for flow action access)
  - If error is flow execution: Engineering escalation (unhandled flow exception)
  - Requires screenshot review to determine classification

---

## Lab Order Documentation Applied

From ingested PDFs:
- ✓ Used "Update Order" button visibility logic (HEAL-33616 diagnosis)
- ✓ Referenced vendor-specific status mappings (Novogenia, 3PL context)
- ✓ Applied Lab Order field structure knowledge (Height/Weight, Category, Product context)
- ✓ Used error classification matrix (flow errors vs. permission vs. data validation)

---

## Recommended Operator Actions (Priority Order)

### IMMEDIATE (Customer-Blocking Issues)
1. **HEAL-33616** — Lab Order Update flow broken
   - Escalate to Engineering immediately (affects multiple Lab Orders, customer blocking)
   - Handoff: outputs/engineering-escalations/HEAL-33616.md
   
2. **HEAL-33439** — Wellvi pharmacy order blocked
   - Review error screenshot; escalate to Engineering (likely API integration)
   - Timeline: Customer ''completely blocked'' — urgent

### SHORT-TERM (1-2 days)
3. **HEAL-33391** — Access for order processing managers
   - Identify "All Orders" list view; confirm if it exists
   - Assign Order object read + list view permission to Sarah and team
   - Support-resolvable (5-10 min implementation)

4. **HEAL-33569** — Access to Generate Supplement Order
   - Review screenshots; classify (access vs. flow error)
   - If access: assign flow action permission set (5 min)
   - If flow error: escalate to Engineering

### FOLLOW-UP (Pending Input)
5. **HEAL-32826** — Informed Consent backfill (awaiting Engineering decision)
6. **HEAL-33316** — Pharmacy order flow (awaiting customer retry confirmation + Engineering diagnosis)
7. **HEAL-33505** — Field history feature (Engineering project; lower priority)

---

## Files Created Today

- outputs/investigations/HEAL-32826.md
- outputs/investigations/HEAL-33316.md
- outputs/investigations/HEAL-33616.md
- outputs/engineering-escalations/HEAL-32826.md
- outputs/engineering-escalations/HEAL-33616.md
- outputs/jira-responses/HEAL-32826.md
- outputs/jira-responses/HEAL-33316.md
- outputs/issue-summary-2026-05-18.md
