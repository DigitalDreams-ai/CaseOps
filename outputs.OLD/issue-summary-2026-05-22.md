# CaseOps Issue Summary - 2026-05-22

Generated: 2026-05-22
Last updated: 2026-05-22

## Executive Summary

- **Total issues in scope:** 1
- **Escalated to Engineering (Jira status):** 0 (but 1 escalated during processing)
- **Active issues processed:** 1
- **Engineering handoffs raised during processing:** 1
- **Sandbox-deployed or sandbox-validated:** 0
- **Operational / data / access follow-up, no metadata deploy:** 0

Engineering escalation rule: if the fix requires Apex/code, a Salesforce Flow, an Approval Process, a Validation Rule, or other Engineering-owned automation, stop after diagnosis and provide an Engineering handoff with a simple problem description, potential fix, root cause, affected metadata, evidence, and reproduction details.

Engineering handoffs are organized in `outputs/engineering-escalations/`.
Closed/Resolved archives are organized in `outputs/closed-resolved/`.

## Closed / Resolved (Skipped)

None. HEAL-32826 was in "On Hold" status at sync and processed through the pipeline.

## Issue Rollup

No Support-owned fixes. HEAL-32826 was escalated to Engineering during processing and appears in the "Escalated to Engineering" section below.

## Sandbox Deployments / Validations

None. No Support-owned fixes; no Sandbox deployment. Backfill validation deferred to Engineering team.

## Escalated to Engineering

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-32826 | On Hold | Shopify-to-SF order sync integration | `outputs/engineering-escalations/HEAL-32826.md` | Shopify→SF order sync failed to invoke Patient Agreement flow during 3/18–3/27, leaving several hundred patient accounts missing Informed Consent 2026. 3/27 fix restored forward-looking assignment; backfill approach requires Engineering confirmation. | Identify which SF automation (flow or trigger) failed during 3/18–3/27 and what 3/27 fix changed. Confirm whether "Assign patient agreements" action is safe for batch backfill on affected Production records. |

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
