# Pipeline Framework Success Plan

Date: 2026-06-02

Source plan: `docs/PIPELINE_FRAMEWORK_ALIGNMENT_PLAN.md`

## Executive Decision

The plan is worth doing, but only if it is implemented as a reliability program, not as
a broad architecture rewrite.

The highest-value work is:

1. Deterministic resume/state signatures.
2. Explicit machine-readable routing and outcome state.
3. Bounded retry/loop control.
4. Evaluator gates for high-risk handoffs.
5. Step-level telemetry.

Do those first. Defer optional parallelism and broad tool-framework work until the
pipeline is consistently boring on known problem issues.

## Tactics Applied

These are the planning tactics that consistently work in real agentic systems and
software pilot programs:

1. **Start with measurable failure modes.**
   A plan should begin from observed failures, not architectural ideals.

2. **Convert prose decisions into machine-readable state.**
   If a UI tag, resume decision, route, or deploy status matters, it cannot live only
   in markdown prose.

3. **Use thin vertical slices.**
   Ship one complete behavior change through UI, API, state file, docs, and regression
   checks before starting the next.

4. **Put gates between model steps.**
   The output of one model step becomes the input to another. Bad handoffs compound.
   Gate the risky transitions.

5. **Bound every loop.**
   Agent loops need explicit retry budgets, stop reasons, and handoff behavior.

6. **Instrument before optimizing.**
   Add step timing, token usage, and reason codes before trying to tune prompts.

7. **Treat context as a product surface.**
   Do not rely on "Claude will figure it out." Control what context is selected,
   capped, summarized, and carried forward.

8. **Prefer deterministic code for policy.**
   Let the model investigate and summarize. Let code decide whether something is
   current, blocked, data-only, deploy-required, or allowed.

9. **Create acceptance tests from real failures.**
   Regression tests should cover the exact issues that created doubt, not synthetic
   happy paths only.

10. **Defer complexity until evidence says it pays.**
    Parallel branches, MCP boundaries, and advanced tool role separation are useful,
    but only after the core state machine is trustworthy.

## Grounding From Current Guidance

This plan follows current agent-workflow guidance in three concrete ways:

- Anthropic recommends simple, composable patterns and only adding complexity when it
  improves outcomes. CaseOps should harden the existing workflow instead of replacing it.
  Reference: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic's relevant patterns are prompt chaining, routing, parallelization,
  orchestrator-workers, and evaluator-optimizer. CaseOps already uses orchestrator-workers;
  the missing pieces are typed routing, hard gates, and bounded evaluator loops.
  Reference: https://www.anthropic.com/engineering/building-effective-agents
- Production agent practice emphasizes owning prompts, context, control flow, execution
  state, pause/resume, focused agents, and compacting errors into context. CaseOps should
  express those as state files, capped context, and resumable steps.
  Reference: https://github.com/humanlayer/12-factor-agents

## Success Metrics

The plan succeeds when these are true across the regression issue set:

| Metric | Target |
| --- | --- |
| False `Data Only` tags | 0 |
| False `Blocked` tags from model prose | 0 |
| Rerun of unchanged completed issue | No Claude subprocess needed, or only Step 12 summary |
| Step indicator accuracy | Shows current next step, not stale Step 3/12 |
| Unbounded Step 5/6/9 loops | 0 |
| End-of-run token visibility | Present for every Claude-backed run when available |
| Preflight failure clarity | One actionable root cause, no frontdoor/API confusion |
| Production write attempts during normal pipeline | 0 |

Regression issue set:

- `HEAL-33628`
- `HEAL-33659`
- `HEAL-33763`
- `HEAL-33979`
- One synthetic unchanged already-complete issue
- One synthetic deploy-required permission metadata issue
- One synthetic no-deploy permission assignment issue

## Phase 1: Make State Authoritative

### Goal

Stop deriving important UI/runtime behavior from loose markdown prose.

### Changes

