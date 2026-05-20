# CaseOps Issue Summary - 2026-05-15

Generated: 2026-05-15
Last updated: 2026-05-15

## Executive Summary

- Total issues in scope: 3
- Escalated to Engineering (Jira status): 0 (escalated during processing)
- Active issues processed: 3
- Engineering handoffs raised during processing: 2
- Sandbox-deployed or sandbox-validated: 1
- Operational / data / access follow-up, no metadata deploy: 0

Engineering escalation rule: if the fix requires Apex/code, a Salesforce Flow, an Approval Process, a Validation Rule, or other Engineering-owned automation, stop after diagnosis and provide an Engineering handoff with a simple problem description, potential fix, root cause, affected metadata, evidence, and reproduction details.

Engineering handoffs are organized in `outputs/engineering-escalations/`.
Closed/Resolved archives are organized in `outputs/closed-resolved/`.

## Closed / Resolved (Skipped)

Issues filtered at triage. No pipeline processing performed.

| Issue | Jira Status | Summary |
| --- | --- | --- |

## Issue Rollup

Active issues that entered the pipeline. Issues with Jira status "Escalated to Engineering" are listed separately in the Escalated to Engineering section below — do not include them here.

| Issue | Jira Status At Sync | Summary | Disposition | Prod deploy? (Gearset / No / N/A) | Next Step |
| --- | --- | --- | --- | --- | --- |
| HEAL-33659 | In Progress | Cx Case function Additions (add Supplement Inquiry picklist to Case) | Fixed in Sandbox | Yes — Gearset | Deploy custom field + layout to Production via Gearset |

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox. Do not include issues that are in the Escalated to Engineering section — their sandbox work is recorded in their handoff files.

| Issue | Sandbox | Deploy / Validation | Prod deploy needed? |
| --- | --- | --- | --- |
| HEAL-33659 | 10xhealth-sean | Custom picklist field Supplement_Inquiry__c created with 44 product values; added to Case-Customer Experience layout; all 44 values verified; field visible and functional for Customer Support | Yes — Gearset |

## Escalated to Engineering

All issues escalated to Engineering, whether pre-escalated in Jira at sync time or escalated during pipeline processing. These issues must not appear in the Issue Rollup or Sandbox Deployments sections.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-33605 | In Progress | SMS template access (tdc_tsw__Message_Template__c), user permissions, org-wide defaults | `outputs/engineering-escalations/HEAL-33605.md` | Amy Stolze has zero access to email and SMS templates despite having identical permission sets to Veronica Berenguer. Permission set assignment hypothesis disproven. Root cause likely in user configuration, org-wide sharing rules, custom permissions, or SMS app code logic. | Investigate Amy's user record (status, IP restrictions, login method, MFA), org-wide defaults and sharing rules for template objects, custom permissions/settings, tdc_tsw__Message_Template__c folder sharing, SMS app custom code/Apex for access control logic. |
| HEAL-33647 | Waiting for support | Shopify-Salesforce integration (Custom Apex `Patient_Patient` or external connector) | `outputs/engineering-escalations/HEAL-33647.md` | Customer shipping address overwritten with billing address during Shopify sync; delivered to wrong address. Salesforce flows verified correct; root cause in external integration layer. | Audit custom Apex `Patient_Patient` action or external Shopify connector field mappings. Fix to prevent address swap. Scope via RCA query (isolated vs systemic). |

## Artifact Index

- Jira summaries: `outputs/jira/summary/`
  - HEAL-33605: `outputs/jira/summary/HEAL-33605.md`
  - HEAL-33647: `outputs/jira/summary/HEAL-33647.md`
  - HEAL-33659: `outputs/jira/summary/HEAL-33659.md`
- Investigations: `outputs/investigations/`
  - HEAL-33605: `outputs/investigations/HEAL-33605.md`
  - HEAL-33647: `outputs/investigations/HEAL-33647.md`
  - HEAL-33659: `outputs/investigations/HEAL-33659.md`
- Engineering handoffs: `outputs/engineering-escalations/`
  - HEAL-33605: `outputs/engineering-escalations/HEAL-33605.md`
  - HEAL-33647: `outputs/engineering-escalations/HEAL-33647.md`
- Closed/Resolved archives: `outputs/closed-resolved/` (none for this run)
- Internal notes: `outputs/internal-notes/`
  - HEAL-33605: `outputs/internal-notes/HEAL-33605.md`
  - HEAL-33647: `outputs/internal-notes/HEAL-33647.md`
  - HEAL-33659: `outputs/internal-notes/HEAL-33659.md`
- Jira message drafts: `outputs/jira-messages/`
  - HEAL-33605: `outputs/jira-messages/HEAL-33605.md`
  - HEAL-33647: `outputs/jira-messages/HEAL-33647.md`
  - HEAL-33659: `outputs/jira-messages/HEAL-33659.md`
- Test reports: `outputs/test-reports/`
  - HEAL-33659: `outputs/test-reports/HEAL-33659.md`

## Summary Maintenance

This summary covers the pipeline runs completed on **2026-05-15**.

**Run Details:**
- Issues processed: 3 (HEAL-33605, HEAL-33647, HEAL-33659)
- Analysis paths: 
  - HEAL-33605: Investigation (Step 3) → Problem hypothesis (Step 4) → Production metadata audit (Step 5) → Engineering escalation gate (Step 6) → Engineering handoff (Step 9)
  - HEAL-33647: Investigation (Step 3) → Problem hypothesis (Step 4) → Production metadata audit (Step 5) → Engineering escalation gate (Step 6) → Engineering handoff (Step 9)
  - HEAL-33659: Investigation (Step 3) → Problem hypothesis (Step 4) → Production metadata audit (Step 5) → Support-resolvable gate (Step 6) → Implement (Step 7) → Deploy/test in Sandbox (Step 8) → Draft (Step 9)
- Support-owned fixes: 1 (HEAL-33659, deployed to Sandbox)
- Engineering escalations: 2 (HEAL-33605, HEAL-33647)

**Next Steps:**
- **HEAL-33605**: Post Jira message draft from `outputs/jira-messages/HEAL-33605.md`; route Engineering handoff `outputs/engineering-escalations/HEAL-33605.md` to Engineering team for investigation of user record, org-wide defaults, sharing rules, and SMS app custom code
- **HEAL-33647**: Engineering team reviews handoff in `outputs/engineering-escalations/HEAL-33647.md`; audits Shopify connector and custom Apex `Patient_Patient` action
- **HEAL-33659**: Deploy custom field and layout to Production via Gearset from Sandbox (10xhealth-sean); post customer response from `outputs/jira-messages/HEAL-33659.md`
