# CaseOps Issue Summary - 2026-05-28

Generated: 2026-05-28  
Last updated: 2026-05-28

## Executive Summary

- **Total issues in scope:** 1
- **Escalated to Engineering (Jira status):** 0
- **Active issues processed:** 1
- **Engineering handoffs raised during processing:** 0
- **Sandbox-deployed or sandbox-validated:** 1 (manual application pending)
- **Operational / data / access follow-up, no metadata deploy:** 0
- **Closed/Resolved (skipped):** 0

**Pipeline Run:** Single issue (HEAL-33763) processed through Steps 1-10. Support-resolvable permission configuration fix. Manual Sandbox application and Production Gearset deployment required.

---

## Closed / Resolved (Skipped)

No issues closed or resolved at sync.

| Issue | Jira Status | Summary |
| --- | --- | --- |

---

## Issue Rollup

| Issue | Jira Status At Sync | Summary | Disposition | Prod deploy? (Gearset / No / N/A) | Next Step |
| --- | --- | --- | --- | --- | --- |
| HEAL-33763 | In Progress | Giving Tier 1 Tech Support more SF access | Support-fixed (manual Sandbox application pending) | **Yes — Gearset** | Admin applies fix to Sandbox, validates with Ray Guevarra, deploys to Production via Gearset |

---

## Sandbox Deployments / Validations

| Issue | Sandbox | Deploy / Validation | Prod deploy needed? |
| --- | --- | --- | --- |
| HEAL-33763 | 10xhealth--sean | Permission Set: add ContentDocument, ContentDocumentLink, Note object permissions. Sharing Rule: grant Tier 1 access to Andy Haas-owned Accounts/Opportunities. Manual application via Setup UI or Gearset (MDAPI limitation). Validation: file delete, record visibility, note creation on closed Opp. | **Yes — Gearset** |

---

## Escalated to Engineering

No issues escalated to Engineering.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |

---

## Artifact Index

- **Jira summaries:** `outputs/jira/summary/HEAL-33763.md`
- **Investigations:** `outputs/investigations/HEAL-33763.md`
- **Engineering handoffs:** None
- **Internal notes:** `outputs/internal-notes/HEAL-33763.md`
- **Jira message drafts:** `outputs/jira-messages/HEAL-33763.md`
- **Test reports:** `outputs/test-reports/HEAL-33763.md`

---

## Next Steps for Operator

1. **Review investigation and fix details**
   - `outputs/investigations/HEAL-33763.md` — full diagnosis and metadata findings
   - `outputs/internal-notes/HEAL-33763.md` — internal notes on fix approach

2. **Manual Sandbox Application (Salesforce Admin)**
   - Permission Set "Tier 1" (ID: 0PSRh00000025ObOAI) requires manual updates via Setup UI or Gearset:
     - Add ContentDocument object: Delete=true
     - Add ContentDocumentLink object: Read, Edit, Delete=true
     - Add Note object: Create, Read, Edit=true
   - Create Sharing Rule: Opportunity & Account objects, Owner = Andy Haas, Grant to = Tier 1 Team, Access Level = Read/Edit
   - Apply changes to 10xhealth--sean Sandbox

3. **Validation Testing (with Tier 1 staff)**
   - Test 1: Ray Guevarra deletes file from test Opportunity (should succeed)
   - Test 2: Ray Guevarra views test Opportunity owned by Andy Haas (should succeed, not access denied)
   - Test 3: Ray Guevarra adds note to closed Opportunity (should succeed)
   - Log results in `outputs/test-reports/HEAL-33763.md`

4. **Production Deployment via Gearset**
   - Deploy Permission Set and Sharing Rule changes to Production
   - Notify Danielle Cress and Tier 1 team of go-live
   - Post Jira message: `outputs/jira-messages/HEAL-33763.md`

---

## Pipeline Statistics

| Metric | Count |
| --- | --- |
| Issues processed | 1 |
| Escalations | 0 |
| Support-owned fixes | 1 |
| Sandbox deployments (pending manual application) | 1 |
| Closed/Resolved | 0 |

---

**Run Date:** 2026-05-28  
**Operator:** Claude Code Pipeline