Add explicit state fields to `outputs/pipeline-state/<KEY>.json`:

```json
{
  "schema_version": 2,
  "routing": {
    "path": "support_resolvable",
    "confidence": "high",
    "reason": "Existing permission set assignment supplies missing access."
  },
  "deliverable": {
    "type": "metadata_candidate",
    "production_deploy_required": "yes",
    "production_deploy_method": "gearset",
    "no_deploy_reason": ""
  },
  "quality_gates": {
    "step_6_problem_location": "pass",
    "step_9_test_report": "pass",
    "step_10_message_separation": "pass"
  },
  "signatures": {
    "jira_source": "sha256:...",
    "investigation": "sha256:...",
    "hypothesis": "sha256:...",
    "test_report": "sha256:...",
    "metadata_workspace": "sha256:..."
  }
}
```

### Acceptance

- UI tags read state first, heuristics second.
- `Data Only` requires `deliverable.production_deploy_required` to be `no` or `n/a`.
- `Escalated to Engineering` tag reflects Jira status only.
- `Needs Escalation` reflects CaseOps handoff state only.
- `Blocked` requires explicit `routing.path = on_hold` or explicit blocker state.

### Stop Rule

Do not proceed to Phase 2 until the known tag regressions are fixed by state, not by
adding more regex exceptions.

## Phase 2: Deterministic Resume Planner

### Goal

Make reprocess cheap and trustworthy.

### Changes

- Add content signatures for the source issue and durable artifacts.
- Mark each step complete only when its expected inputs and outputs match.
- Emit concise `resume-skip` lines without spawning Claude for completed steps.
- Add a `why_next_step` field for operator visibility.

### Acceptance

- Running Reprocess All on unchanged completed issues does not rerun Steps 3-10.
- Touching only a summary file does not invalidate metadata work.
- Changing Jira source invalidates Step 3 and downstream artifacts.
- Changing candidate metadata invalidates Step 9 and Step 10 only.

### Stop Rule

If unchanged issues still spawn full Claude runs, pause implementation and fix planner
state before continuing.

## Phase 3: Gates and Loop Control

### Goal

Prevent weak evidence and repeated exploration from moving forward.

### Changes

Add hard gates after:

- Hypothesis
- Step 6 problem location
- Step 9 test report
- Step 10 message separation

Each gate returns:

```json
{
  "result": "pass",
  "confidence": "high",
  "reason": "Problem location identifies artifact, failure point, and evidence.",
  "retry_to_step": null
}
```

Add loop budgets:

| Loop | Budget | Failure Result |
| --- | --- | --- |
| Step 5/6 metadata drill | 2 refinement rounds | `on_hold: insufficient evidence` |
| Step 8/9 deploy-test | 2 failed attempts | `on_hold: candidate failed validation` |
| Same failed command pattern | 2 repeats | force replan |

### Acceptance

- Logs show reason codes for rework.
- Failed Sandbox attempts are reverted before retry.
- No issue stays on Step 5 without a changing reason code.
- Operator can see why the pipeline stopped.

### Stop Rule

If a loop repeats the same command family with no new evidence twice, stop and mark
manual review.

## Phase 4: Telemetry Before Optimization

### Goal

Make performance visible enough to tune.

### Changes

Persist per-run metrics:

```json
{
  "run_metrics": {
    "started_at": "2026-06-02T00:00:00Z",
    "ended_at": "2026-06-02T00:10:00Z",
    "steps": {
      "3": {"seconds": 52, "input_tokens": 12000, "output_tokens": 1800},
      "5": {"seconds": 240, "input_tokens": 19000, "output_tokens": 3200}
    },
    "total_tokens": 36000,
    "total_cost_usd": 1.23
  }
}
```

### Acceptance

- End of every run logs token usage when available.
- Pipeline-state contains step durations.
- Regression review can compare current vs previous runtime.

### Stop Rule

Do not tune prompts or add parallelization until there is a baseline for timing and
token usage.

## Phase 5: Context Governance

