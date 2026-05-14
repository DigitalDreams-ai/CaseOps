# Jira to Salesforce fix workflow

**Authoritative numbered steps for `jira-salesforce-fix-pipeline`.** The orchestrator follows **Steps 1–11** below. Sub-agent copy-paste prompts live in **`references/sub-agent-prompts.md`**. Paths such as `assets/...` are relative to the skill folder `skills/jira-salesforce-fix-pipeline/`.

## Pipeline at a glance

| Step | Owner | What |
|------|--------|------|
| 1 | Orchestrator | Sync from Jira (`jira_sync.py`) |
| 2 | Orchestrator | Triage `manifest.csv` |
| 3 | **Sub-agent** | Analyze issue → investigation record (partial) |
| 4 | Orchestrator | Problem hypothesis and smallest viable fix |
| 5 | **Sub-agent** | Production metadata (read-only) → investigation record |
| 6 | Orchestrator | Engineering escalation gate |
| 7 | Orchestrator | Implement (Support path only) |
| 8 | **Sub-agent** | Deploy + test in allowlisted Sandbox (mandatory on Support path) |
| 9 | **Sub-agent** | Internal notes + Jira message drafts |
| 10 | Orchestrator | Dated issue summary |
| 11 | Orchestrator | Inform the user |

**Delegated skills:** Step 3 → `jira-issue-analysis`; Step 5 → `salesforce-production-metadata-investigation`; Step 8 → `salesforce-sandbox-deploy-test`; Step 9 → `jira-response-drafting`.

---

## Operator setup (CaseOps GUI + Claude)

Put **Chrome Dev** in `.env.jira` as `CASEOPS_CLAUDE_BROWSER`. Use **`CASEOPS_PRODUCTION_MAGIC_LINK`** only for **read-only** Production UI investigation and **`CASEOPS_SANDBOX_MAGIC_LINK`** for **full CRUD** in Sandbox (deploy/test). See **AGENTS.md**. Refresh frontdoor links when sessions expire; treat them like secrets.

---

## Step 1 — Sync from Jira

Run from the repo root:

```bash
python jira_sync.py --env-file .env.jira
```

For follow-up runs where only recent changes matter, add `--incremental`.

**If the script fails** (credentials, network, Jira unreachable): stop and report the error. Do not proceed with stale or partial data. If the user supplies pasted issue content or an export for affected keys, you may proceed for those keys only.

**Outputs:**

- `outputs/jira/raw/<KEY>.json` — full issue bundle
- `outputs/jira/summary/<KEY>.md` — lean summary
- `outputs/jira/manifest.csv` — index: Key, Status, Summary, Updated

---

## Step 2 — Triage routing from `manifest.csv`

Read `outputs/jira/manifest.csv` and route **every** issue **before** loading full issue content into context:

| Condition | Action |
|-----------|--------|
| Status is `Closed` or `Resolved` | Copy summary to `outputs/closed-resolved/<KEY>.md` using `assets/closed-resolved-log-template.md`. Log in the dated summary (Step 10). **Stop for this key — do not process further.** |
| Status is `Escalated to Engineering` (pre-existing Jira status) | Copy summary to `outputs/engineering-escalations/<KEY>.md`. Log in dated summary as pre-escalated. **Stop for this key.** |
| All other statuses | Add to the active list. Process **one key at a time** through Steps 3–11. |

Only load full issue content (`raw/<KEY>.json` or `summary/<KEY>.md`) for **active** issues.

---

## Step 3 — Analyze the issue [SUB-AGENT]

Spawn a sub-agent via the Agent tool using the template **“Step 3 — Analyze the issue”** in **`references/sub-agent-prompts.md`**.

The orchestrator retains **only** the returned compact summary. Do not read the full investigation file into orchestrator context.

---

## Step 4 — Determine the Salesforce problem and solution [ORCHESTRATOR]

From the Step 3 summary, state a Salesforce-specific **problem hypothesis** — confirmed facts separated from symptoms — and define the **smallest viable fix**: what metadata or code changes, why it solves the problem, Sandbox validation plan, rollback, and risks.

Examples:

- Flow condition does not match the expected case record type.
- Validation rule blocks the intended update.
- Permission set does not grant required field access.
- Assignment rule or queue routing condition is incomplete.

---

## Step 5 — Retrieve relevant Production metadata [SUB-AGENT]

Spawn a sub-agent using **“Step 5 — Retrieve relevant Production metadata”** in **`references/sub-agent-prompts.md`**. Paste the Step 4 hypothesis into the prompt.

**Existence check — required before any creation:** Before creating new metadata (field, permission set, list view, object, layout, etc.), query Production to confirm the intended API name and label do not already exist. See **`references/safety-policy.md`** (“Check Before Creating”) for query patterns.

- If the existing component is what you need → use and extend it.
- If the API name or label is taken by something else → pick a different API name and label; do not collide.

Do not create anything until API name and label are confirmed available or collisions are resolved.

