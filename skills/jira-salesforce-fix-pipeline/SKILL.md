---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process and work assigned issues, diagnose Salesforce problems, investigate Production metadata, determine whether to escalate to Engineering, implement Support-owned fixes, deploy to Sandbox, test the fix, iterate if needed, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
---

# Jira Salesforce Fix Pipeline

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
- Target Salesforce Sandbox name or alias before deployment.
- Production org access or exported Production metadata for read-only investigation.
- Acceptance criteria or enough issue detail to infer testable behavior.

## Agent Architecture

This pipeline is an orchestrator. Steps 1, 2, 4, 6, 7, 10, and 11 run in the orchestrator context. Steps 3, 5, 8, and 9 are delegated to sub-agents using the Agent tool.

**Why sub-agents:** Each sub-agent runs in a clean context window, preventing context rot across a long multi-issue pipeline run. The orchestrator receives only a compact summary (300–500 tokens) from each sub-agent — not the full context of its work — keeping the orchestrator context lean throughout.

**Sub-agent discipline:**
- Spawn one sub-agent per step per issue. Do not batch multiple issues into a single sub-agent call.
- Each sub-agent prompt must be fully self-contained: include the issue key, relevant file paths, the specific task, and the return format. The sub-agent has no access to the orchestrator's context.
- The sub-agent writes its output files directly to `outputs/`. The orchestrator reads the compact summary returned, not the full output file.

## Workflow

### Step 1 — Sync from Jira

Run the sync script to pull all issues assigned to you:

```
python jira_sync.py --env-file .env.jira
```

For follow-up runs where only recent changes matter, add `--incremental`.

The script produces:
- `outputs/jira/raw/<KEY>.json` — full issue bundle per issue
- `outputs/jira/summary/<KEY>.md` — lean markdown summary per issue
- `outputs/jira/manifest.csv` — index of all synced issues with Key, Status, Summary, Updated

**If the script fails** (bad credentials, network error, Jira unreachable): stop and report the error to the user. Do not proceed with stale or partial data. If the user provides pasted issue content or a Jira export as a fallback, you may proceed with that for the affected issues only.

### Step 2 — Triage routing from manifest.csv

Read `outputs/jira/manifest.csv` and route every issue before loading full content into context:

| Condition | Action |
|---|---|
| Status is `Closed` or `Resolved` | Copy summary to `outputs/closed-resolved/<KEY>.md` using `assets/closed-resolved-log-template.md`. Log in dated summary. **Stop. Do not process further.** |
| Status is `Escalated to Engineering` (pre-existing Jira status) | Copy summary to `outputs/engineering-escalations/<KEY>.md`. Log in dated summary as pre-escalated. **Stop. Do not process further.** |
| All other statuses | Add to the active issue list. Process one at a time through steps 3–14. |

Only load full issue content for active issues. Process one at a time through steps 3–11.

### Step 3 — Analyze the issue [SUB-AGENT]

Spawn a sub-agent using the Agent tool with the following prompt, substituting the actual values:

```
You are analyzing a Jira issue for Salesforce implementation work.

Issue key: <KEY>
Jira summary file: outputs/jira/summary/<KEY>.md

Instructions:
1. Use the jira-issue-analysis skill.
2. Read outputs/jira/summary/<KEY>.md as your primary input.
3. Write the Issue Understanding section of outputs/investigations/<KEY>.md
   using skills/jira-salesforce-fix-pipeline/assets/investigation-record-template.md.

Return a compact summary (max 400 tokens) containing:
- Observed behavior
- Expected behavior
- Acceptance criteria
- Affected Salesforce area (object, field, flow, permission, etc.)
- Top unknowns or missing information
- Path written: outputs/investigations/<KEY>.md
```

The orchestrator retains only the returned summary. Do not read the full investigation file into orchestrator context.

### Step 4 — Determine the Salesforce problem and solution [ORCHESTRATOR]

From the sub-agent summary returned in Step 3, state a Salesforce-specific problem hypothesis — confirmed facts separated from symptoms — and define the smallest viable fix: what metadata or code changes, why it solves the problem, the Sandbox validation plan, rollback approach, and risks.

### Step 5 — Retrieve relevant Production metadata [SUB-AGENT]

Spawn a sub-agent using the Agent tool with the following prompt:

```
You are retrieving Salesforce Production metadata for a Jira issue.

Issue key: <KEY>
Problem hypothesis: <paste the hypothesis from Step 4>
Investigation record: outputs/investigations/<KEY>.md

Instructions:
1. Use the salesforce-production-metadata-investigation skill.
2. Retrieve only metadata directly relevant to the hypothesis. Do not modify Production.
3. Append your findings to the Production Metadata Retrieved section of
   outputs/investigations/<KEY>.md.

Return a compact summary (max 400 tokens) containing:
- Metadata items retrieved and why
- Key findings per item
- Whether each item confirms or rejects the hypothesis
- Recommended implementation surface (what to change and where)
- Path written: outputs/investigations/<KEY>.md
```

The orchestrator retains only the returned summary.

### Step 6 — Engineering escalation gate [ORCHESTRATOR]

Using the Step 4 solution plan and Step 5 metadata findings, classify the fix:

- **Escalate to Engineering** if the fix requires changing Apex/code, flows, approval processes, validation rules, or other Engineering-owned automation.
- **Continue as Support-resolvable** only for data, config, access, report, list-view, or permission changes that do not require Engineering ownership.

For Engineering escalations: do not implement or deploy. Draft the handoff at `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md`. The handoff must include the Engineering Message section (simple problem description + potential fix), root cause, affected metadata, evidence, and reproduction details. Then skip to Step 9.

### Step 7 — Implement [ORCHESTRATOR]

