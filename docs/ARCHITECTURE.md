# CaseOps Architecture

## Overview

CaseOps combines a Flask dashboard, deterministic Python/Jira helpers, Claude Code skills, and Salesforce CLI helpers.

```text
Jira API
  -> jira_sync.py
  -> instance outputs
  -> Flask dashboard
  -> Claude Code pipeline
  -> Salesforce sf CLI
  -> Sandbox validation artifacts
```

## Major Components

| Component | Purpose |
| --- | --- |
| `app.py` | Flask app, APIs, Settings, pipeline launcher, SSE logs, path validation |
| `jira_sync.py` | Jira issue sync and manifest generation |
| `templates/` | Jinja/HTML UI |
| `static/` | CSS, JS, icons |
| `skills/` | Claude Code skills and prompts |
| `scripts/sf_caseops_helper.py` | Deterministic Salesforce helper commands |
| `instance1/outputs/` | Persistent issue artifacts and appdata |
| `instance1/outputs/metadata-cache/` | Persistent read-only Production metadata cache |
| `instance1/outputs/metadata-workspaces/` | Persistent issue workspaces, Sandbox attempts, rollback evidence, confirmed packages |

## Pipeline

| Step | Owner | Purpose |
| --- | --- | --- |
| 1 | Orchestrator | Sync Jira |
| 2 | Orchestrator | Triage by Jira status |
| 3 | Sub-agent | Analyze issue |
| 4 | Orchestrator | Hypothesis and smallest viable fix |
| 5 | Sub-agent | Retrieve relevant Production metadata read-only |
| 6 | Sub-agent | Pinpoint problem artifact and failure point |
| 7 | Orchestrator | Support vs Engineering gate |
| 8 | Orchestrator | Prepare proposed solution |
| 9 | Sub-agent | Deploy/test in allowlisted Sandbox |
| 10 | Sub-agent | Draft customer, internal, and handoff docs |
| 11 | Orchestrator | Dated summary |
| 12 | Orchestrator | Completion report |

Sub-agents run with isolated context and return compact summaries. Detailed evidence is written to files.

## Runtime Storage

Current NAS runtime:

```text
instance1/
  outputs/
    jira/
    investigations/
    step-4-hypothesis/
    internal-notes/
    jira-messages/
    test-reports/
    engineering-escalations/
    closed-resolved/
    pipeline-logs/
    settings/
    org-knowledge/
  metadata-cache/
    production/<org>/<api-version>/
      raw/
      summaries/
  metadata-workspaces/
    <KEY>/
      metadata-workspace.json
      attempt-001/
        baseline-sandbox/
        candidate/
        revert/
      confirmed/
        support-owned/
        engineering-proposal/
```

`outputs/` is persistent appdata. Legacy `.temp/metadata/` is migration-only historical evidence and is not used for new work.

## Salesforce Metadata Rules

Raw Production metadata:

- stored under `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/`
- read-only evidence
- never edited in place

Sandbox attempts:

- stored under `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/`
- each attempt contains `baseline-sandbox/`, `candidate/`, and `revert/`
- failed or abandoned attempts must be reverted before a new attempt starts

Confirmed work:

- copied to `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/support-owned/` or `confirmed/engineering-proposal/`
- still not deployed to Production by CaseOps

## Salesforce Command Rules

CaseOps uses modern `sf` CLI commands only.

Allowed:

- `sf org ...`
- `sf data query ...`
- `sf project retrieve start --metadata ...`
- `sf project retrieve start --source-dir ...`
- `sf project deploy start --source-dir ...`
- `sf project deploy start --metadata-dir ...`

Forbidden for routine CaseOps retrieve/deploy:

- legacy `sfdx force:*`
- `package.xml`
- `--manifest`
- frontdoor or magic-link sessions as API bearer tokens

## Org Knowledge

Org knowledge lives under `outputs/org-knowledge/`. Startup seeds default files and merges required rules without overwriting operator edits.

The index selects topic files by keyword so Claude reads only relevant knowledge. Current seed topics include Salesforce gotchas for fields, layouts, access, deploys, and automation.

## Safety

- Production is read-only.
- Only `CASEOPS_SANDBOX_TARGET_ORG` can receive deploys or writes.
- CaseOps drafts Jira messages but does not post automatically unless explicitly requested.
- CaseOps does not promote changes to Production.
- Settings and token writes are persisted to the active env file or mounted outputs.
