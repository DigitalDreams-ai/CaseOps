# CaseOps Agents And Skills

CaseOps uses Claude Code skills. The authoritative skill files stay under `skills/` and must not be moved into `docs/`.

## Skills

| Skill | Purpose |
| --- | --- |
| `jira-salesforce-fix-pipeline` | 12-step orchestrator |
| `jira-issue-analysis` | Step 3 issue understanding |
| `salesforce-production-metadata-investigation` | Steps 5 and 6 Production read-only metadata work |
| `salesforce-sandbox-deploy-test` | Step 9 Sandbox deploy/test/revert |
| `jira-response-drafting` | Step 10 customer/internal/handoff drafting |

## Orchestrator Pattern

The pipeline orchestrator:

- runs Steps 1, 2, 4, 7, 8, 11, and 12 in the main context
- delegates Steps 3, 5, 6, 9, and 10 to sub-agents
- passes selected org-knowledge bullets into sub-agent prompts
- keeps sub-agent results compact
- writes detailed evidence to files

## Context Management

CaseOps follows progressive disclosure:

- do not bulk-read `outputs/org-knowledge/`
- do not load full raw metadata trees into the orchestrator
- use helper scripts for repeated Salesforce mechanics
- pass concise findings between steps
- keep detailed artifacts in files

## Salesforce Rules For Agents

- Production is read-only.
- Sandbox writes only target `CASEOPS_SANDBOX_TARGET_ORG`.
- Use modern `sf` CLI only.
- Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine retrieve/deploy.
- Do not use frontdoor/magic-link session IDs for API, SOQL, retrieve, deploy, or tests.
- Use `scripts/sf_caseops_helper.py` before repeated ad hoc custom field, layout, FLS, or deploy experiments.

## Step Progress

Agents must emit progress markers:

```text
STEP_3 ISSUE-12345
STEP_4 ISSUE-12345
...
```

The dashboard parses these markers for real-time issue-card progress.

## Output Discipline

Sub-agents write to issue-specific paths under `outputs/` and metadata workspace variables. They must not create root-level `temp*`, `retrieve*`, `deploy*`, or `metadata*` directories.
