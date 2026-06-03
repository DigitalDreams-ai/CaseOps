# Pipeline quality checklist

Verify before treating a run as complete.

- `jira_sync.py` is run before any issue processing begins.
- `manifest.csv` is read and all issues are routed before loading full issue content.
- Closed/Resolved issues are archived to `outputs/closed-resolved/<KEY>.md` and not processed.
- Issues with Jira status "Escalated to Engineering" are archived to `outputs/engineering-escalations/<KEY>.md` and not processed further.
- Active issues are processed one at a time, sequentially.
- Steps 3, 5, 6, 9, and 10 are always executed as sub-agents via the Agent tool — never inline in the orchestrator context.
- Each sub-agent prompt is fully self-contained with the issue key, relevant file paths, task, and return format.
- The orchestrator retains only the compact summary returned by each sub-agent, not the full contents of output files.
- Production metadata retrieval (Steps 5 and 6) is read-only.
- **Step 6 (Problem Location identification) is completed before escalation** — investigation record documents exact artifact, location, problem type, and failure point. No vague component discovery tasks delegated to Engineering.
- Step 6 can loop back to Step 5 if additional metadata drilling is needed; iterations recorded in investigation record.
- **Profile permissions were not modified** — no Salesforce Profile metadata or profile-level permission edits; use permission sets or escalate.
- **Production vs Sandbox is explicit** in investigation, test report, internal notes, and Jira draft: what Production has (read-only proof), what is **Sandbox-only**, and **Production deploy required?** (**Yes — Gearset** / **No** / **N/A**). Never imply Production was updated when only Sandbox was deployed/validated.
- The Salesforce problem statement is explicit before implementation.
- The solution plan identifies affected metadata or code.
- The Engineering escalation gate (Step 7) is evaluated before any implementation or Sandbox deployment.
- Engineering handoffs include the Engineering Message section: simple problem description and potential fix. Include problem location section with artifact details from Step 6.
- Engineering handoff notes are stored under `outputs/engineering-escalations/`.
- Step 9 is **mandatory** for every Support-resolvable issue (after Step 8). It is skipped **only** when Step 7 routes to Engineering escalation.
- **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira` is the **only** writable deploy target for Step 9; production and other orgs must not receive deploys or writes from this pipeline.
- The target Sandbox is explicit in the Step 9 sub-agent prompt and matches `.env.jira` before deployment.
- Tests map to Jira acceptance criteria.
- Failed iterations are recorded in `outputs/investigations/<KEY>.md` before re-spawning sub-agents.
- The dated issue summary `outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md` is created or updated after all issues are processed.
- The summary includes Closed/Resolved skips, Engineering escalations, and active pipeline results.
- Final Jira message is factual and avoids overclaiming.
