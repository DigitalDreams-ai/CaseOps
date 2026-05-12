# Jira To Salesforce Fix Workflow

## Pipeline

0. Sync from Jira using `jira_sync.py`. Triage and route all issues before processing.
1. [jira-issue-analysis] Process each active issue into a structured record.
2. Determine the Salesforce problem and solution.
3. [salesforce-production-metadata-investigation] Retrieve relevant metadata from Production.
4. Engineering escalation gate: classify as Support-resolvable or Engineering escalation.
5. For Engineering escalations: produce handoff file. Skip to step 8.
6. For Support-resolvable fixes: implement the solution.
7. [salesforce-sandbox-deploy-test] Deploy to Sandbox, test, iterate until fixed.
8. [jira-response-drafting] Draft internal notes and Jira message.
9. Create or update the dated issue summary.
10. Inform the user.

## Step Details

### 0. Sync and Triage

**Sync:**

Run the script to pull all issues assigned to you:

```
python jira_sync.py --env-file .env.jira
```

For follow-up runs, use `--incremental` to limit to recently updated issues.

The script outputs:
- `outputs/jira/raw/<KEY>.json` — full issue bundle
- `outputs/jira/summary/<KEY>.md` — lean markdown summary
- `outputs/jira/manifest.csv` — index: Key, Status, Summary, Updated, paths

**Triage routing:**

Read `manifest.csv` immediately. Route every issue before loading any full issue content:

| Status | Action |
|---|---|
| `Closed` or `Resolved` | Archive summary to `outputs/closed-resolved/<KEY>.md` using `assets/closed-resolved-log-template.md`. Log in dated summary. Skip. |
| `Escalated to Engineering` | Archive summary to `outputs/engineering-escalations/<KEY>.md`. Log in dated summary as pre-escalated. Skip. |
| All other statuses | Add to active list. Process sequentially through steps 1–11. |

Only load full issue content (`raw/<KEY>.json` or `summary/<KEY>.md`) for active issues. Process one issue at a time.

### 1. Analyze Issues → `jira-issue-analysis`

Invoke the `jira-issue-analysis` skill for each active issue. It reads `outputs/jira/summary/<KEY>.md` and produces a structured issue record covering observed/expected behavior, acceptance criteria, reproduction steps, affected Salesforce area, and unknowns. See that skill's workflow for full detail.

### 2. Determine Salesforce Problem and Solution

From the issue analysis output, state a Salesforce-specific problem hypothesis — confirmed facts separated from user-reported symptoms. Then define the smallest viable fix: what metadata or code changes, why it solves the problem, the Sandbox validation plan, rollback approach, and risks.

Examples of problem statements:
- Flow condition does not match the expected case record type.
- Validation rule blocks the intended update.
- Permission set does not grant required field access.
- Assignment rule or queue routing condition is incomplete.

### 3. Retrieve Production Metadata → `salesforce-production-metadata-investigation`

Invoke the `salesforce-production-metadata-investigation` skill. It owns targeted read-only retrieval, recording what was retrieved and why, and separating findings from hypotheses. See that skill's workflow for full detail.

**Existence check — required before any creation:**

Before creating any new metadata component (field, permission set, list view, object, layout, etc.), query Production to confirm the intended API name and label do not already exist. See `safety-policy.md` § "Check Before Creating" for query patterns.

- If the existing component is the same thing you need → use and extend it.
- If the API name or label is taken by something different → choose a different API name and label. Do not collide with an existing name even if the component serves a different purpose.

Do not create anything until both the API name and label are confirmed available or the collision is resolved.

### 4. Engineering Escalation Gate

Before any implementation or deployment, classify the solution.

Escalate to Engineering when the issue requires changing:
- Apex or other code.
- Salesforce flows.
- Approval processes.
- Validation rules.
- Other Engineering-owned automation.

For escalations: do not implement or deploy. Produce `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md`. Include the Engineering Message section, root cause, affected metadata, potential fix, evidence, and reproduction details. Then skip to step 8.

Only continue to step 5 for Support-resolvable fixes: access, data correction, report/list-view, or configuration changes that do not require Engineering ownership.

### 5. Implement

Make local changes scoped to the issue. Avoid unrelated refactors.

Before creating any new metadata component, confirm it does not already exist in Production (see step 3 existence check and `safety-policy.md` § "Check Before Creating"). If it exists, extend it. Only create something new when the query confirms it is absent and no existing component can be adapted.

### 6. Deploy, Test, and Iterate → `salesforce-sandbox-deploy-test`

Invoke the `salesforce-sandbox-deploy-test` skill for deployment to `10xhealth-sean` (the predefined sandbox). Do NOT deploy to Production (`10xhealth`) or any other org — those require explicit user approval in the current conversation. The skill owns deployment, testing against Jira acceptance criteria, and result recording. If tests fail, it returns failure evidence — update the problem hypothesis from step 2, re-invoke `salesforce-production-metadata-investigation` if more metadata is needed, re-implement (step 5), and re-invoke `salesforce-sandbox-deploy-test`. Do not discard failed attempts.

### 7. Draft Notes and Jira Message → `jira-response-drafting`

Invoke the `jira-response-drafting` skill. It owns drafting internal notes and the Jira-ready message for both confirmed fixes and Engineering escalations. See that skill's workflow for full detail.

### 9. Create or Update Dated Summary

Create or update `outputs/issue-summary-YYYY-MM-DD.md` using today's date. See SKILL.md Step 10 for required sections.

### 10. Inform User

Before the final response, create or update:

```text
outputs/issue-summary-YYYY-MM-DD.md
```

Use today's date in the filename (e.g., `issue-summary-2026-05-11.md`).

The summary must include:

- Total issues in scope.
- Escalated to Engineering (Jira status) count.
- Active issues processed count.
- Engineering handoffs raised during processing count.
- Sandbox deployment/validation count (Support-owned issues only).
- Operational/data/access follow-up count.
- Closed/Resolved section: one row per skipped issue.
- Issue rollup table: one row per active issue with Jira status, summary, disposition, and next step. **Do not include issues with Jira status "Escalated to Engineering" here.**
- Sandbox Deployments / Validations section: Support-owned fixes only. **Do not include issues that are in the Escalated to Engineering section — their sandbox work belongs in their handoff files.**
- Escalated to Engineering section: one unified table covering all escalated issues (pre-escalated at sync AND escalated during processing). Columns: Issue, Jira Status, Component, Handoff File, Problem, Potential Fix. **This is the only place escalated issues appear.**
- Artifact index for Jira summaries, investigations, engineering handoffs, closed/resolved logs, internal notes, Jira messages, and test reports.

Report per issue:

- Jira issue key and summary.
- Root cause.
- Solution or Engineering handoff status.
- Files or metadata changed.
- Sandbox deployed to.
- Tests run.
- Whether the issue is fixed.
- Open risks or follow-up.
- Draft internal notes path.
- Draft Jira message path.
- Dated issue summary path.
