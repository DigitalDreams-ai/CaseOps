# Pipeline Framework Alignment Plan (2026-06-02)

## Purpose

This plan captures what we still need to change in CaseOps pipeline behavior so it is
stable for pilot use while respecting the existing Orchestrator/Sub-agent/Skill model.

The objective is not cosmetic changes. The objective is:

- fewer false-positive tags and unnecessary reruns,
- lower token/runtime cost per issue,
- deterministic reruns without replaying completed work,
- easier production readiness checks before each pilot session.

## Current baseline (already present)

CaseOps already has the following high-value pieces in place:

- 12-step orchestrator playbook with sub-agents for Steps 3, 5, 6, 9, and 10.
- Modern `sf` CLI-only retrieve/deploy policy (no routine `sfdx force:*`, no routine `package.xml`).
- Runtime preflight for Claude auth + Salesforce auth + SOQL availability.
- Separate metadata cache and workspace directories (`metadata-cache/`, `metadata-workspaces/`).
- Resume planning implemented in `app.py` and persisted as `outputs/pipeline-state/<KEY>.json`.
- Org-knowledge progressive disclosure and prompt trimming logic.
- Token usage extraction and log emission already wired into Claude stream processing.

Because these pieces exist, the work now should be **targeted hardening**, not rewrites.

## Decision: which changes are needed?

### 1) Make resume/skip decisions deterministic by content signatures

**Needed:** **Yes**

**Why:** The current planner relies heavily on file presence, file size, and mtimes.
That is effective, but noisy in practice when cache writes or touched timestamps make
completed work look stale. This can drive extra Claude calls and repeated metadata
walks.

**Change:**

- Add a compact, step-level signature in `pipeline-state` artifacts:
  - source summary hash (Jira key + updated timestamp),
  - artifact checksum for key files (`investigation`, `step4`, `test_report`, etc.),
  - workspace manifest hash (`metadata-workspace.json`).
- Mark steps `complete/pending/stale/block` based on signature mismatch rather than only
  timestamp/size heuristics.

**Gains:**

- materially reduces rerun work and token usage,
- improves reproducibility when operator runs are repeated after status-only edits,
- lowers “pipeline got slower” perception from avoidable recomputation.

**Worth doing:** **High**. This is the largest practical stability gain for ongoing pilot use.

---

### 2) Replace regex-inference tags with explicit state artifacts

**Needed:** **Yes**

**Why:** Current tag derivation still reads issue text heuristically in places
(`blocked`/`Data Only`/escalation indicators). That is fragile and has already produced
incorrect classification in edge cases.

**Change:**

- Persist authoritative routing and deployment outcome in machine-readable status files written
  by orchestrator steps (e.g., `outputs/pipeline-state/<KEY>.json`):
  - `routing = support_resolvable | engineering_required | on_hold`
  - `deliverable_type = metadata_candidate | no_deploy_admin | data_admin | blocked`
  - `production_deploy_required = yes | no | n/a`
- Gate UI/API tag derivation from these fields first, then fall back to file-level checks.
- Keep heuristic fallback only for backward compatibility with old historical artifacts.

**Gains:**

- eliminates false tags like “Data Only” on deploy-required issues,
- prevents “blocked” false positives from model prose,
- makes operator decisions consistent across UI and APIs.

**Worth doing:** **Very High**. Directly addresses the classification pain you reported and is
low implementation risk.

---

### 3) Add loop-control for Step 5/6/8/9 retry cycles

**Needed:** **Yes**

**Why:** Some run logs show repeated exploration loops even after evidence exists.
Without explicit caps and stop conditions, retries can become rabbit-hole heavy and cost
more tokens than needed.

**Change:**

- Add per-issue retry budget in the run state:
  - max metadata drill rounds (for Steps 5→6→8→9),
  - max failed deploy/test retries per attempt,
  - automatic transition to `on_hold` when the budget is exceeded.
- Log explicit reason codes:
  - `repeat_metadata`, `deploy_fail`, `no_candidate_delta`, `safe_stoppoint_hit`.

**Gains:**

- avoids unbounded runtime spikes,
- creates predictable bounded cost per issue,
- improves post-mortem quality (you get repeatable failure reasons).

**Worth doing:** **High**. This protects runtime and gives operators confidence during incidents.

---

