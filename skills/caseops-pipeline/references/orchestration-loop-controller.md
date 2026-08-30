# CaseOps Orchestration Loop Controller

This reference defines the authoritative execution loop for CaseOps pipeline runs.

## Binding Queue Scope

- Process issues assigned to the configured Jira user.
- Skip Closed, Resolved, Canceled, Cancelled, Hold, and On Hold issues.
- Treat every other Jira status, including the legacy `Escalated to Engineering` status, as active pipeline work.
- Do not create an Engineering escalation route, handoff, state, tag, or terminal disposition.
- A concrete external dependency may put an issue on hold. Difficulty, code ownership, metadata type, or failed attempts are not external dependencies.

## One Active Route

Every active issue uses `routing.path=full_pipeline` and proceeds through the same graph:

1. Analyze the issue.
2. Build and validate the problem hypothesis.
3. Retrieve relevant Production metadata read-only.
4. Identify the exact problem location.
5. Confirm the solution path.
6. Implement or prepare the candidate solution.
7. Deploy and test in Sandbox, or perform the declared no-deploy validation.
8. Draft the issue brief, internal notes, and Jira message.
9. Update the dated summary and checkpoints.

Production mutation remains prohibited unless the operator provides valid, issue-scoped temporary Production approval. Without that approval, CaseOps prepares and validates the solution but leaves the Production action to the operator.

## Required Markers

Emit these compact markers so queue progress can be measured deterministically:

- `STEP_<N> <KEY>` when a step starts.
- `STEP_<N> <KEY> COMPLETE` only after the step checkpoint and required artifacts are durable.
- `STEP_<N> <KEY> RETRY <attempt>/<limit>: <reason>` for bounded retries.
- `HOLD <KEY>: <external dependency>` when an external dependency blocks progress.
- `END <KEY> disposition=<validated|data-only|blocked|in-progress>` when processing ends.

Do not use escalation markers or dispositions.

## Orchestration Pseudocode

```text
for issue in assigned_issues:
    if jira_status_is_closed_or_resolved(issue):
        record_skip(issue, "closed/resolved")
        continue

    if jira_status_is_hold(issue):
        record_skip(issue, "hold")
        continue

    state = load_or_initialize_state(issue)
    normalize_legacy_route(state, to="full_pipeline")

    run_step_3_analysis(issue, state)
    run_step_4_hypothesis(issue, state)

    for attempt in range(1, 4):
        run_step_5_production_metadata(issue, state, attempt)
        run_step_6_problem_location(issue, state, attempt)
        if problem_location_is_specific_and_evidence_backed(state):
            break
    else:
        record_blocker(issue, "Problem location was not proven within the retry budget")
        finish(issue, disposition="blocked")
        continue

    persist_routing(issue, path="full_pipeline")

    for attempt in range(1, 4):
        run_step_8_candidate_solution(issue, state, attempt)
        run_step_9_sandbox_or_no_deploy_validation(issue, state, attempt)
        if validation_passed(state):
            break
        revise_hypothesis_and_candidate(issue, state)
    else:
        record_blocker(issue, "Candidate validation did not pass within the retry budget")
        finish(issue, disposition="blocked")
        continue

    run_step_10_outputs(issue, state)
    validate_required_outputs(issue)
    update_summary_and_checkpoints(issue, state)
    finish(issue, disposition=derive_supported_disposition(state))
```

## Diagnosis Loop

Steps 5 and 6 may repeat up to three times when evidence is incomplete. Each retry must state what evidence is missing and narrow the next retrieval. A valid problem location names:

- the problem type;
- the specific artifact or data object;
- the location within that artifact or data path;
- the observed failure point and supporting evidence.

If those facts cannot be established within the retry budget, preserve all evidence and mark the issue blocked with a visible reason. Do not convert uncertainty into an Engineering escalation.

## Solution And Validation Loop

Steps 8 and 9 may repeat up to three times. Each attempt must use an issue-scoped workspace and preserve its result. Failed Sandbox attempts must be reverted before the next attempt.

The candidate may be metadata, code, configuration, access, data/admin work, a customer answer, or a no-change conclusion. The ownership category does not change the route.

When a safe test cannot run because of a real external dependency, record the dependency and mark the issue blocked. When no deployment is required, Step 9 records the applicable read-only or behavioral validation instead of pretending a Sandbox deploy occurred.

## Step 10 Output Contract

For every processed issue, Step 10 creates and validates exactly these active deliverables:

- `outputs/issue-briefs/<KEY>.md`
- `outputs/internal-notes/<KEY>.md`
- `outputs/jira-messages/<KEY>.md`

Historical files under `outputs/engineering-escalations/` are read-only evidence. Never create or update them.

If output validation fails, retry Step 10 with the validation errors. If the bounded retry fails, preserve the invalid artifact for diagnosis, record a blocker, and leave the issue incomplete. Do not switch routes.

## Allowed Dispositions

- `validated`: the candidate solution passed Sandbox or declared no-deploy validation.
- `data-only`: the confirmed solution is a Production data/admin action that CaseOps did not perform without explicit Production approval.
- `blocked`: a specific external dependency, missing evidence, or exhausted bounded validation loop prevents completion.
- `in-progress`: work ended before reaching a supported terminal disposition.

Jira workflow status is not a substitute for CaseOps evidence. In particular, legacy `Escalated to Engineering` is treated as active input, not an outcome.

## Queue Completion

At queue end, report:

- counts for closed/resolved and Hold skips;
- counts for validated, data-only, blocked, and in-progress results;
- the exact stop cause when the queue stalls, reaches its pass limit, receives a stop request, or encounters issue failures;
- each incomplete issue's next step and blocker.

The queue must stop when no issue advances during a pass or when the configured pass limit is reached. It must not repeatedly run unchanged failed work.

## Safety Invariants

1. Production is read-only unless issue-scoped temporary approval is valid for the requested action.
2. Sandbox deploy/test work is issue-scoped and reversible.
3. Profile permissions are never modified; use permission sets or document the required admin action.
4. Closed/resolved and Hold issues are never active queue work.
5. Historical escalation artifacts never control current routing, tags, or completion.
6. Retries are bounded and evidence-driven.
7. Each fact has one durable owner: pipeline state for execution, investigation for evidence, test report for validation, and Step 10 files for their declared audiences.
