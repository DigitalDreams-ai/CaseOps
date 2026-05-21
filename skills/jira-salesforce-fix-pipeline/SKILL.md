---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process and work assigned issues, diagnose Salesforce problems, investigate Production metadata, determine whether to escalate to Engineering, implement Support-owned fixes, **always** deploy and test only in the single Sandbox named by CASEOPS_SANDBOX_TARGET_ORG in .env.jira, iterate if needed, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
compatibility: CaseOps repo root, `.env.jira` (Jira credentials, JIRA_BASE_URL, CASEOPS_DEFAULT_ASSIGNEE, CASEOPS_SANDBOX_TARGET_ORG), Python 3 for `jira_sync.py`; Salesforce CLI optional for deploy/test sub-path.
---

# Jira Salesforce Fix Pipeline

## Authoritative workflow

After this skill activates, read **`references/workflow.md`** end-to-end. It is the **single source of truth** for numbered steps, triage rules, iteration, and dated-summary content.

Supporting references (load when doing the step they support):

- **`references/sub-agent-prompts.md`** — copy-paste Agent-tool prompts for Steps **3, 5, 6, 9, and 10**.
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

This pipeline is an **orchestrator**. Steps **1, 2, 4, 7, 8, 11, and 12** run in the orchestrator context. Steps **3, 5, 6, 9, and 10** are delegated to sub-agents via the Agent tool using the templates in **`references/sub-agent-prompts.md`**.

**Why sub-agents:** Each sub-agent runs in a clean context window. The orchestrator keeps only the compact summary (about 300–500 tokens) each sub-agent returns — not their full working context.

**Sub-agent discipline:**

- Spawn **one** sub-agent per step per issue. Do not batch multiple issues into one Agent call.
- Every sub-agent prompt must be fully self-contained (issue key, paths, task, return format).
- Sub-agents write artifacts under `outputs/`. The orchestrator does **not** load full output files into its own context — only the returned summary.

**Loop Control:** See **`references/orchestration-loop-controller.md`** for detailed pseudocode, loop-back conditions, blocker handling, and progress tracking logic. The loop processes issues sequentially (Steps 3–11), handles Step 5/6 metadata discovery, Step 8/9 hypothesis refinement, and escalation branching.

## Available Scripts

- **`jira_sync.py`** (repo root): Sync Jira into `outputs/jira/` (raw JSON, summaries, `manifest.csv`). Run with `--env-file .env.jira`; add `--incremental` when only recent changes matter.

## How to Run This Pipeline (Full Steps 1–12 Orchestration)

This skill orchestrates the complete pipeline from issue sync through summary generation. No Python prerequisite is required; the skill handles Steps 1–2 internally via Bash calls.

**CRITICAL: Step Progress Tracking**

Throughout Steps 1–12, you MUST emit step progress lines to stdout in the format `STEP_N identifier` (e.g., `STEP_3 HEAL-33753`). These lines are parsed by the CaseOps GUI in real-time to update the pipeline progress indicator. Without these explicit output lines, the progress indicator will not display.

### Operator Setup

Before running:
1. **Ensure `.env.jira` is configured** with Jira credentials, Salesforce orgs, and URLs.
2. **Verify `CASEOPS_SANDBOX_TARGET_ORG`** is set in `.env.jira` (e.g., `10xhealth-sean`). This is the **only** org that may receive Support-path deploys (Step 8–9).
3. **Python 3** and **sf CLI** (optional) are available on the system.

### Execution Flow

**Step 1 — Sync from Jira (Orchestrator)**

**Emit to stdout:** `STEP_1 __sync__`

```bash
python jira_sync.py --env-file .env.jira
```

- Fetches all issues assigned to `CASEOPS_DEFAULT_ASSIGNEE` from Jira.
- Outputs:
  - `outputs/jira/raw/<KEY>.json` — full issue bundles
  - `outputs/jira/summary/<KEY>.md` — lean markdown summaries
  - `outputs/jira/manifest.csv` — index of all keys and statuses

If sync fails (credentials, network): STOP and fix `.env.jira` or network, then retry.

**Step 2 — Triage and Route (Orchestrator)**

**Emit to stdout:** `STEP_2 __triage__`

Read `outputs/jira/manifest.csv` and classify every issue:

| Condition | Action |
|-----------|--------|
| Status is `Closed`, `Resolved`, or `Canceled` | Archive to `outputs/closed-resolved/<KEY>.md`. **Stop for this key.** |
| Status is `Escalated to Engineering` | Archive to `outputs/engineering-escalations/<KEY>.md`. **Stop for this key.** |
| All other statuses | Add to active processing list. Process through Steps 3–11. |

Create progress tracking file: `outputs/pipeline-logs/<RUN_DATE>.log`

**Step 3 — Analyze issue (Sub-agent)**

