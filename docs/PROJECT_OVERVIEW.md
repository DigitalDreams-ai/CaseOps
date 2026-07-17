# CaseOps Project Overview

CaseOps is a Dockerized Flask web app for Jira-to-Salesforce support work. It syncs Jira issues, runs a Claude Code investigation pipeline, validates candidate fixes in a configured Salesforce Sandbox, and drafts internal notes or customer-facing Jira replies.

CaseOps does not deploy to Salesforce Production. Production access is read-only.

## Runtime Model

CaseOps is intended to run from a published Docker image:

```text
ghcr.io/digitaldreams-ai/caseops:0.1.62
```

The container uses:

- `/data` for persistent runtime data,
- `/data/outputs` for Jira sync data and generated artifacts,
- `/data/.env` for Settings-managed configuration and tokens,
- `/tmp/caseops` for temporary files.

The default web URL is:

```text
http://localhost:5350
```

## What CaseOps Produces

Issue artifacts are stored in persistent appdata:

- `jira/` - raw Jira issue bundles, markdown summaries, manifest.
- `investigations/` - issue understanding and diagnosis record.
- `hypothesis/` - problem hypothesis and smallest viable fix.
- `internal-notes/` - internal diagnosis and operational notes.
- `jira-messages/` - customer-facing draft responses.
- `test-reports/` - Sandbox validation results.
- `engineering-escalations/` - Engineering handoffs when required.
- `pipeline-logs/` - streamed run logs.
- `pipeline-state/` - resume plans, transition history, loop counts, and gate diagnostics.
- `eval-reports/` - timestamped output-quality reports, append-only history, and the latest summary.
- `generated-files/` - issue-specific generated reports and files.
- `issue-clusters/` - public-safe similar-issue summaries, deterministic cluster state, local corrections, adjudication records, and safety-validation records.
- `settings/` - persistent Settings overrides, including canned messages.
- `org-knowledge/` - reusable Salesforce knowledge selected by topic.
- `metadata-cache/` - read-only Production metadata retrievals.
- `metadata-workspaces/` - Sandbox attempts, rollback evidence, and confirmed packages.

## Pipeline Summary

CaseOps runs a 12-step pipeline:

| Step | Owner | Purpose |
| --- | --- | --- |
| 1 | Orchestrator | Sync Jira |
| 2 | Orchestrator | Triage by Jira status |
| 2B | Orchestrator | Look up similar issues and add safe cluster context |
| 3 | Sub-agent | Analyze issue |
| 4 | Orchestrator | Create hypothesis and smallest viable fix |
| 5 | Sub-agent | Retrieve relevant Production metadata read-only |
| 6 | Sub-agent | Identify exact problem location |
| 7 | Orchestrator | Decide Support-resolvable vs Engineering-owned |
| 8 | Orchestrator | Prepare proposed solution |
| 9 | Sub-agent | Deploy and test in allowlisted Sandbox |
| 10 | Sub-agent | Draft internal notes, Jira message, and handoff |
| 11 | Orchestrator | Generate summary |
| 12 | Orchestrator | Return action report |

Engineering handoffs should include evidence, not just a hypothesis.

## Pipeline Hardening

`pipeline_gates.py` validates Step 4 hypotheses and Step 7 Engineering handoffs before downstream work can count as complete. `pipeline_fsm.py` records explicit step markers, rejects illegal transitions, and moves loop-cap violations on hold for operator review.

`CASEOPS_ANTHROPIC_MODEL` is required and must contain a versioned Claude model id. `model_config.py` provides the shared validator used by the app and evaluation CLI. CaseOps stamps the id into pipeline state and evaluation reports. A model change is logged and triggers an immediate evaluation when scheduled evaluations are enabled.

`output_evals.py` evaluates recent Jira messages, internal notes, hypotheses, and Engineering handoffs. Deterministic checks always run; optional model grading uses the pinned model. Configure the scheduler and sample using `CASEOPS_OUTPUT_EVALS_ENABLED`, `CASEOPS_OUTPUT_EVALS_INTERVAL_MINUTES`, `CASEOPS_EVAL_LOOKBACK_DAYS`, `CASEOPS_EVAL_MAX_ARTIFACTS`, `CASEOPS_EVAL_LLM_ENABLED`, and `CASEOPS_EVAL_ALERT_THRESHOLD`.

## Similar Issues

CaseOps automatically creates current-user-only similarity clusters from synced Jira issues and existing CaseOps artifacts. Closed and resolved issues are included as context, even though they are excluded from normal active queue processing.

The first implementation is intentionally conservative:

- deterministic fingerprints and evidence terms identify candidates,
- the issue detail page separates open matches from closed/resolved matches,
- the current issue is not shown as a match to itself,
- public-safe cluster summaries are written under `/data/outputs/issue-clusters`,
- operator corrections are stored locally in appdata,
- pipeline reuse and delta validation remain gated by adjudication and Salesforce validation.

## Salesforce Command Contract

CaseOps uses modern `sf` CLI commands for Salesforce work.

Allowed command families:

- `sf org ...`
- `sf data query ...`
- `sf project retrieve start --metadata ...`
- `sf project retrieve start --source-dir ...`
- `sf project deploy start --source-dir ...`
- `sf project deploy start --metadata-dir ...`

Forbidden for routine CaseOps retrieve/deploy:

- legacy `sfdx force:*`,
- `package.xml`,
- `--manifest`,
- frontdoor or magic-link session IDs as API tokens.

## Related Docs

- [CaseOps Quickstart](CASEOPS_QUICKSTART.md)
- [Tester Guide](TESTER_GUIDE.md)
- [User Guide](USER_GUIDE.md)
- [Docker Setup](DOCKER_SETUP.md)
