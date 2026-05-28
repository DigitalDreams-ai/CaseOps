# CaseOps Pipeline Run Summary — 2026-05-26

**Run Date:** 2026-05-26  
**Issues in Scope:** 1  
**Issues Processed:** 1  
**Support-fixed:** 1  
**Engineering-escalated:** 0  
**On-hold / Blockers:** 0  

---

## Executive Summary

Single issue processed through the CaseOps Jira-to-Salesforce fix pipeline. Root cause identified as a CMT configuration mismatch (not a code defect), allowing resolution at the Support level. Fix deployed to Sandbox and validated. Ready for Production deployment via Gearset.

---

## Issue Rollup

| Issue | Jira Status | Summary | Disposition | Prod Deploy? | Next Step |
|---|---|---|---|---|---|
| HEAL-33633 | In Progress | Wellvi Submission error Joshua Brown | Support-fixed (Sandbox deployed) | Yes — Gearset | Deploy to Production; smoke test; close |

---

## Sandbox Deployments / Validations

| Issue | Sandbox | Deployment | Prod Deploy Needed? |
|---|---|---|---|
| HEAL-33633 | 10xhealth-sean | 4 CMT JSON path updates (Wellvi shipping address parameters) | Yes — Gearset |

---

## Solution Details — HEAL-33633

**Root Cause:** CMT JSON path configuration mismatch. The `API_Parameter__mdt` records for Wellvi were mapping address fields to nested lowercase paths (`$.shippingAddress.city`), but the Wellvi/TenX API contract expects root-level PascalCase (`$.City`).

**Fix Applied:** Updated four CMT records with correct JSON paths:
- `Wellvi_SP_Shipping_City` → `$.City`
- `Wellvi_SP_Shipping_Street` → `$.AddressLine1`
- `Wellvi_SP_Shipping_State` → `$.StateProvince`
- `Wellvi_SP_Shipping_Zip_Code` → `$.PostalCode`

**Sandbox Validation:** Deployed to `10xhealth-sean`; SOQL verification confirms correct paths.

**Production Status:** Defective mappings currently live. Order `801Ql00000zolrtIAA` exhibits the HTTP 400 failure. Gearset promotion required after operator authorization.

---

## Closed / Resolved (Skipped)

None. No issues had Closed or Resolved status at triage.

---

## Escalated to Engineering

None. Earlier escalation withdrawn; issue resolved at Support level via metadata configuration update.

---

## Artifact Index

- **Jira Summary:** `outputs/jira/summary/HEAL-33633.md`
- **Investigation:** `outputs/investigations/HEAL-33633.md`
- **Internal Notes:** `outputs/internal-notes/HEAL-33633.md`
- **Jira Message (Customer-facing):** `outputs/jira-messages/HEAL-33633.md`
- **Test Report:** `outputs/test-reports/HEAL-33633.md`

---

## Production Deployment Checklist

Before Gearset promotion:
- [ ] Operator reviews and approves the updated CMT JSON paths
- [ ] Operator runs Gearset deployment of the 4 CMT updates to Production
- [ ] Operator executes Production smoke test with Order `801Ql00000zolrtIAA`
- [ ] Reporter (KKrupnik) confirms successful submission to Wellvi
- [ ] Operator closes HEAL-33633 in Jira with resolution message

---

## Pipeline Run Duration

- Issue sync: Immediate (single issue provided)
- Investigation/diagnosis: 2026-05-20 — 2026-05-26 (6 days for initial escalation analysis)
- Support resolution: 2026-05-26 (1 day for fix identification, deployment, and validation)
- **Total time to Support fix:** 7 days (including escalation reconsideration)

---

## Recommendations

1. **Deploy to Production promptly** — CMT fix is low-risk (metadata configuration only); no code changes.
2. **Audit Wellvi logs** — Check if other Orders experienced the same HTTP 400 error since 2026-05-14.
3. **Consider pre-submission validation** — Add Apex validation to `PharmacyOrderValidation` to prevent submission of incomplete addresses and improve user-facing error messages.

---

## Sign-Off

**Pipeline completed by:** CaseOps AI Agent  
**Date:** 2026-05-26  
**Status:** Ready for operator handoff (Production deployment and smoke testing)

**Operator action required:** Gearset deployment + Production smoke test + Jira closure.
