---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process and work assigned issues, diagnose Salesforce problems, investigate Production metadata, determine whether to escalate to Engineering, implement Support-owned fixes, **always** deploy and test only in the single Sandbox named by CASEOPS_SANDBOX_TARGET_ORG in .env.jira, iterate if needed, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
compatibility: CaseOps repo root, `.env.jira` (Jira credentials, JIRA_BASE_URL, CASEOPS_DEFAULT_ASSIGNEE, CASEOPS_SANDBOX_TARGET_ORG), Python 3 for `jira_sync.py`; Salesforce CLI optional for deploy/test sub-path.
---

# Jira Salesforce Fix Pipeline

## Authoritative workflow

After this skill activates, read **`references/workflow.md`** end-to-end. It is the **single source of truth** for numbered steps, triage rules, iteration, and dated-summary content.

Supporting references (load when doing the step they support):

- **`references/sub-agent-prompts.md`** — copy-paste Agent-tool prompts for Steps **3, 5, 8, and 9**.
- **`references/safety-policy.md`** — Production read-only, Sandbox allowlist, Jira and data rules.
- **`references/quality-checklist.md`** — gates before you declare a run complete.

## Use This Skill When

- The user wants Jira issues taken through Salesforce diagnosis, implementation, Sandbox deployment, testing, and response drafting.
- The user provides a Jira issue key, Jira URL, exported Jira issue data, or asks to retrieve Jira issues.
- The work requires understanding a Salesforce problem before making metadata or code changes.
- The work may need an Engineering escalation handoff instead of an implementation.

## Do Not Use This Skill When

- The user only wants a general explanation.
- The task does not involve Jira or Salesforce.
- The user asks for direct Production changes.
- Required Jira or Salesforce access is unavailable and the user has not provided issue or metadata exports.

## Required Inputs

- `.env.jira` configured with valid Jira credentials (`JIRA_EMAIL` + `JIRA_API_TOKEN`, or `JIRA_BEARER_TOKEN`, or `JIRA_AUTH_HEADER_COMMAND`).
- `JIRA_BASE_URL` and `CASEOPS_DEFAULT_ASSIGNEE` set in `.env.jira`.
- Read **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira` before deployment. That is the **only** org that may receive deploys or writes on the Support-resolvable path (see `salesforce-sandbox-deploy-test` and `references/safety-policy.md`).
- Production org access or exported Production metadata for read-only investigation.
- Acceptance criteria or enough issue detail to infer testable behavior.

## Agent Architecture

This pipeline is an **orchestrator**. Steps **1, 2, 4, 6, 7, 10, and 11** run in the orchestrator context. Steps **3, 5, 8, and 9** are delegated to sub-agents via the Agent tool using the templates in **`references/sub-agent-prompts.md`**.

**Why sub-agents:** Each sub-agent runs in a clean context window. The orchestrator keeps only the compact summary (about 300–500 tokens) each sub-agent returns — not their full working context.

**Sub-agent discipline:**

- Spawn **one** sub-agent per step per issue. Do not batch multiple issues into one Agent call.
- Every sub-agent prompt must be fully self-contained (issue key, paths, task, return format).
- Sub-agents write artifacts under `outputs/`. The orchestrator does **not** load full output files into its own context — only the returned summary.

## Available Scripts

- **`jira_sync.py`** (repo root): Sync Jira into `outputs/jira/` (raw JSON, summaries, `manifest.csv`). Run with `--env-file .env.jira`; add `--incremental` when only recent changes matter.

## Assets

- `assets/investigation-record-template.md` — working record per issue.
- `assets/engineering-handoff-template.md` — Engineering escalations (includes Engineering Message section).
- `assets/internal-notes-template.md` — internal notes.
- `assets/jira-message-template.md` — Jira response draft.
- `assets/issue-summary-template.md` — dated rollup.
- `assets/test-report-template.md` — Sandbox test report.
- `assets/closed-resolved-log-template.md` — Closed/Resolved archive at triage.