### 4) Introduce lightweight run telemetry (step timings + token budget)

**Needed:** **Yes**

**Why:** You already asked for efficiency and token accounting visibility. Timing and token data
exist partially, but they are not currently stored as a durable, per-step metric surface.

**Change:**

- Persist `run_metrics` in the existing pipeline-state file:
  - start/end time per step,
  - wall-clock + token totals per step,
  - sub-agent call count,
  - pass/fail reason.
- Include a one-line end-of-run summary in logs with `issue`, `steps`, `total_time`,
  `token_estimate`, `cost_estimate` when available.

**Gains:**

- immediate visibility into regressions,
- easier right-sizing of `CASEOPS_CLAUDE_*` settings,
- supports pilot review and trend tracking.

**Worth doing:** **Yes**. High signal-to-noise for ops health.

---

### 5) Add explicit evaluator-optimizer checkpoints

**Needed:** **Yes**

**Why:** Anthropic describes an **Evaluator-Optimizer** loop for workflows with clear acceptance criteria:
an initial worker step produces an artifact, then a separate evaluator pass validates it before advancing.

**Change:**

- Add short, deterministic validator passes for:
  - Step 5 artifact quality (problem location confidence),
  - Step 6 hypothesis specificity vs evidence,
  - Step 9 test report quality (deploy/test evidence completeness),
  - Final Step 10 readiness (customer/internal message separation and escalation correctness).
- Add explicit `quality_gate` result in `pipeline-state`:
  - `pass`, `needs_rework`, `blocked`, `manual_review`.
- Only proceed when gate says pass; otherwise route back to the correct step with a bounded retry budget.

**Gains:**

- fewer weak/partial conclusions,
- fewer downstream false positives,
- clearer operator decision path when a run stalls.

**Worth doing:** **High**. This is the highest-confidence way to stop weak evidence from cascading into the wrong step.

---

### 6) Formalize routing as a typed decision stage

**Needed:** **Yes**

**Why:** Anthropic’s routing pattern fits this domain: classify the issue path before heavy work.
CaseOps currently has routing signals, but they are sometimes inferred late and inconsistently across artifacts.

**Change:**

- Add a dedicated routing step artifact:
  - `outputs/pipeline-state/<KEY>.json` fields:
    - `routing.path = support_resolvable | engineering_required | on_hold | unknown`
    - `routing.confidence = high | medium | low`
    - `routing.reason`
- Persist and re-use route for Step 7 gating, Step 9 branch behavior, and status/tag rendering.
- Require routing to be explicit after Step 6 and before Step 8.

**Gains:**

- deterministic branch behavior,
- lower chance of unnecessary code-deploy work on non-code fixes,
- simpler triage/priority handling.

**Worth doing:** **Very High**. Directly maps to the orchestrator design and improves consistency.

---

### 7) Strengthen context governance with cap/selection + compaction triggers

**Needed:** **Yes**

**Why:** Anthropic guidance on long-running systems calls out context growth, pagination, and summarization/compaction behaviors to prevent drift and token bloat.

**Change:**

- Define explicit context budgets for sub-agent prompts and outputs:
  - hard max on readback snippets,
  - deterministic truncation (e.g., 25k/50k token cap per artifact type),
  - short result schema per sub-agent step.
- Store only the compact summary + evidence IDs in context; keep raw evidence in files.
- Trigger automatic compact/restart of stale long-runs based on step duration and repeated output volume.

**Gains:**

- more stable outputs under multi-issue stress,
- reduced token bleed from logs/tool output,
- better chance of passing long loops without context degradation.

**Worth doing:** **High**. This is a practical safeguard against “pipeline feels slower over time.”

### 8) Tighten prompt chaining for high-risk transitions

**Needed:** **Yes**

**Why:** Anthropic’s prompt-chaining model works best where the output of one model step must be validated before the next can run correctly.

**Change:**

- For Step 4 → Step 5, Step 5 → Step 6, and Step 8 → Step 9, require typed mini-contracts:
  - required fields in each artifact,
  - machine-checkable section markers,
  - minimum confidence fields.
- If schema validation fails, do not continue; force a single corrective re-run of that step.

**Gains:**

- fewer silent step transitions on weak artifacts,
- predictable handoff between steps,
- fewer retries due to malformed intermediate notes.

**Worth doing:** **High** for reliability, especially with noisy issue inputs.

