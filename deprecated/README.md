# Deprecated Legacy Agents

Scripts in this directory are superseded by the **skill-based pipeline** (`skills/jira-salesforce-fix-pipeline/`).

## Migration Map

| Legacy Script | Replaced By | Status |
|---|---|---|
| `escalation_gate_agent.py` | `Step 7` (Skill escalation gate in orchestrator) | Deprecated 2026-05-20 |
| `step8_agent.py` | `Step 9` (`salesforce-sandbox-deploy-test` skill) | Deprecated 2026-05-20 |
| `test_report_agent.py` | `Step 9` output (`test-report-template.md`) | Deprecated 2026-05-20 |
| `investigation_finalization_agent.py` | `Step 3` (`jira-issue-analysis` skill) | Deprecated 2026-05-20 |
| `notes_and_escalation_agent.py` | `Step 10` (`jira-response-drafting` skill) | Deprecated 2026-05-20 |
| `solution_planning_agent.py` | `Step 8` (Orchestrator implementation in workflow) | Deprecated 2026-05-20 |
| `production_promotion_plan_agent.py` | `Step 8` output (`solution plan` in investigation record) | Deprecated 2026-05-20 |

## Current Pipeline

Use **Claude Code skill** (`jira-salesforce-fix-pipeline`) for Steps 1–12:
- Canonical: `skills/jira-salesforce-fix-pipeline/references/workflow.md`
- Sub-agent prompts: `skills/jira-salesforce-fix-pipeline/references/sub-agent-prompts.md`
- Templates: `skills/jira-salesforce-fix-pipeline/assets/`

## Cleanup Timeline

These scripts are archived here pending removal. Delete after:
- [ ] Confirm skill-based pipeline is stable in production
- [ ] All active workflows use skill approach
- [ ] No external integrations reference legacy agents
- [ ] 2026-06-30 (1 month grace period)
