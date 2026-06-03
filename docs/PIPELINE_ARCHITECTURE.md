# CaseOps Pipeline Architecture

The CaseOps pipeline is an orchestrator skill with specialized sub-agents and file-based state.

## Current Architecture

```
UI button or Claude Code invocation
  ↓
jira-salesforce-fix-pipeline skill
  ├─ Step 1-2: Sync and triage
  ├─ Step 3: Delegate to jira-issue-analysis
  ├─ Step 4: Synthesize hypothesis
  ├─ Step 5: Delegate to salesforce-production-metadata-investigation
  ├─ Step 6: Delegate to salesforce-production-metadata-investigation in drilling mode
  ├─ Step 7: Classify Support-owned vs Engineering-owned
  ├─ Step 8: Prepare proposed solution
  ├─ Step 9: Delegate to salesforce-sandbox-deploy-test
  ├─ Step 10: Delegate to jira-response-drafting
  └─ Step 11-12: Dated summary and user report
```

Both Support-owned and Engineering-owned paths can produce Sandbox-validated proposed solutions. CaseOps never deploys to Production.

Pipeline Salesforce work follows the current command contract:

- modern `sf` CLI only
- no legacy `sfdx force:*`
- no routine `package.xml`
- no routine `--manifest`
- frontdoor/magic links only for visual inspection

## Metadata State

Salesforce metadata is separated by lifecycle:

```
${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/      # Read-only Production cache
${CASEOPS_METADATA_WORKSPACES_DIR}/<KEY>/
├── metadata-workspace.json
├── attempt-N/                              # Baseline, candidate, revert
└── confirmed/                              # Passed Support package or Engineering proposal
```

Failed or abandoned Sandbox attempts must be reverted from the captured baseline before another attempt starts.

## File-Based State

```
outputs/
├── jira/manifest.csv
├── closed-resolved/<KEY>.md
├── investigations/<KEY>.md
├── step-4-hypothesis/<KEY>.md
├── test-reports/<KEY>.md
├── internal-notes/<KEY>.md
├── jira-messages/<KEY>.md
├── engineering-escalations/<KEY>.md
└── summaries/
    └── YYYY-MM-DD/
        └── issue-summary-YYYY-MM-DD.md
```

The orchestrator reads compact sub-agent summaries and output file presence. It does not load entire investigation records into context unless a step explicitly requires a narrow excerpt.

## Org Knowledge

The orchestrator receives selected org-knowledge files from `outputs/org-knowledge/`. It should not bulk-read the full directory. Sub-agents receive relevant selected bullets in their prompts because they start with isolated context.