The orchestrator retains **only** the returned compact summary.

---

## Step 6 — Engineering escalation gate [ORCHESTRATOR]

Using the Step 4 plan and Step 5 findings, classify:

- **Escalate to Engineering** if the fix requires Apex/code, flows, approval processes, validation rules, or other Engineering-owned automation.
- **Support-resolvable** only for data, config, access, report, list-view, or permission changes that do **not** require Engineering ownership.

**If escalating:** Do **not** implement or deploy. Draft `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md` (Engineering Message, root cause, affected metadata, evidence, reproduction). Then go to **Step 9** (drafting) with test result **“N/A - Engineering escalation”** — skip Steps **7** and **8**.

---

## Step 7 — Implement [ORCHESTRATOR]

Make local changes scoped to the issue. Avoid unrelated refactors. Record changed files in `outputs/investigations/<KEY>.md`.

Before creating new metadata, confirm it does not already exist in Production (Step 5 existence check and **`references/safety-policy.md`**). Extend existing components when possible.

Update **`Solution Plan` → Production vs sandbox deployment state** in the investigation record: pre-fill what Production has vs what will be Sandbox-only, and the expected **Production deploy?** (**Yes — Gearset** / **No** / **N/A**). Refine after Step 8 with test evidence.

## Step 8 — Deploy, test, and iterate [SUB-AGENT] (mandatory on Support path)

**Spawn this sub-agent** after Step 7 for every Support-resolvable issue. **Do not skip** deploy and test to “finalize” in prose first.

**Allowlist:** Read **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira`. If missing or empty, **STOP**. Only that org may receive deploys or mutating operations. See **`references/sub-agent-prompts.md`** — **“Step 8 — Deploy, test, and iterate”** for the full prompt and failure-loop behavior.

On **Fail:** revise hypothesis (Step 4), re-run Step 5 if needed, re-implement (Step 7), re-run Step 8. Record iterations in `outputs/investigations/<KEY>.md`.

---

## Step 9 — Draft internal notes and Jira message [SUB-AGENT]

Spawn a sub-agent using **“Step 9 — Draft internal notes and Jira message”** in **`references/sub-agent-prompts.md`**. For Support path, **test result** must come from Step 8; for Engineering escalation from Step 6, use **“N/A - Engineering escalation”**.

**Production vs Sandbox in every customer-facing and internal summary:** Drafts must **never** read as if new metadata already exists in **Production** when it was only created or deployed in **Sandbox**. Always include an explicit line: **Production deploy required** (e.g. Gearset) vs **already in Production** vs **N/A** (no metadata change). This pipeline does not promote to Production unless the operator explicitly asks.

---

## Documentation standard: Production vs Sandbox

Apply to investigation updates, test reports, internal notes, Jira drafts, and dated rollup:

| Must state | Options |
| --- | --- |
| What **Production** has (read-only verification) | Present / absent / partial + how we know |
| What exists **only in Sandbox** after the fix | List components |
| **Production metadata deploy required?** | **Yes** — Gearset (or standard) / **No** / **N/A** |
| **Operator next step** | Concrete action |

Do **not** conflate “fix confirmed in Sandbox” with “Production is fixed” unless Production was separately verified or deployed by the operator.

---

## Step 10 — Create or update the dated summary

Create or update `outputs/issue-summary-YYYY-MM-DD.md` (today’s date) using `assets/issue-summary-template.md`.

The summary must include:

- Total issues in scope.
- Escalated to Engineering (Jira status) count.
- Active issues processed count.
- Engineering handoffs raised during processing count.
- Sandbox deployment/validation count (Support-owned issues only).
- Operational/data/access follow-up count.
- **Closed/Resolved** section: one row per skipped issue.
- **Issue rollup** table: one row per active issue with Jira status, summary, disposition, **Production deploy?** (Gearset / No / N/A), next step. **Exclude** issues whose Jira status is already “Escalated to Engineering” from this table.
- **Sandbox deployments / validations** section: Support-owned fixes only. Include **Prod deploy needed?** per row. **Do not** duplicate pre-escalated or Engineering-only rows here.
- **Escalated to Engineering** section: one unified table (pre-escalated at sync **and** escalated during processing). Columns: Issue, Jira Status, Component, Handoff File, Problem, Potential Fix. **Only place** escalated issues appear together.
- **Artifact index** for Jira summaries, investigations, engineering handoffs, closed/resolved logs, internal notes, Jira messages, and test reports.

---

## Step 11 — Inform the user

Per issue, report:

- Jira key and summary
- Root cause
- Solution or escalation status
- **Production vs Sandbox:** what exists in Production (verified read-only) vs Sandbox-only; **Production deploy required?** (Gearset / No / N/A); operator next step
- Files or metadata changed
- Sandbox target (if applicable)
- Tests run and outcome
- Open risks or follow-up
- Paths: internal notes, Jira message draft, dated summary

---

## Final verification

Before closing the run, check **`references/quality-checklist.md`**.