### Goal

Prevent long-run context bloat and repeated relearning.

### Changes

- Define max context sizes per artifact type.
- Inject selected org knowledge only.
- Summarize large artifacts into small evidence packets.
- Store raw metadata and long logs on disk, not in prompts.
- Add a `context_packet` section to the resume plan with selected files and byte/token
  estimates.

### Acceptance

- Sub-agent prompts contain only issue-relevant org knowledge.
- Large logs are never pasted wholesale into the operator log.
- Repeated Salesforce CLI behavior is handled by helper scripts or org knowledge.

### Stop Rule

If a prompt contains full playbook text, raw metadata dumps, or long logs, treat it as
a bug.

## Phase 6: Optional Parallelism

### Goal

Improve latency only after the deterministic pipeline is stable.

### Candidate Parallel Work

- Read-only object existence checks.
- Org knowledge selection validation.
- Independent SOQL evidence queries.
- Multi-issue processing with worker limits.

### Do Not Parallelize

- Sandbox deploy/test attempts.
- Metadata workspace writes for the same issue.
- Any action that could mutate Salesforce or Jira.

### Acceptance

- Parallel branches write separate evidence files.
- Aggregator summarizes results without loading all raw outputs.
- Failures are isolated to their branch.

### Stop Rule

If parallelism makes logs or state harder to reason about, revert it.

## Implementation Order

1. Add state schema version 2.
2. Add deterministic signature helpers.
3. Update tag derivation to consume state first.
4. Add route and deliverable writers during pipeline prompt construction/results.
5. Add gate validators for Step 6, Step 9, and Step 10.
6. Add loop budget counters.
7. Add step timing and token persistence.
8. Add regression fixtures/tests.
9. Run the regression issue set locally.
10. Sync to NAS, restart, and run the same issue set in Docker.

## Tests To Add

### Unit tests

- Signature unchanged means step remains complete.
- Jira updated timestamp invalidates downstream steps.
- `Data Only` is false when production deploy is required.
- `Blocked` is false for prose like "I am completely blocked."
- Jira escalated status is the only source of the `Escalated to Engineering` tag.

### Integration tests

- `Reprocess All` skips unchanged completed issues.
- Forced reprocess of pre-escalated issue runs full pipeline safely.
- Step 5 timeout or repeated failed query produces `on_hold` with reason.
- No-deploy permission assignment skips Sandbox deploy and writes a test report.
- Deploy-required permission metadata is not tagged `Data Only`.

### Docker validation

- `/api/settings/status` remains fast.
- Claude and Salesforce preflight run with `HOME=/home/caseops`.
- Appdata paths are under `/volume1/docker/appdata/caseops/instance1/outputs`.
- No runtime output is written under `/volume1/docker/stacks/caseops/instance1`.

## Risks

| Risk | Mitigation |
| --- | --- |
| State schema drift breaks old issues | Keep fallback readers for historical artifacts |
| Gates are too strict and block useful runs | Start with warning mode, then enforce on Step 9/10 |
| More state increases complexity | Keep state fields small and typed |
| Parallelism hides failure causes | Defer until core telemetry is stable |
| Token metrics are incomplete from some Claude outputs | Store `unavailable` explicitly and still record duration |

## Definition Of Done

This plan is complete when:

- Known false tags are gone.
- Unchanged reprocessing is fast and avoids unnecessary Claude work.
- Every run has a durable state file explaining next step and why.
- Loops stop with useful reason codes.
- Token and timing data are visible per issue.
- Docker behavior matches local behavior.
- The pilot operator can trust the issue card without opening logs first.

## First Patch Scope

The first implementation patch should be deliberately narrow:

1. Add schema version 2 fields to `pipeline-state`.
2. Add signature helpers.
3. Update tag derivation to prefer state.
4. Add regression tests for `Data Only`, `Blocked`, and escalation tags.

That patch should not include parallelism, MCP changes, or broad prompt rewrites.
