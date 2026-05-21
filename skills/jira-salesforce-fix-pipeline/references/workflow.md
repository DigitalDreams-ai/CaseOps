# Jira to Salesforce fix workflow

**Authoritative numbered steps for `jira-salesforce-fix-pipeline`.** The orchestrator follows **Steps 1–12** below. Sub-agent copy-paste prompts live in **`references/sub-agent-prompts.md`**. Paths such as `assets/...` are relative to the skill folder `skills/jira-salesforce-fix-pipeline/`.

## Pipeline at a glance

| Step | Owner | What |
|------|--------|------|
| 1 | Orchestrator | Sync from Jira (`jira_sync.py`) |
| 2 | Orchestrator | Triage `manifest.csv` |
| 3 | **Sub-agent** | Analyze issue → investigation record (partial) |
| 4 | Orchestrator | Problem hypothesis and smallest viable fix |
| 5 | **Sub-agent** | Production metadata (read-only) → investigation record |
| 6 | **Sub-agent** | Identify problem location (type, artifact, failure point) |
| 7 | Orchestrator | Engineering escalation gate |
| 8 | Orchestrator | Implement (Support path only) |
| 9 | **Sub-agent** | Deploy + test in allowlisted Sandbox (mandatory on Support path) |
| 10 | **Sub-agent** | Internal notes + Jira message drafts |
| 11 | Orchestrator | Dated issue summary |
| 12 | Orchestrator | Inform the user |

**Delegated skills:** Step 3 → `jira-issue-analysis`; Step 5 → `salesforce-production-metadata-investigation`; Step 6 → `salesforce-production-metadata-investigation` (drilling); Step 9 → `salesforce-sandbox-deploy-test`; Step 10 → `jira-response-drafting`.

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

From the Step 3 summary (Issue Understanding), synthesize a Salesforce-specific **problem hypothesis** and define the **smallest viable fix**.

**Output artifact:** Inline notes or `outputs/step-4-hypothesis/<KEY>.md` using `assets/step-4-problem-hypothesis-template.md`.

**Must include:**
- **Confirmed facts** (from Step 3, separated from symptoms)
- **Root cause hypothesis** (one sentence: what is broken and why)
- **Smallest viable fix** (exact artifact + specific change + why it solves)
- **Sandbox validation plan** (test scenario, expected outcome, success criteria)
- **Rollback plan** (if Sandbox or Production deployment fails)
- **Risks and constraints** (potential side effects, external dependencies, mitigations)
- **Production deploy readiness** (Gearset vs manual, rollout timing, monitoring)

**Examples of strong hypotheses:**
- "Flow condition does not match the expected case record type; Fix: add OR condition for the missing record type."
- "Validation rule blocks the intended update; Fix: modify rule exception to allow this workflow."
- "Permission set does not grant required field access; Fix: add field-level Read-Write permission for this field."
- "Apex integration payload is missing required address fields in JSON structure; Fix: update CMT mappings to emit flat root-level fields instead of nested objects."

**Input to Step 5:** Pass the Step 4 hypothesis (from file or inline) as the "Problem hypothesis" input to Step 5 sub-agent prompt. Steps 5 and 6 will use this to scope metadata retrieval and problem location drilling.

---

## Step 5 — Retrieve relevant Production metadata [SUB-AGENT]

Spawn a sub-agent using **“Step 5 — Retrieve relevant Production metadata”** in **`references/sub-agent-prompts.md`**. Paste the Step 4 hypothesis into the prompt.

**Existence check — required before any creation:** Before creating new metadata (field, permission set, list view, object, layout, etc.), query Production to confirm the intended API name and label do not already exist. See **`references/safety-policy.md`** (“Check Before Creating”) for query patterns.

- If the existing component is what you need → use and extend it.
- If the API name or label is taken by something else → pick a different API name and label; do not collide.

Do not create anything until API name and label are confirmed available or collisions are resolved.

The orchestrator retains **only** the returned compact summary.

---

## Step 6 — Identify problem location [SUB-AGENT]

**Mandatory gate before escalation.** Spawn a sub-agent using **"Step 6 — Identify problem location"** in **`references/sub-agent-prompts.md`**. Drill down from Step 5 metadata to pinpoint the exact artifact causing the problem.

**Must identify:**
- **Problem type** (data / component / config / integration / access / setting / process)
- **Specific artifact** (exact name, API name, class name, field name, etc.)
- **Location** (Production path: Setup > Object > Field, or code path, or org setting, etc.)
- **Failure point** (where in the flow it breaks: at read, at mapping, at validation, at API call, etc.)

**Example outputs:**
- Data: "Order.ShipToCity field is null (Production has field, data missing)"
- Component: "Apex class WellviPayloadBuilder, line 45, SOQL SELECT missing ShipToCity"
- Config: "Permission Set 'Order Manager' missing Read-Write on ShipToCity field"
- Integration: "Wellvi API endpoint /v1/submit rejects null address fields (external constraint)"
- Access: "User 'Agent X' role lacks permission to edit Order record type 'Phone Order'"

**Iteration with Step 5:** If Step 6 discovers additional Production metadata is needed (e.g., "Found custom Flow handler, need to retrieve Flow definition"), pause Step 6, loop back to Step 5 with refined metadata request, then resume Step 6 with retrieved metadata. Record iterations in `outputs/investigations/<KEY>.md`.

The orchestrator retains **only** the returned compact summary. Do not read the full investigation file into context.

---

## Step 7 — Engineering escalation gate [ORCHESTRATOR]

Using the Step 6 problem location (exact artifact + failure point), classify:

