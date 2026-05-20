# CaseOps Issue Summary - 2026-05-18

Generated: 2026-05-18
Last updated: 2026-05-18

## Executive Summary

- Total issues in scope: 7 (Lab Order-related issues)
- Processing status: 1 of 7 complete (HEAL-32826)
- Escalated to Engineering during processing: 1 (HEAL-32826)
- Active issues pending: 6 (HEAL-33316, HEAL-33391, HEAL-33439, HEAL-33505, HEAL-33569, HEAL-33616)

## Closed / Resolved (Skipped)

None in this batch.

## Escalated to Engineering

| Issue | Jira Status | Component | Handoff File | Problem | Potential Fix |
| --- | --- | --- | --- | --- | --- |
| HEAL-32826 | On Hold | Account creation flow / Shopify→SF integration | outputs/engineering-escalations/HEAL-32826.md | Sync flow from Shopify to Salesforce failed 3/18–3/27/2026, leaving ~300+ Account records without "Informed Consent 2026" populated. Fix deployed 3/27 restored sync for new orders. Consent removal post-Chrono sync status unclear. | Audit Account/Opportunity creation flow/Apex; confirm 3/27 fix permanence; clarify/implement consent removal workflow; validate and execute bulk backfill via "Assign patient agreements" |

## Artifact Index

- Jira summaries: `outputs/jira/summary/`
- Investigations: `outputs/investigations/`
- Engineering handoffs: `outputs/engineering-escalations/`
- Jira message drafts: `outputs/jira-responses/`