For each active issue:
1. **Emit to stdout:** `STEP_3 <ISSUE_KEY>` (replace <ISSUE_KEY> with the actual key, e.g., `STEP_3 HEAL-33753`)
2. Spawn a sub-agent via the Agent tool using the **Step 3 prompt** from `references/sub-agent-prompts.md`. Retain only the ~300-token summary returned.

**Step 4 — Synthesize hypothesis (Orchestrator)**

For each active issue:
1. **Emit to stdout:** `STEP_4 <ISSUE_KEY>`
2. From Step 3 summary, synthesize root cause (one sentence) and smallest viable fix. Document in `outputs/step-4-hypothesis/<KEY>.md` using `assets/step-4-problem-hypothesis-template.md`.

**Step 5 — Retrieve metadata (Sub-agent)**

For each active issue:
1. **Emit to stdout:** `STEP_5 <ISSUE_KEY>`
2. Spawn salesforce-production-metadata-investigation sub-agent using **Step 5 prompt** from `references/sub-agent-prompts.md`. Pass Step 4 hypothesis. Retain summary only.

**Step 6 — Identify problem location (Sub-agent)**

For each active issue:
1. **Emit to stdout:** `STEP_6 <ISSUE_KEY>`
2. Spawn salesforce-production-metadata-investigation sub-agent (drilling mode) using **Step 6 prompt** from `references/sub-agent-prompts.md`. Identify exact artifact, type, location, failure point. Retain summary only.

**Step 7 — Escalation gate (Orchestrator)**

For each active issue:
1. **Emit to stdout:** `STEP_7 <ISSUE_KEY>`
2. Using Step 6 problem location, classify:

- **Support-resolvable:** Proceed to Step 8.
- **Engineering-required:** Create `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md`. Skip Steps 8–9, proceed to Step 10.

Log decision in `outputs/pipeline-logs/<RUN_DATE>.log`.

**Step 8 — Implement (Orchestrator)**

For Support-resolvable issues:
1. **Emit to stdout:** `STEP_8 <ISSUE_KEY>`
2. Make the fix in Sandbox only (see Step 9 allowlist check). Use Salesforce CLI, web UI, or declarative tools. Never touch Production. Document changed files.

**Step 9 — Deploy and test (Sub-agent)**

**Before spawning:** Read `CASEOPS_SANDBOX_TARGET_ORG` from `.env.jira`. If missing or empty, STOP.

For each Support-resolvable issue:
1. **Emit to stdout:** `STEP_9 <ISSUE_KEY>`
2. Spawn salesforce-sandbox-deploy-test sub-agent using **Step 9 prompt** from `references/sub-agent-prompts.md`. Pass the allowlisted Sandbox org value.

- **On Pass:** Proceed to Step 10.
- **On Fail:** Revise Step 4 hypothesis, loop back to Step 5–6 if more metadata is needed, re-implement Step 8, re-run Step 9. Record iterations in `outputs/investigations/<KEY>.md`.

**Step 10 — Draft messages (Sub-agent)**

For each active issue:
1. **Emit to stdout:** `STEP_10 <ISSUE_KEY>`
2. Spawn jira-response-drafting sub-agent using **Step 10 prompt** from `references/sub-agent-prompts.md`. Creates `outputs/jira-messages/<KEY>.md` (customer-facing only) and `outputs/internal-notes/<KEY>.md` (internal diagnosis only).

**Validation checkpoint:** Verify file separation (no [INTERNAL] sections in jira-messages; no customer greetings in internal-notes).

**Step 11 — Generate dated summary (Orchestrator)**

**Emit to stdout:** `STEP_11 __summary__`

After all active issues are processed through Steps 3–10, generate `outputs/issue-summary-YYYY-MM-DD.md` using `assets/issue-summary-template.md`.

**Required sections:**

1. **Executive Summary**
   - Total issues in scope
   - Count of Closed/Resolved (skipped at triage)
   - Count of active issues processed
   - Count of Engineering escalations (pre-escalated at sync + escalated during processing)
   - Count of Sandbox deployments/validations (Support-resolvable fixes only)
   - Count of on-hold or blockers

2. **Closed / Resolved (Skipped)**
   - Table: Issue, Jira Status, Summary
   - Issues filtered at triage (no pipeline processing)

3. **Issue Rollup**
   - Table: Issue, Jira Status, Summary, Disposition (fixed/escalated/on-hold), Prod deploy? (Gearset/No/N/A), Next Step
   - **Exclude** pre-escalated or escalated issues (they appear in Escalated to Engineering section below)

4. **Sandbox Deployments / Validations**
   - Table: Issue, Sandbox, Deploy/Validation, Prod deploy needed?
   - Support-resolvable fixes only

5. **Escalated to Engineering**
   - Unified table: Issue, Jira Status, Component, Handoff File, Problem, Potential Fix
   - Pre-escalated at sync + escalated during processing
   - **Must not** appear in Issue Rollup or Sandbox sections