- **Escalate to Engineering** if the artifact requires Apex/code changes, Flow modifications, approval processes, validation rule updates, or other Engineering-owned automation to fix.
- **Support-resolvable** only for data updates, permission assignments, config changes (like enabling a feature flag), or read-only metadata that do **not** require Engineering code ownership.

**If escalating:** Do **not** implement or deploy. Draft `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md` with problem location details from Step 6 (exact artifact, location, failure point, root cause). Then go to **Step 10** (drafting) with test result **”N/A - Engineering escalation”** — skip Steps **8** and **9**.

---

## Step 8 — Implement [ORCHESTRATOR]

Make local changes scoped to the issue. Avoid unrelated refactors. Record changed files in `outputs/investigations/<KEY>.md`.

Before creating new metadata, confirm it does not already exist in Production (Step 5 existence check and **`references/safety-policy.md`**). Extend existing components when possible.

Update **`Solution Plan` → Production vs sandbox deployment state** in the investigation record: pre-fill what Production has vs what will be Sandbox-only, and the expected **Production deploy?** (**Yes — Gearset** / **No** / **N/A**). Refine after Step 9 with test evidence.

## Step 9 — Deploy, test, and iterate [SUB-AGENT] (mandatory on Support path)

**Spawn this sub-agent** after Step 8 for every Support-resolvable issue. **Do not skip** deploy and test to “finalize” in prose first.

**Allowlist:** Read **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira`. If missing or empty, **STOP**. Only that org may receive deploys or mutating operations. See **`references/sub-agent-prompts.md`** — **”Step 9 — Deploy, test, and iterate”** for the full prompt and failure-loop behavior.

On **Fail:** revise hypothesis (Step 4), re-run Step 5 if needed (and Step 6 if more drilling required), re-implement (Step 8), re-run Step 9. Record iterations in `outputs/investigations/<KEY>.md`.

---

## Step 10 — Draft internal notes and Jira message [SUB-AGENT]

Spawn a sub-agent using **”Step 10 — Draft internal notes and Jira message”** in **`references/sub-agent-prompts.md`**. For Support path, **test result** must come from Step 9; for Engineering escalation from Step 7, use **”N/A - Engineering escalation”**.

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

## Step 11 — Create or update the dated summary [ORCHESTRATOR — OPTIONAL]

**When using Claude Code skill** (`/jira-salesforce-fix-pipeline`): This step is typically deferred or run separately. After processing all issues through Steps 1-10, run:

```bash
python run_pipeline.py --no-sync --no-agents
```

This executes the Python orchestrator’s Steps 11-12 without re-syncing Jira or re-running sub-agents. It rolls up all processed issues into a dated summary.

**When using Python orchestrator** (`run_pipeline.py`): Steps 11-12 execute automatically after all issues complete.

---

**Output artifact:** `outputs/issue-summary-YYYY-MM-DD.md` using `assets/issue-summary-template.md`.

**The summary must include:**

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

## Step 12 — Inform the user [ORCHESTRATOR — MANUAL]

After all issues are processed and Step 11 summary is created, report back to stakeholders.

**When using Claude Code skill** (`/jira-salesforce-fix-pipeline`): Report is generated inline during skill execution. Manually summarize for stakeholders: reference the dated summary file (`outputs/issue-summary-YYYY-MM-DD.md`) and individual Jira message drafts (`outputs/jira-messages/<KEY>.md`).

**When using Python orchestrator** (`run_pipeline.py`): Summary is printed to stdout and written to dated summary file.

---

**What to report per issue:**

- **Jira key and summary**
- **Root cause** (from Step 4 hypothesis + Step 6 confirmation)
- **Solution or escalation status** (Support-fixed / Engineering-escalated / On-hold pending customer response)
- **Production vs Sandbox:** 
  - What exists in Production (verified read-only)
  - What is Sandbox-only (after fix deployed)
  - **Production deploy required?** (Yes — Gearset / No / N/A)
  - Operator next step (e.g., "Run Gearset to promote to Production", "Deploy via standard change control")
- **Files or metadata changed** (list of Apex classes, Flows, fields, configs modified)
- **Sandbox target** (if applicable; reference CASEOPS_SANDBOX_TARGET_ORG)
- **Tests run and outcome** (from Step 9 test report, if Support-resolvable)
- **Open risks or follow-up** (known issues, test gaps, manual verification needed)
- **Paths:** Internal notes (`outputs/internal-notes/<KEY>.md`), Jira message draft (`outputs/jira-messages/<KEY>.md`), dated summary (`outputs/issue-summary-YYYY-MM-DD.md`)

---

## Final verification

Before closing the run, check **`references/quality-checklist.md`**.

---

## Step 5 ↔ Step 6 Iteration (Metadata Loop)

If Step 6 discovers additional Production metadata is needed during problem location drilling:

1. **Step 6 pauses** — returns request for specific metadata (e.g., "Found custom Flow handler, need Flow definition")
2. **Loop back to Step 5** — spawn new Step 5 sub-agent with refined metadata request
3. **Step 5 retrieves** — appends findings to investigation record
4. **Resume Step 6** — drill continues with retrieved metadata to complete problem location identification
5. **Record in investigation** — document iteration history (e.g., "Step 5 loop 1: Email-to-Case routing addresses. Step 6 discovers custom handler. Step 5 loop 2: Flow definition for handler.")

This loop is distinct from Step 8 failure iteration (Step 4 → 5 → 8 cycle). Step 5/6 iteration is for **metadata discovery**, Step 8 iteration is for **implementation/test failure**.