Make local changes scoped to the issue. Avoid unrelated refactors. Record all changed files in `outputs/investigations/<KEY>.md`.

### Step 8 — Deploy, test, and iterate [SUB-AGENT]

**DEPLOYMENT RULE — read before spawning this sub-agent.**

- Deploying to `10xhealth-sean` (the predefined sandbox, `CASEOPS_SANDBOX_TARGET_ORG`) is permitted without additional confirmation.
- Deploying to Production (`10xhealth`) is NEVER permitted under any circumstances.
- Deploying to any other org requires explicit user approval in the current conversation before proceeding. Stop and ask if the target is anything other than `10xhealth-sean`.

Spawn a sub-agent using the Agent tool with the following prompt:

```
You are deploying and testing a Salesforce fix in Sandbox.

Issue key: <KEY>
Sandbox target: <SANDBOX ALIAS>
Fix description: <paste the solution from Step 7>
Investigation record: outputs/investigations/<KEY>.md

Instructions:
1. Use the salesforce-sandbox-deploy-test skill.
2. Confirm the Sandbox target, deploy the fix, and test against the Jira acceptance criteria.
3. Write results to outputs/test-reports/<KEY>.md using
   skills/jira-salesforce-fix-pipeline/assets/test-report-template.md.

Return a compact summary (max 400 tokens) containing:
- Pass or Fail
- Steps tested and actual results
- Whether the issue is confirmed fixed
- If failed: what broke, what hypothesis was wrong, what to try next
- Path written: outputs/test-reports/<KEY>.md
```

If the sub-agent returns Fail: update the problem hypothesis in Step 4, spawn a new Step 5 sub-agent if more metadata is needed, re-implement in Step 7, and spawn a new Step 8 sub-agent. Repeat until confirmed fixed or reclassified as Engineering escalation. Record each failed iteration in `outputs/investigations/<KEY>.md`.

### Step 9 — Draft internal notes and Jira message [SUB-AGENT]

Spawn a sub-agent using the Agent tool with the following prompt:

```
You are drafting internal notes and a Jira message for a completed Salesforce issue.

Issue key: <KEY>
Root cause: <from Step 4>
Fix or escalation: <Support fix description from Step 7, or "Escalated to Engineering">
Test result: <from Step 8 summary, or "N/A - Engineering escalation">
Investigation record: outputs/investigations/<KEY>.md
Test report: outputs/test-reports/<KEY>.md (if exists)
Engineering handoff: outputs/engineering-escalations/<KEY>.md (if escalated)

Instructions:
1. Use the jira-response-drafting skill.
2. Write internal notes to outputs/internal-notes/<KEY>.md.
3. Write the Jira message draft to outputs/jira-messages/<KEY>.md.

Return a compact summary (max 300 tokens) containing:
- One-paragraph outcome summary
- Paths written: outputs/internal-notes/<KEY>.md, outputs/jira-messages/<KEY>.md
```

### Step 10 — Create or update the dated summary

Create or update `outputs/issue-summary-YYYY-MM-DD.md` (using today's date) with `assets/issue-summary-template.md`. Include all issues from the current run: Closed/Resolved skips, pre-escalated, Engineering escalations from processing, and active pipeline results.

### Step 11 — Inform the user

Report per issue: key and summary, root cause, solution or escalation status, files or metadata changed, Sandbox target, tests run, outcome, open risks, internal notes path, Jira message path, and dated summary path.

## References

- `references/workflow.md`: Full pipeline details and iteration rules.
- `references/safety-policy.md`: Production, Sandbox, Jira, and data-handling guardrails.

## Assets

- `assets/investigation-record-template.md`: Working record for each Jira issue.
- `assets/engineering-handoff-template.md`: Required output format for Engineering escalations (includes Engineering Message section).
- `assets/internal-notes-template.md`: Internal implementation notes format.
- `assets/jira-message-template.md`: User-editable Jira response draft.
- `assets/issue-summary-template.md`: Dated rollup summary format for all processed issues.
- `assets/test-report-template.md`: Sandbox test report format.
- `assets/closed-resolved-log-template.md`: Archive record for Closed/Resolved issues skipped at triage.

## Quality Checks

- `jira_sync.py` is run before any issue processing begins.
- `manifest.csv` is read and all issues are routed before loading full issue content.
- Closed/Resolved issues are archived to `outputs/closed-resolved/<KEY>.md` and not processed.
- Issues with Jira status "Escalated to Engineering" are archived to `outputs/engineering-escalations/<KEY>.md` and not processed further.
- Active issues are processed one at a time, sequentially.
- Steps 3, 5, 8, and 9 are always executed as sub-agents via the Agent tool — never inline in the orchestrator context.
- Each sub-agent prompt is fully self-contained with the issue key, relevant file paths, task, and return format.
- The orchestrator retains only the compact summary returned by each sub-agent, not the full contents of output files.
- Production metadata retrieval is read-only.
- The Salesforce problem statement is explicit before implementation.
- The solution plan identifies affected metadata or code.
- The Engineering escalation gate is evaluated before any implementation or Sandbox deployment.
- Engineering handoffs include the Engineering Message section: simple problem description and potential fix.
- Engineering handoff notes are stored under `outputs/engineering-escalations/`.
- The target Sandbox is explicit before deployment.
- Tests map to Jira acceptance criteria.
- Failed iterations are recorded in `outputs/investigations/<KEY>.md` before re-spawning sub-agents.
- The dated issue summary `outputs/issue-summary-YYYY-MM-DD.md` is created or updated after all issues are processed.
- The summary includes Closed/Resolved skips, Engineering escalations, and active pipeline results.
- Final Jira message is factual and avoids overclaiming.
