# Pipeline quality checklist

Verify before treating a run as complete.

- `jira_sync.py` is run before any issue processing begins.
- `manifest.csv` is read and all issues are routed before loading full issue content.
- Closed/Resolved issues are archived to `outputs/closed-resolved/<KEY>.md` and not processed.
- Issues with Jira status "Escalated to Engineering" are archived to `outputs/engineering-escalations/<KEY>.md` and not processed further.
- Active issues are processed one at a time, sequentially.
- Steps 3, 5, 8, and 9 are always executed as sub-agents via the Agent tool — never inline in the orchestrator context.
- Each sub-agent prompt is fully self-contained with the issue key, relevant file paths, task, and return format.
- The orchestrator retains only the compact summary returned by each sub-agent, not the full contents of output files.
- Production metadata retrieval is read-only.
- **Profile permissions were not modified** — no Salesforce Profile metadata or profile-level permission edits; use permission sets or escalate.
- **Production vs Sandbox is explicit** in investigation, test report, internal notes, and Jira draft: what Production has (read-only proof), what is **Sandbox-only**, and **Production deploy required?** (**Yes — Gearset** / **No** / **N/A**). Never imply Production was updated when only Sandbox was deployed/validated.
- The Salesforce problem statement is explicit before implementation.
- The solution plan identifies affected metadata or code.
- The Engineering escalation gate is evaluated before any implementation or Sandbox deployment.
- Engineering handoffs include the Engineering Message section: simple problem description and potential fix.
- Engineering handoff notes are stored under `outputs/engineering-escalations/`.
- Step 8 is **mandatory** for every Support-resolvable issue (after Step 7). It is skipped **only** when Step 6 routes to Engineering escalation.
- **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira` is the **only** writable deploy target for Step 8; production and other orgs must not receive deploys or writes from this pipeline.
- The target Sandbox is explicit in the Step 8 sub-agent prompt and matches `.env.jira` before deployment.
- Tests map to Jira acceptance criteria.
- Failed iterations are recorded in `outputs/investigations/<KEY>.md` before re-spawning sub-agents.
- The dated issue summary `outputs/issue-summary-YYYY-MM-DD.md` is created or updated after all issues are processed.
- The summary includes Closed/Resolved skips, Engineering escalations, and active pipeline results.
- Final Jira message is factual and avoids overclaiming.
