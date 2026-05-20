# CaseOps Issue Summary - 2026-05-16

Generated: 2026-05-16
Last updated: 2026-05-16

## Executive Summary

- Total issues in scope:
- Escalated to Engineering (Jira status):
- Active issues processed: 30
- Engineering handoffs raised during processing:
- Sandbox-deployed or sandbox-validated:
- Operational / data / access follow-up, no metadata deploy:

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
| HEAL-33628 | Waiting for support | "Send Patient Agreements" SF feature not opening consents for numerous patients | Support-resolvable: portal user profile lacked READ access to Patient_Agreement__c custom object. Fixed by adding READ permissions to profile. Sandbox tests passed. | Yes — standard metadata deploy | Deploy profile update to Production; test end-to-end consent signing with affected accounts (001Rh000010no9eIAA, 001Rh000006rScJIAU, 0015a00003GjtXVAAZ); confirm patients can sign without error |

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox. Do not include issues that are in the Escalated to Engineering section — their sandbox work is recorded in their handoff files.

| Issue | Sandbox | Deploy / Validation | Prod deploy needed? |
| --- | --- | --- | --- |
| HEAL-33628 | 10xhealth-sean | Added READ permissions to Patient_Agreement__c and Patient_Agreement_Configuration__c on "Portal - Authenticated User" profile. Deploy ID: 0AfEa00000Zr1oDKAR. All tests passed. | Yes |

## Escalated to Engineering

All issues escalated to Engineering, whether pre-escalated in Jira at sync time or escalated during pipeline processing. These issues must not appear in the Issue Rollup or Sandbox Deployments sections.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-33618 | In Progress | Case object, Record-Triggered Flow | `outputs/engineering-escalations/HEAL-33618.md` | No custom Date/Time field captures when a Case is escalated from Tier 1 to Tier 2; standard `IsEscalated` is boolean only | Create `Case.Escalation_DateTime__c` field, build Record-Triggered Flow to stamp on escalation, create report with elapsed-time formulas |

## Artifact Index

- Jira summaries: `outputs/jira/summary/`
- Investigations: `outputs/investigations/`
- Engineering handoffs: `outputs/engineering-escalations/`
- Closed/Resolved archives: `outputs/closed-resolved/`
- Internal notes: `outputs/internal-notes/`
- Jira message drafts: `outputs/jira-messages/`
- Test reports: `outputs/test-reports/`

## Summary Maintenance

Create or update this file for the current day on every pipeline run:

```text
outputs/issue-summary-YYYY-MM-DD.md
```

Update whenever an issue is processed, escalated, skipped, deployed to Sandbox, tested, or closed out.
