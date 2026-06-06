---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process assigned issues, diagnose Salesforce problems, investigate Production metadata read-only, classify Support vs Engineering ownership, create a proposed solution, deploy and test only in the single Sandbox named by CASEOPS_SANDBOX_TARGET_ORG, revert failed Sandbox attempts, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
compatibility: CaseOps repo root, active env file from CASEOPS_JIRA_ENV_FILE, Python 3 for `jira_sync.py`, Salesforce CLI for Production read-only investigation and Sandbox deploy/test.
---

# CaseOps — Claude Code entrypoint

This folder exists so **Claude Code** can discover a skill named `jira-salesforce-fix-pipeline` under `.claude/skills/`.

**Canonical instructions are not edited here.** From the repository root, open and follow the full Agent Skills playbook:

- **Playbook:** `skills/jira-salesforce-fix-pipeline/SKILL.md`
- **References:** `skills/jira-salesforce-fix-pipeline/references/`
- **Assets:** `skills/jira-salesforce-fix-pipeline/assets/`

Read `skills/jira-salesforce-fix-pipeline/SKILL.md`, then **`skills/jira-salesforce-fix-pipeline/references/workflow.md`** end-to-end (authoritative steps 1–12). Use `skills/jira-salesforce-fix-pipeline/references/sub-agent-prompts.md` when spawning sub-agents. Execute for the Jira issue key in the current task; do not ask the user which workflow to run — derive next steps from those files and from which `outputs/` artifacts already exist for that key.