---

### 9) Add optional parallel evidence branches for independent checks

**Needed:** **Optional (pilot later)**

**Why:** Parallelization is useful when checks do not depend on each other (e.g., independent read-only validations).

**Change:**

- Parallelize independent evidence gathers only when safe:
  - org-accessibility checks (SOQL/auth sanity),
  - org-knowledge selection validation,
  - object/component existence prechecks.
- Keep serialization for mutation/deploy/test steps.

**Gains:**

- lower latency on some issues,
- better resource utilization on multi-issue runs.

**Worth doing:** **Medium**. Useful in aggregate but adds scheduling complexity.

---

### 10) Codify tool-first interfaces and bounded role permissions

**Needed:** **Medium-High (ongoing quality debt)**

**Why:** Anthropic’s tooling guidance emphasizes clean, primary action tools with bounded permissions per role.

**Change:**

- Document and enforce per-step tool contracts:
  - retrieve/search tools,
  - metadata manipulation tools,
  - Salesforce-safe test/deploy tools.
- Keep toolsets explicit for sub-agent roles (fewer broad permissions, narrower command surface).
- Maintain role/tool allowlists per pipeline step.

**Gains:**

- safer execution profile,
- easier review of why a tool was called,
- reduced accidental drift into unsupported command families.

**Worth doing:** **Medium**. Good long-term governance and safety hardening.

---

### 11) Keep current architecture: no package.json/legacy command migration

**Needed:** **No (already done)**

**Why:** The code is already enforcing modern `sf`-only flow and already rejects `run_pipeline.py`.

**Plan:** No pipeline behavior change required here. Only document remaining legacy notes as archived.

**Gains:** avoid churn and unnecessary risk.

**Worth doing:** **Low / not needed now**.

---

## Work package and sequencing

### Phase 1 — Pilot Hardening (1-2 sessions)

1. Implement deterministic signature-based resume planner (Item 1).
2. Add explicit pipeline-state fields for routing/outcome and make UI/API consume them (Item 2).
3. Add capped Step 5/6/9 loop budget (Item 3).
4. Add evaluator-optimizer quality gates (Item 5).

### Phase 2 — Operator Confidence (same sprint)

5. Add per-step timing + token usage metrics in `pipeline-state` and issue summary (Item 4).
6. Add regression tests that assert:
   - `Data Only` requires explicit no-deploy evidence + no production deploy intent,
   - no rerun when unchanged inputs + unchanged signatures.
7. Add typed artifact contracts for high-risk step transitions (Item 8).

### Phase 3 — Process Maturity

8. Add this file link to `docs/README.md` and `docs/CASEOPS_ENHANCEMENT_PLAN.md` as the pilot runtime hardening plan.
9. Add typed quality gates and route/state fields to docs and operator checklists.
10. Pilot optional parallel evidence branches and tool-role hardening (Items 9/10), then promote if stable.

### Ongoing (follow-up)

- Regularly trim stale docs patterns and keep the framework evidence (plan + artifacts) current.
- Re-run a bounded regression set after each release: `HEAL-33628`, `HEAL-33659`, `HEAL-33979`, and one clean synthetic case.

## Value proposition summary (expected impact)

- **Reliability:** high (fewer incorrect tags and better run-state consistency).
- **Cost:** high (fewer reprocesses and fewer repeated sub-agent calls).
- **Pilot readiness:** high (predictable reruns, bounded loops, clearer failure surfaces).
- **Risk:** low-to-medium (all changes stay within current orchestration model and do not replace the existing
  sub-agent architecture).

## Open questions before implementation

1. Should the run-metric retention policy be “all runs for 7 days” or “all runs for 30 days”?
2. Should blocked-on-budget issues auto-post as `on-hold` in UI with optional manual override?
3. Which issues should be included in the first pilot regression sweep (`HEAL-*` + synthetic fixtures)?
4. Should evaluator-optimizer be hard-blocking (must pass) for all critical handoffs or only for Step 9/10?
5. What parallel branch width is safe for the environment (1–2 workers vs more)?

If you approve, next step is a concrete patch sequence in `app.py` with the same
`pipeline-state` and file contracts already used today, then execution on the known
problem issues (for example, `HEAL-33628`, `HEAL-33979`, and recent regressions) to confirm no false positives.
