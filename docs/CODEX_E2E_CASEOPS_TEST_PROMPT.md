# Codex Prompt: End-To-End CaseOps Browser And Pipeline Validation

Use this prompt only after the implementation work in:

`docs/PIPELINE_FRAMEWORK_SUCCESS_PLAN.md`

is complete and locally verified.

## Objective

Test CaseOps end to end in a Chrome Dev browser, identify every issue, fix all bugs/gaps/errors/timeouts, and repeat until CaseOps runs smoothly.

After browser and runtime validation succeeds, run the full CaseOps pipeline only for issues tagged `Not Triaged`, watch the run, and fix any CaseOps bugs, UI errors, path errors, timeouts, pipeline-state errors, progress-display errors, or logging errors found during the run.

## Absolute Safety Rules

These are non-negotiable:

1. **NEVER write to Jira.**
2. **NEVER modify Jira issue status, comments, fields, assignee, tags, or metadata.**
3. **NEVER write to Salesforce Production.**
4. **NEVER deploy, update data, assign permissions, run mutating Apex, or run any mutating command against the Production alias from `CASEOPS_PRODUCTION_READ_ORG`.**
5. **The org alias in `CASEOPS_PRODUCTION_READ_ORG` is read-only.**
6. **Do not use frontdoor/magic links for API, SOQL, retrieve, deploy, or tests.**
7. **Do not use legacy `sfdx force:*`, routine `package.xml`, or routine `--manifest`.**
8. **Do not sync to NAS, restart Docker, rebuild Docker, or mutate remote deployment unless Sean explicitly asks in the current conversation.**

If there is any uncertainty, ask yourself:

**"What would Sean's Salesforce/Anthropic architect do?"**

Then choose the conservative path that prevents Jira writes and Production writes.

## Browser Testing Scope

Use Chrome Dev browser automation to validate:

- CaseOps loads successfully.
- Settings page loads quickly.
- Settings status does not block initial UI load.
- Issue list renders.
- Issue detail view renders.
- Issue tags are correct and mutually consistent.
- Pipeline log loads.
- Copy pipeline log button works.
- Step indicator updates accurately.
- Force Reprocess only appears when Jira status is `Escalated to Engineering`.
- `instruction-panel`, `detail-actions`, `tabs`, and `content-area` layout behave correctly on desktop.
- Canned messages save to the correct appdata path.
- No runtime output is written into the stack/source directory.
- No stale `run_pipeline.py` calls appear.

## Pipeline Validation Scope

Only after browser/runtime checks pass:

1. Identify issues tagged `Not Triaged`.
2. Run the full CaseOps pipeline for those issues.
3. Watch logs continuously.
4. Stop/fix only CaseOps problems:
   - app crashes,
   - bad paths,
   - stale state,
   - incorrect tags,
   - progress indicator stuck,
   - unexpected timeouts,
   - invalid `sf` command usage,
   - loops without changing reason codes,
   - bad log noise,
   - missing token/step metrics.

Do not stop only because an issue needs normal Salesforce/Jira human action. Stop only if CaseOps itself is malfunctioning or if it attempts a forbidden write.

## Forbidden Commands And Actions

Never run commands that write to the Production alias from `CASEOPS_PRODUCTION_READ_ORG`, including but not limited to:

- `sf project deploy ... -o "$CASEOPS_PRODUCTION_READ_ORG"`
- `sf data create ... -o "$CASEOPS_PRODUCTION_READ_ORG"`
- `sf data update ... -o "$CASEOPS_PRODUCTION_READ_ORG"`
- `sf data delete ... -o "$CASEOPS_PRODUCTION_READ_ORG"`
- `sf apex run ... -o "$CASEOPS_PRODUCTION_READ_ORG"`
- permission assignment commands against `CASEOPS_PRODUCTION_READ_ORG`
- any REST call that mutates Production

Never call Jira write APIs:

- comment creation,
- status transitions,
- field updates,
- assignee changes,
- issue edits,
- attachment uploads,
- label/tag changes.

## Required Monitoring Behavior

While testing:

- Keep a running issue list of observed problems.
- Fix problems one at a time.
- Re-test the exact failing workflow after each fix.
- Keep logs concise.
- Track any timeout with command, duration, and likely root cause.
- If the pipeline loops, record the repeated step/reason and fix the loop-control bug.

## Required Final Report

Return:

- browser workflows tested,
- issues/pipeline keys tested,
- bugs found,
- files changed,
- tests run,
- confirmation that no Jira writes were made,
- confirmation that no Salesforce Production writes were made,
- remaining risks or manual checks.

Do not claim CaseOps is pilot-ready unless all tested workflows pass and the forbidden-write checks are clean.
