# Codex Prompt: Implement The CaseOps Pipeline Success Plan With Subagents

Use this prompt in a fresh Codex session when you want the agent to implement the remaining work in:

`docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`

---

## Prompt To Give Codex

You are Codex working in the CaseOps repository.

Your objective is to implement all remaining work in:

`docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`

Treat that file as the source of truth. Read it first. Re-read it before each phase. Every decision, edit, test, and validation must map back to a phase, acceptance criterion, stop rule, or definition of done in that plan.

## Core Operating Rules

1. Do not freewheel. Continually reference `docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`.
2. Use subagents for focused discovery, implementation review, test planning, and validation.
3. Keep the parent Codex agent as the orchestrator. The parent owns final integration, sequencing, risk decisions, and the final verification summary.
4. Subagents must return concise results with file references, risks, and recommended edits. They must not dump large file contents.
5. If any subagent is unsure, it must ask itself exactly: **"What would a Salesforce/Anthropic architect do?"** Then it must make the conservative architecture-quality decision and explain it.
6. Do not implement broad rewrites. Use thin vertical slices.
7. Do not add regex exceptions when the plan calls for machine-readable state.
8. Do not use Production Salesforce writes, Jira writes, or destructive Git commands.
9. Do not use frontdoor/magic links for API, SOQL, retrieve, deploy, or tests.
10. Do not use legacy `sfdx force:*`, routine `package.xml`, or routine `--manifest`.
11. Use modern `sf` CLI only for Salesforce CLI work.
12. Do not sync to NAS, rebuild Docker, restart Docker, or mutate remote deployment unless the operator explicitly asks for that step in the current conversation.

## Required First Actions

1. Read `docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`.
2. Read `app.py`, `templates/index.html`, `templates/settings.html`, and relevant files under `skills/jira-salesforce-fix-pipeline/`.
3. Identify current implementation gaps against the plan.
4. Create a short execution checklist grouped by the plan phases:
   - Phase 1: authoritative state
   - Phase 2: deterministic resume planner
   - Phase 3: gates and loop control
   - Phase 4: telemetry
   - Phase 5: context governance
   - Phase 6: optional parallelism only after stability
5. Start with the plan's "First Patch Scope":
   - Add schema version 2 fields to `pipeline-state`.
   - Add signature helpers.
   - Update tag derivation to prefer state.
   - Add regression tests for `Data Only`, `Blocked`, and escalation tags.

## Subagent Strategy

Spawn subagents only when their work is separable and their result can be summarized.

Do not spawn a subagent with vague instructions like "review the codebase." Every subagent must receive:

- the source plan path,
- the exact phase or acceptance criterion it owns,
- files it should inspect,
- what it must return,
- what it must not do,
- the required uncertainty question.

Use this pattern:

```text
Subagent task:
Read docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md first.
Focus only on <phase / acceptance criterion>.
Inspect <specific files>.
Return:
- current behavior,
- gap against the plan,
- recommended implementation,
- risks,
- tests to add,
- file references.
Do not edit files unless explicitly assigned.
If unsure, ask: "What would a Salesforce/Anthropic architect do?" Then choose the conservative path.
```

## Required Subagents

### Subagent 1: State Schema And Tagging Auditor

Purpose:
Map every issue tag and pipeline state decision to the plan's authoritative state model.

Inspect:

- `app.py`
- `templates/index.html`
- any API routes that return issue flags/tags
- any state files under `outputs/pipeline-state/` if present

Return:

- where `Data Only`, `Blocked`, `Escalated to Engineering`, `Needs Escalation`, and progress state are currently derived,
- which parts are heuristic,
- exact fields needed from schema version 2,
- recommended migration/fallback behavior for historical issues,
- tests required.

Must enforce:

- Jira status is the only source for the actual `Escalated to Engineering` tag.
- CaseOps handoff state is separate from Jira status.
- `Data Only` requires explicit no-deploy or N/A deploy state.
- `Blocked` requires explicit blocker/on-hold state, not model prose.

### Subagent 2: Resume Planner And Signature Auditor

Purpose:
Map the current resume planner to deterministic content signatures.

Inspect:

- `app.py`
- existing `_build_pipeline_resume_plan` and related helpers
- `outputs/pipeline-state/` structure if available

Return:

- current resume logic,
- where mtimes/file sizes are used,
- proposed `sha256` signature helpers,
- invalidation rules for Jira source, investigation, Step 4, test report, and metadata workspace,
- tests required to prove unchanged issues skip Steps 3-10.

Must enforce:

- unchanged completed issues should not spawn full Claude runs.
- changed Jira source invalidates Step 3 and downstream.
- changed candidate metadata invalidates Step 9 and Step 10 only.

### Subagent 3: Gates And Loop-Control Designer

Purpose:
Design the smallest implementable evaluator gates and loop budgets.

Inspect:

- `app.py`
- `skills/jira-salesforce-fix-pipeline/SKILL.md`
- `skills/jira-salesforce-fix-pipeline/references/workflow.md`
- `skills/jira-salesforce-fix-pipeline/references/orchestration-loop-controller.md`

Return:

- where gates should be computed in code vs prompt,
- exact `quality_gates` state shape,
- loop budget counters,
- failure reason codes,
- how to prevent repeated Step 5/6/9 loops,
- tests required.

Must enforce:

- failed Sandbox attempts are reverted before retry.
- repeated same failed command pattern forces replan/manual review.
- no issue stays on Step 5 without a changing reason code.

### Subagent 4: Telemetry And Log Auditor

Purpose:
Implementability review for per-step timing and token metrics.

Inspect:

- `app.py`
- pipeline log streaming functions
- Claude stream/token usage functions
- API routes that expose pipeline logs/status

Return:

