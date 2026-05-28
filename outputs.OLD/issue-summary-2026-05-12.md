# CaseOps2 Issue Summary - 2026-05-12

Generated: 2026-05-12
Last updated: 2026-05-12

## Executive Summary

- Total issues in scope: 1
- Escalated to Engineering (Jira status): 0
- Active issues processed: 1
- Engineering handoffs raised during processing: 0
- Sandbox-deployed or sandbox-validated: 0 (permission set assignment — no deploy required)
- Operational / data / access follow-up, no metadata deploy: 1

Engineering escalation rule: if the fix requires Apex/code, a Salesforce Flow, an Approval Process, a Validation Rule, or other Engineering-owned automation, stop after diagnosis and provide an Engineering handoff with a simple problem description, potential fix, root cause, affected metadata, evidence, and reproduction details.

Engineering handoffs are organized in `outputs/engineering-escalations/`.
Closed/Resolved archives are organized in `outputs/closed-resolved/`.

## Closed / Resolved (Skipped)

Issues filtered at triage. No pipeline processing performed.

| Issue | Jira Status | Summary |
| --- | --- | --- |
| — | — | None this run |

## Issue Rollup

Active issues that entered the pipeline. Issues with Jira status "Escalated to Engineering" are listed separately in the Escalated to Engineering section below.

| Issue | Jira Status At Sync | Summary | Disposition | Next Step |
| --- | --- | --- | --- | --- |
| HEAL-33569 | Waiting for customer | SF - Access to Generate Supplement Order | Support-resolvable. Root cause confirmed: missing Order Create permission (`Order_Processor` PSA not assigned to msallo@10xhealthsystem.com). Fix ready to execute. | 1. Verify `Order_Processor` also grants `OrderItem` Create/Edit. 2. Assign PSA to msallo@10xhealthsystem.com in Production. 3. Test flow. 4. Send Jira message. 5. Engineering follow-up: add fault connectors to both flows. |

## Sandbox Deployments / Validations

Support-owned fixes validated in Sandbox.

| Issue | Sandbox | Deploy / Validation |
| --- | --- | --- |
| HEAL-33569 | N/A | Permission set assignment applied directly in Production — no Sandbox deployment required. |

## Escalated to Engineering

All issues escalated to Engineering, whether pre-escalated in Jira at sync time or escalated during pipeline processing.

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| — | — | — | — | None this run | — |

## Artifact Index

- Jira summaries: `outputs/jira/summary/`
- Investigations: `outputs/investigations/`
- Engineering handoffs: `outputs/engineering-escalations/`
- Closed/Resolved archives: `outputs/closed-resolved/`
- Internal notes: `outputs/internal-notes/`
- Jira message drafts: `outputs/jira-messages/`
- Test reports: `outputs/test-reports/`

### This Run (2026-05-12)

| Artifact | Path |
| --- | --- |
| Jira summary | `outputs/jira/summary/HEAL-33569.md` |
| Investigation record | `outputs/investigations/HEAL-33569.md` |
| Internal notes | `outputs/internal-notes/HEAL-33569.md` |
| Jira message draft | `outputs/jira-messages/HEAL-33569.md` |