6. **Artifact Index**
   - Links to: `outputs/jira/summary/`, `outputs/investigations/`, `outputs/engineering-escalations/`, `outputs/closed-resolved/`, `outputs/internal-notes/`, `outputs/jira-messages/`, `outputs/test-reports/`

**Progress tracking:** Log each issue's final disposition in `outputs/pipeline-logs/<RUN_DATE>.log` as: `END <KEY> disposition=<fixed|escalated|on-hold>`

**Step 12 — Return to user (Orchestrator)**

**Emit to stdout:** `STEP_12 __complete__`

After Step 11 summary is created, generate and present a clear action report:

**Report format:**

```
═══════════════════════════════════════════════════════════════════
CaseOps Pipeline Run Complete - YYYY-MM-DD
═══════════════════════════════════════════════════════════════════

Processing Summary:
- Issues processed: N active
- Support-fixed: N
- Engineering-escalated: N
- On-hold / blockers: N
- Closed/Resolved (skipped): N

Dated Summary: outputs/issue-summary-YYYY-MM-DD.md

NEXT STEPS FOR USER (Step 12 — Manual):

1. Review dated summary
   File: outputs/issue-summary-YYYY-MM-DD.md

2. Post Jira messages (customer-facing)
   - HEAL-XXXXX: outputs/jira-messages/HEAL-XXXXX.md
   - [Additional issues...]

3. Deploy to Production via Gearset (if needed)
   - [Issues requiring Gearset deployment]

4. Coordinate with Engineering (if applicable)
   - Engineering handoffs: outputs/engineering-escalations/

5. Archive and document
   - Pipeline run log: outputs/pipeline-logs/YYYYMMDD-HHMMSS.log
   - Internal notes: outputs/internal-notes/

Total runtime: H hours M minutes
```

**What the user owns (final manual step):**
- Post Jira message drafts to actual Jira issues (customer communication)
- Coordinate Production deployment via Gearset (if Support-fixed issues need to be promoted)
- Review Engineering handoffs and coordinate with Engineering team (if applicable)
- Archive run artifacts for audit trail

### Safety Constraints

**Step 1–2: Read Jira data**
- ✓ Sync issues from Jira
- ✓ Triage by status
- ✗ Do not modify Jira

**Step 3–7: Read Production metadata (read-only investigation only)**
- ✓ Query Production flows, validation rules, permission sets, fields, objects
- ✓ Use `CASEOPS_PRODUCTION_MAGIC_LINK` from `.env.jira` for UI access
- ✗ **Never write to Production**
- ✗ **Never execute actions in Production** (read-only diagnosis only)

**Step 8–9: Write ONLY to `CASEOPS_SANDBOX_TARGET_ORG`**

**Mandatory safety checks:**

1. **Before Step 8:** Read `CASEOPS_SANDBOX_TARGET_ORG` from `.env.jira`
   - If missing or empty: STOP and report error. User must set `.env.jira`.
   
2. **Before Step 9 (first time):** Verify Sandbox org is reachable
   - Test: `sf org list` should include the org alias
   - Test: `sf org display --target-org <CASEOPS_SANDBOX_TARGET_ORG>` should succeed
   - If unreachable: STOP, report auth/network error, ask user to refresh credentials or magic link

3. **Step 9 sub-agent execution:** Pass exact `CASEOPS_SANDBOX_TARGET_ORG` value to Step 9 prompt
   - Sub-agent must confirm CLI target matches before any deploy or write
   - Sub-agent must not proceed if org mismatch detected
   - Sub-agent must log all writes to Sandbox with timestamp and action description

4. **After Step 9:** Audit log
   - Log: "Deployed X to CASEOPS_SANDBOX_TARGET_ORG on [timestamp]"
   - Log each artifact changed (flow, field, permission set, data, etc.)
   - Log in `outputs/pipeline-logs/<RUN_DATE>.log`

**Step 10–12: Draft messages and summaries (file-based, no external writes)**
- ✓ Create files in `outputs/`
- ✓ User posts Jira messages in Step 12 (final manual action)
- ✗ Do not automatically post to Jira

**Blocker exits (system errors):**
- `.env.jira` missing CASEOPS_SANDBOX_TARGET_ORG → STOP
- Sandbox org unreachable or credentials expired → STOP
- Production write detected → STOP immediately, investigate, do not proceed

## Assets

- `assets/investigation-record-template.md` — working record per issue.
- `assets/step-4-problem-hypothesis-template.md` — Step 4 hypothesis worksheet.
- `assets/engineering-handoff-template.md` — Engineering escalations (includes Engineering Message section).
- `assets/internal-notes-template.md` — internal notes.
- `assets/jira-message-template.md` — Jira response draft.
- `assets/issue-summary-template.md` — dated rollup.
- `assets/test-report-template.md` — Sandbox test report.
- `assets/closed-resolved-log-template.md` — Closed/Resolved archive at triage.
