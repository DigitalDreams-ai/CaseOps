# CaseOps Project Overview

CaseOps is a Flask-based operations tool for Jira-to-Salesforce support work. It syncs assigned Jira issues, runs a Claude Code pipeline to investigate Salesforce problems, validates proposed fixes in a single allowlisted Sandbox, and drafts customer-facing and internal handoff notes.

CaseOps does not deploy to Production. Production Salesforce access is read-only.

## Current Deployment

The active pilot deployment runs in Docker on the NAS:

- SSH: `ssh docker@10.0.1.10`
- Stack/code/env: `/volume1/docker/stacks/caseops`
- Appdata reference: `/volume1/docker/appdata/caseops`
- Container: `caseops`
- Host URL: `http://10.0.1.10:5350`
- Container URL: `http://127.0.0.1:5000`

The NAS deployment bind-mounts source files for predictable pilot updates:

- `app.py`
- `templates/`
- `static/`
- `skills/`
- `scripts/`
- `instance1/outputs/`
- `.env.jira.nas` as `/app/.env.jira`

## What CaseOps Produces

Issue artifacts are stored under the active outputs directory, currently `instance1/outputs/`:

- `jira/` - raw Jira issue bundles, markdown summaries, manifest.
- `investigations/` - issue understanding and diagnosis record.
- `step-4-hypothesis/` - problem hypothesis and smallest viable fix.
- `internal-notes/` - internal diagnosis and operational notes.
- `jira-messages/` - customer-facing draft responses.
- `test-reports/` - Sandbox validation results.
- `engineering-escalations/` - Engineering handoffs when required.
- `pipeline-logs/` - streamed run logs.
- `settings/` - persistent Settings overrides, including canned messages.
- `org-knowledge/` - reusable Salesforce knowledge selected by topic.

Salesforce metadata workspaces are currently under `instance1/.temp/metadata/`.

## Pipeline Summary

CaseOps runs a 12-step pipeline:

| Step | Owner | Purpose |
| --- | --- | --- |
| 1 | Orchestrator | Sync Jira |
| 2 | Orchestrator | Triage by Jira status |
| 3 | Sub-agent | Analyze issue |
| 4 | Orchestrator | Create hypothesis and smallest viable fix |
| 5 | Sub-agent | Retrieve relevant Production metadata read-only |
| 6 | Sub-agent | Identify exact problem location |
| 7 | Orchestrator | Decide Support-resolvable vs Engineering-owned |
| 8 | Orchestrator | Prepare proposed solution |
| 9 | Sub-agent | Deploy and test in allowlisted Sandbox |
| 10 | Sub-agent | Draft internal notes, Jira message, and handoff |
| 11 | Orchestrator | Generate dated summary |
| 12 | Orchestrator | Return action report |

Both Support-resolvable and Engineering-escalation paths run Sandbox validation when a proposed solution exists. Engineering handoffs should include evidence, not just a hypothesis.

## Salesforce Command Contract

CaseOps uses modern `sf` CLI commands only for Salesforce CLI work.

Allowed command families:

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
- frontdoor or magic-link session IDs as API tokens

## Related Docs

- [User Guide](USER_GUIDE.md)
- [Architecture](ARCHITECTURE.md)
- [Docker Setup](DOCKER_SETUP.md)
- [Technical Overview](TECHNICAL_OVERVIEW.md)
