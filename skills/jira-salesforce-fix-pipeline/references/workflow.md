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
| 8 | Orchestrator | Implement (both paths: propose fix) |
| 9 | **Sub-agent** | Deploy + test in allowlisted Sandbox (both paths: validate proposed solution) |
| 10 | **Sub-agent** | Internal notes + Jira message + escalation handoff (if needed) |
| 11 | Orchestrator | Dated issue summary |
| 12 | Orchestrator | Inform the user |

**Delegated skills:** Step 3 → `jira-issue-analysis`; Step 5 → `salesforce-production-metadata-investigation`; Step 6 → `salesforce-production-metadata-investigation` (drilling); Step 9 → `salesforce-sandbox-deploy-test`; Step 10 → `jira-response-drafting`.

**Both paths run full Steps 1-12.** Escalation routing decision in Step 7 determines how Step 10 routes: Support issues produce Sandbox-validated packages ready for operator-controlled Production promotion; Escalation issues hand off to Engineering with Sandbox-validated proposed solutions. CaseOps does not deploy to Production.

---

## Operator setup (CaseOps GUI + Claude)

Put **Chrome Dev** in `.env.jira` as `CASEOPS_CLAUDE_BROWSER` only for visual UI checks. Default Salesforce access is **sf CLI + SOQL**. Use **`CASEOPS_PRODUCTION_MAGIC_LINK`** only for read-only visual Production UI inspection and **`CASEOPS_SANDBOX_MAGIC_LINK`** only for visual Sandbox UI inspection or UI-only actions. Do not use frontdoor session IDs as API bearer tokens; they do not replace `sf` CLI auth. See **AGENTS.md**. Refresh frontdoor links when sessions expire; treat them like secrets.

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

**Output artifact:** Inline notes or `outputs/hypothesis/<KEY>.md` using `assets/step-4-problem-hypothesis-template.md`.

Generated supporting files such as spreadsheets, CSV exports, PDFs, or screenshots must be saved under `outputs/generated-files/<KEY>/`, never directly under `outputs/`.

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

**Input to Step 5:** Pass the Hypothesis (from file or inline) as the "Problem hypothesis" input to Step 5 sub-agent prompt. Steps 5 and 6 will use this to scope metadata retrieval and problem location drilling.

---

## Salesforce metadata workspace

Use the environment-provided workspace instead of ad hoc root directories:

| Purpose | Directory |
| --- | --- |
| Raw Production metadata, read-only | `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/` |
| Sandbox test attempts | `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/` |
| Confirmed Support package | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/support-owned/` |
| Confirmed Engineering proposal | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/engineering-proposal/` |

Raw Production metadata is stored in the persistent metadata cache and may be reused as read-only evidence, but it must not be edited. Every Sandbox attempt gets its own persistent issue-workspace directory with `baseline-sandbox/`, `candidate/`, and `revert/` subdirectories. Failed or abandoned attempts must be reverted in Sandbox before the next attempt starts.

Each issue with Sandbox work must maintain `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/metadata-workspace.json` with attempt number, touched components, baseline path, candidate path, revert status, test outcome, and confirmed package path when applicable. This is the index that keeps the workspace auditable without spreading metadata across root-level folders.

---

## Org knowledge progressive disclosure

CaseOps maintains reusable org knowledge under the instance output directory:

```text
outputs/org-knowledge/
  index.json
  run-rules.md
  query-patterns/
  deploy-patterns/
  lessons-learned.md
```

The orchestrator reads `index.json`, selects only files relevant to the active issue, and injects a capped **Org Knowledge Context** into the run prompt. Do not read every file under `org-knowledge/`.

Before spawning Step 5, Step 6, Step 8, or Step 9 sub-agents, include the relevant selected org-knowledge bullets in the sub-agent prompt. Sub-agents start with isolated context and do not automatically know what the orchestrator read.

Use org knowledge to avoid relearning Salesforce CLI behavior. If a selected pattern fails twice, stop and replan; do not try many small variants of the same failed command.

For known Salesforce mechanics, use the CaseOps helper before improvising:

```bash
python scripts/sf_caseops_helper.py --help
```

The helper is the preferred path for custom field/picklist summaries, layout placement, FLS checks, and deterministic MDAPI candidate deploys. It writes compact JSON summaries in the issue workspace and keeps noisy CLI progress out of the pipeline log.

Retrieve/deploy command contract:

- Use modern `sf` CLI commands only.
- Do not use legacy `sfdx force:*` commands.
- Do not use `package.xml` or `--manifest` for routine CaseOps retrieve/deploy.
- Prefer `sf project retrieve start --metadata`, `sf project retrieve start --source-dir`, `sf project deploy start --source-dir`, and `sf project deploy start --metadata-dir`.

If a run discovers a durable, verified, reusable org fact, update the most specific selected topic file with one short bullet. Do not store secrets, raw access tokens, frontdoor links, or customer-private narrative.

---

## Step 5 — Retrieve relevant Production metadata [SUB-AGENT]

Spawn a sub-agent using **“Step 5 — Retrieve relevant Production metadata”** in **`references/sub-agent-prompts.md`**. Paste the Hypothesis into the prompt.

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

**Stop condition:** Once direct evidence confirms a Support-resolvable permission assignment, data update, or existing-config action, stop deep investigation. Do not continue into Apex/class/automation checks unless the evidence specifically points to Apex, Flow modification, validation rules, or another Engineering-owned artifact.

**Permission-set assignment hard stop:** If the fix is assigning an existing permission set that comparable users already have, and that permission set supplies the missing object/field access, stop there. Do not perform additional Apex class access checks unless the issue text, flow fault, or debug evidence explicitly names Apex/class access as the failure.