- where token usage is already captured,
- how to persist run metrics into `pipeline-state`,
- how to associate metrics with step numbers,
- how to keep logs concise,
- tests required.

Must enforce:

- every Claude-backed run should show token usage when available.
- every issue state file should record run duration and step timings when available.
- missing token data should be stored as unavailable, not guessed.

### Subagent 5: Context Governance Auditor

Purpose:
Reduce context bloat and repeated relearning.

Inspect:

- `app.py`
- org-knowledge prompt construction
- Claude prompt construction
- tool-result/log suppression helpers
- skill reference prompts

Return:

- where full playbooks/logs/metadata might enter prompt or operator logs,
- proposed context caps,
- proposed `context_packet` shape,
- how to keep selected org knowledge narrow,
- tests or manual checks required.

Must enforce:

- no wholesale playbook dumps in operator logs.
- no raw metadata dumps in prompts unless explicitly scoped.
- org knowledge is selected, not bulk-read.

### Subagent 6: Regression Test Planner

Purpose:
Turn the plan's success metrics into tests.

Inspect:

- repo test structure, if any
- `app.py`
- current fixtures or sample pipeline artifacts
- known local logs: `HEAL-33628_pipelineLogs.txt`, `HEAL-33659_pipelineLogs.txt` when useful

Return:

- test framework recommendation based on existing repo patterns,
- unit tests to add,
- integration tests to add,
- synthetic fixture files needed,
- commands to run locally.

Must include tests for:

- false `Data Only`,
- false `Blocked`,
- Jira escalated status vs CaseOps handoff,
- unchanged reprocess skip,
- Step 5 loop budget/on-hold reason.

### Subagent 7: Final Reviewer

Purpose:
Review the completed implementation before final response.

Inspect:

- changed files only,
- `docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`,
- test output,
- any known gaps.

Return:

- findings ordered by severity,
- acceptance criteria still unmet,
- tests not run,
- whether implementation matches the plan,
- whether any decision should be revisited by asking: **"What would a Salesforce/Anthropic architect do?"**

## Implementation Rules For The Parent Codex Agent

The parent agent must:

1. Run subagents in batches only when their work is independent.
2. Integrate subagent findings into a single concrete patch plan.
3. Use `apply_patch` for manual edits.
4. Avoid touching unrelated files.
5. Preserve user/NAS/appdata path rules.
6. After each phase, update the checklist and run targeted validation.
7. Keep changes local unless the operator explicitly asks for NAS sync/restart/rebuild.
8. Never mark the work complete until the plan's definition of done is honestly satisfied or remaining blockers are clearly listed.

## Preferred Implementation Sequence

### Patch 1: State Schema + Tag Derivation

Implement:

- schema version 2 defaults,
- state read/write helpers,
- route/deliverable fallback extraction,
- tag derivation from state first,
- historical fallback second.

Validate:

- `Data Only` false when deploy required,
- `Blocked` false for "I am completely blocked",
- `Escalated to Engineering` only from Jira status,
- `Needs Escalation` only from CaseOps handoff.

### Patch 2: Signatures + Resume Planner

Implement:

- `sha256` helpers,
- source/artifact/workspace signatures,
- signature-aware step completeness,
- `why_next_step`,
- concise `resume-skip` behavior.

Validate:

- unchanged completed issue skips Steps 3-10,
- Jira source change invalidates downstream,
- candidate change invalidates Step 9/10 only.

### Patch 3: Gates + Loop Budgets

Implement:

- gate state structure,
- Step 6/9/10 validators,
- retry counters,
- reason codes,
- manual review/on-hold stop behavior.

Validate:

- repeated same failure stops,
- Step 5 cannot loop silently,
- failed candidate requires revert evidence before next attempt.

### Patch 4: Telemetry

Implement:

- run timing,
- per-step timing when step markers are observed,
- token usage persistence,
- unavailable token handling.

Validate:

- final logs include token usage when available,
- state file includes timing metrics.

### Patch 5: Context Governance

Implement:

- context caps,
- context packet metadata,
- stricter log/prompt suppression for large artifacts,
- org-knowledge selected-file accounting.

Validate:

- no full playbook or raw metadata dumps,
- selected org knowledge stays issue-relevant.

### Patch 6: Optional Parallelism

Only implement after Patches 1-5 pass.

Implement only safe read-only branch work. Do not parallelize mutation/deploy/test for the same issue.

## Required Final Verification

Before final response, run the most relevant tests available. At minimum:

- syntax/import check for edited Python,
- targeted unit tests if test framework exists,
- manual or scripted checks for tag derivation,
- resume planner dry-run for at least one known issue,
- review changed files for stale legacy references.

If tests cannot run, explain exactly why and what risk remains.

## Required Final Response Format

Return:

- what was implemented,
- which plan phases are complete,
- tests run and results,
- remaining work by phase,
- any blockers,
- whether NAS sync/restart/rebuild is needed or intentionally not done.

Do not claim pilot readiness unless the success metrics in `docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md` have been validated.

## Source Guidance Used To Shape This Prompt

This prompt is intentionally structured around current effective agent implementation tactics:

- Keep the orchestrator in charge of sequencing and synthesis.
- Use subagents for focused context-isolated work.
- Make subagents return summaries with file references.
- Use prompt chaining with gates.
- Use routing and evaluator-optimizer loops where the plan has clear acceptance criteria.
- Keep execution state in files so runs can pause/resume.
- Prefer deterministic code for policy decisions.

Relevant references:

- Anthropic, Building Effective Agents: https://www.anthropic.com/engineering/building-effective-agents
- Claude Code subagents documentation: https://code.claude.com/docs/en/sub-agents
- 12-Factor Agents: https://github.com/humanlayer/12-factor-agents
