---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process and work assigned issues, diagnose Salesforce problems, investigate Production metadata, determine whether to escalate to Engineering, implement Support-owned fixes, **always** deploy and test only in the single Sandbox named by CASEOPS_SANDBOX_TARGET_ORG in .env.jira, iterate if needed, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
compatibility: CaseOps repo root, `.env.jira` (Jira credentials, JIRA_BASE_URL, CASEOPS_DEFAULT_ASSIGNEE, CASEOPS_SANDBOX_TARGET_ORG), Python 3 for `jira_sync.py`; Salesforce CLI optional for deploy/test sub-path.
---

# CaseOps — Claude Code entrypoint

This folder exists so **Claude Code** can discover a skill named `jira-salesforce-fix-pipeline` under `.claude/skills/`.

**Canonical instructions are not edited here.** From the repository root, open and follow the full Agent Skills playbook:

- **Playbook:** `skills/jira-salesforce-fix-pipeline/SKILL.md`
- **References:** `skills/jira-salesforce-fix-pipeline/references/`
- **Assets:** `skills/jira-salesforce-fix-pipeline/assets/`

Read `skills/jira-salesforce-fix-pipeline/SKILL.md`, then **`skills/jira-salesforce-fix-pipeline/references/workflow.md`** end-to-end (authoritative steps 1–12). Use `skills/jira-salesforce-fix-pipeline/references/sub-agent-prompts.md` when spawning sub-agents. Execute for the Jira issue key in the current task; do not ask the user which workflow to run — derive next steps from those files and from which `outputs/` artifacts already exist for that key.