**Production write hard stop:** Normal pipeline runs must never execute Production data writes, permission-set assignments, deletes, Apex anonymous execution, or deploys. For Support-resolvable no-deploy actions, document the exact operator/admin action and validation plan only. Do not run `sf data create`, `sf data update`, `sf data delete`, or assignment commands against Production unless the operator explicitly starts a separate approved Production-write workflow.

**Routing:**
- Support-resolvable metadata changes continue to Steps 8-9 for Sandbox validation.
- Support-resolvable no-deploy admin actions (existing permission-set assignment, data correction, feature/config toggle) continue to Step 8, then create a no-deploy test report and skip Sandbox deploy in Step 9. These actions are operator instructions, not commands to execute in Production.
- Engineering-required changes continue to Steps 8-9 when a Sandbox proposal can be safely built and tested.

---

## Step 8 — Implement / Prepare Action [ORCHESTRATOR]

Propose and document the fix. For Support issues, this becomes the Production fix. For Escalation issues, this becomes the proposed solution to hand to Engineering.

Make local changes scoped to the issue only when a metadata/code candidate is required. Avoid unrelated refactors. Record changed files in `outputs/investigations/<KEY>.md`.

For no-deploy Support actions, do not create a metadata workspace attempt and do not execute the Production action. Document the exact admin/data action, why it is Support-resolvable, expected validation steps, and Production deploy state = **N/A**.

Before creating new metadata, confirm it does not already exist in Production (Step 5 existence check and **`references/safety-policy.md`**). Extend existing components when possible.

Update **`Solution Plan` → Production vs sandbox deployment state** in the investigation record: pre-fill what Production has vs what will be Sandbox-only, and the expected **Production deploy?** (**Yes — Gearset** / **No** / **N/A**). Refine after Step 9 with test evidence.

## Step 9 — Deploy, test, and iterate [SUB-AGENT OR NO-DEPLOY TEST REPORT]

Spawn this sub-agent after Step 8 only when there is a metadata/code candidate to deploy or a Sandbox-safe configuration change to test. Sandbox testing validates proposed metadata/code solutions so Engineering receives evidence-backed handoffs, not just hypotheses.

For no-deploy Support actions, do **not** spawn the deploy/test sub-agent. Create `outputs/test-reports/<KEY>.md` directly with:
- Root cause evidence from Production read-only checks.
- Exact admin/data action to perform, explicitly marked as **operator action not executed by CaseOps**.
- Validation steps after the operator applies the action.
- Production deploy required: **N/A**.

**Allowlist:** Read exported env var **`CASEOPS_SANDBOX_TARGET_ORG`**. If missing or empty, **STOP**. Only that org may receive deploys or mutating operations. See **`references/sub-agent-prompts.md`** — **”Step 9 — Deploy, test, and iterate”** for the full prompt and failure-loop behavior.

On **Fail:** revise hypothesis (Step 4), re-run Step 5 if needed (and Step 6 if more drilling required), re-implement (Step 8), re-run Step 9. Record iterations in `outputs/investigations/<KEY>.md`.

Before returning Fail, the Step 9 sub-agent must revert non-viable Sandbox changes from the attempt baseline and record the revert command/result in `outputs/test-reports/<KEY>.md`. The next iteration must use the next attempt directory number.

---

## Step 10 — Draft internal notes, Jira message, and escalation handoff (if needed) [SUB-AGENT]

Spawn a sub-agent using **”Step 10 — Draft internal notes and Jira message”** in **`references/sub-agent-prompts.md`**. Pass the test results from Step 9, or the no-deploy test report for Support admin/data actions.

**If Support-resolvable:** Drafts are ready for operator-controlled Production action via Gearset, standard change control, or manual admin/data correction. CaseOps does not execute Production writes in normal pipeline runs.

**If Engineering-escalation:** Create `outputs/engineering-escalations/<KEY>.md` using `assets/engineering-handoff-template.md` with:
- Problem location (from Step 6)
- Root cause (from Step 4)
- **Proposed solution** (from Step 9 test results: what was deployed in Sandbox and whether tests passed)
- Why it requires Engineering
- Sandbox test evidence

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

## Step 11 — Create or update the dated summary [ORCHESTRATOR]

Create or update the dated summary directly in the active Claude Code run after active issues complete Steps 3-10. Do not call deprecated Python orchestration paths.

Before writing the dated summary, check whether `outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md` already exists. If it exists, Read it and then Edit it. Use Write only when the dated summary file does not already exist.

---

**Output artifact:** `outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md` using `assets/issue-summary-template.md`.

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

## Step 12 — Inform the user [ORCHESTRATOR]

After all issues are processed and Step 11 summary is created, report back to stakeholders.

Report is generated inline during skill execution. Reference the dated summary file (`outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md`) and individual Jira message drafts (`outputs/jira-messages/<KEY>.md`).

---

**What to report per issue:**

- **Jira key and summary**
- **Root cause** (from Hypothesis + Step 6 confirmation)
- **Solution or escalation status** (Support-fixed / Engineering-escalated / On-hold pending customer response)
- **Production vs Sandbox:** 
  - What exists in Production (verified read-only)
  - What is Sandbox-only (after fix deployed)
  - **Production deploy required?** (Yes — Gearset / No / N/A)
  - Operator next step (e.g., "Run Gearset to promote to Production", "Deploy via standard change control")
- **Files or metadata changed** (list of Apex classes, Flows, fields, configs modified)
- **Sandbox target** (if applicable; reference CASEOPS_SANDBOX_TARGET_ORG)
- **Tests run and outcome** (from Step 9 test report)
- **Open risks or follow-up** (known issues, test gaps, manual verification needed)
- **Paths:** Internal notes (`outputs/internal-notes/<KEY>.md`), Jira message draft (`outputs/jira-messages/<KEY>.md`), dated summary (`outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md`)

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
