# CaseOps Pipeline Quality Checklist

Use this checklist before a run is considered complete.

## Queue Scope

- Only issues assigned to the configured Jira user were considered.
- Closed, Resolved, Canceled, Cancelled, Hold, and On Hold issues were skipped.
- Every other assigned issue, including one with a legacy `Escalated to Engineering` Jira status, used the full pipeline.
- No Engineering escalation route, handoff, state, tag, or disposition was created.

## Investigation And Routing

- The hypothesis is evidence-backed and stored in the canonical hypothesis artifact.
- Production investigation was read-only.
- Step 6 identifies the problem type, exact artifact or data object, location, failure point, and evidence.
- Step 7 persists `routing.path=full_pipeline`.
- A blocker is specific and externally actionable. Difficulty or metadata ownership alone is not a blocker.
- Historical files under `outputs/engineering-escalations/` did not influence current routing or state.

## Solution And Validation

- Step 8 records a concrete candidate solution, admin/data action, customer answer, or supported no-change conclusion.
- Step 9 records Sandbox validation or an explicit no-deploy validation result for every active issue.
- Failed Sandbox attempts were reverted before retrying.
- Confirmed solution artifacts are stored under the issue-scoped `confirmed/solution/` path.
- Profile permissions were not modified. Permission sets or documented admin actions were used instead.
- Production was not mutated without valid issue-scoped temporary approval.

## Outputs

- `outputs/issue-briefs/<KEY>.md` exists and follows the five-section template.
- `outputs/internal-notes/<KEY>.md` exists and contains a concise decision memo.
- `outputs/jira-messages/<KEY>.md` exists and is customer-facing only.
- No file under `outputs/engineering-escalations/` was created or updated.
- Sandbox and Production state are clearly distinguished.
- The dated summary reports validated, data-only, blocked, and in-progress outcomes without an escalation section.

## State And Completion

- A completed step has a durable checkpoint and required artifact.
- The final disposition is one of `validated`, `data-only`, `blocked`, or `in-progress`.
- Incomplete issues expose their next step and blocker.
- Queue termination reports whether work completed, stalled, reached the pass limit, was stopped, or failed.
- Unchanged failed work is not repeatedly reprocessed.
