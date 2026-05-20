# CaseOps Issue Summary - 2026-05-14

Generated: 2026-05-14
Last updated: 2026-05-14

## Executive Summary

- Total issues in scope: 4
- Escalated to Engineering (Jira status): 0 (pre-existing)
- Active issues processed: 4
- Engineering handoffs raised during processing: 2
- Sandbox-deployed or sandbox-validated: 1
- Operational / data / access follow-up, no metadata deploy: 2

## Closed / Resolved (Skipped)

Issues filtered at triage. No pipeline processing performed.

| Issue | Jira Status | Summary |
| --- | --- | --- |

## Issue Rollup

Active issues that entered the pipeline. Issues with Jira status "Escalated to Engineering" are listed separately in the Escalated to Engineering section below.

| Issue | Jira Status At Sync | Summary | Disposition | Prod deploy? (Gearset / No / N/A) | Next Step |
| --- | --- | --- | --- | --- | --- |
| HEAL-33150 | In Progress | Cx Case Record Response | Support-resolvable: workflow/routing configuration recommendation; no Apex/code/metadata change required | No | Communicate Email-to-Case routing requirement to CX team; monitor for additional threading examples with reply-to-case verification |
| HEAL-33645 | In Progress | Kershon S needs permissions in SF | Support-resolvable: Data-only fix (PermissionSetAssignment record); Create_Credit_Card PS already exists in Production. Sandbox validation: PASS (Account, Opportunity, Credit Card create/edit all confirmed). | No | Create PermissionSetAssignment in Production for Kershon Stephens (Kstephens@10xhealthsystem.com) assigning Create_Credit_Card PS (0PSRh0000006cllOAA). |

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox.

| Issue | Sandbox | Deploy / Validation |
| --- | --- | --- |
| HEAL-33645 | 10xhealth-sean | **PASS** — PermissionSetAssignment created (0PaEa00000aw4IrKAI) assigning Create_Credit_Card PS to test user. All acceptance criteria validated: Account create (001Ea00001TSk57IAD), Opportunity create (006Ea00000ckMngIAE), Credit_Card__c create/edit (a09Ea00000Vw913IAB with full field access). No Production metadata deploy needed. |

## Escalated to Engineering

All issues escalated to Engineering.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-33623 | Waiting for support | MyWellnessPortal integration (Named Credential, external endpoint) | outputs/engineering-escalations/HEAL-33623.md | External MyWellnessPortal service returns network error when patient clicks consent form link. Portal user permissions and Salesforce configuration correct; root cause in external service or Named Credential configuration. | Verify MyWellnessPortal Named Credential (auth, endpoint, timeout) in org Setup; test external service connectivity; check debug logs for HTTP response; coordinate with vendor or update endpoint config. |
| HEAL-33633 | Waiting for customer | Wellvi integration (Flow/Apex) | outputs/engineering-escalations/HEAL-33633.md | Order address fields (BillingStreet, BillingCity, BillingState, BillingPostalCode) not being extracted and serialized to Wellvi API request payload; HTTP 400 error with missing address fields despite data existing in Order record | Review and repair Wellvi integration code (Flow or Apex) to ensure proper field mapping and serialization of Order address fields; add null-checks before API callout; test with Order 801Ql00000zolrtIAA |

## Artifact Index

- Jira summaries: outputs/jira/summary/
- Investigations: outputs/investigations/
- Engineering handoffs: outputs/engineering-escalations/
- Internal notes: outputs/internal-notes/
- Jira message drafts: outputs/jira-messages/
