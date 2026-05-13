---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, process and work assigned issues, diagnose Salesforce problems, investigate Production metadata, determine whether to escalate to Engineering, implement Support-owned fixes, deploy to Sandbox, test the fix, iterate if needed, draft internal notes plus a Jira response, and produce a dated issue summary. Routes Closed/Resolved issues to outputs/closed-resolved/ and pre-escalated issues to outputs/engineering-escalations/ without processing.
---

# CaseOps — Claude Code entrypoint

This folder exists so **Claude Code** can discover a skill named `jira-salesforce-fix-pipeline` under `.claude/skills/`.

**Canonical instructions are not edited here.** From the repository root, open and follow the full Agent Skills playbook:

- **Playbook:** `skills/jira-salesforce-fix-pipeline/SKILL.md`
- **References:** `skills/jira-salesforce-fix-pipeline/references/`
- **Assets:** `skills/jira-salesforce-fix-pipeline/assets/`

Execute that playbook for the Jira issue key in the current task. Do not ask the user which workflow to run; derive next steps from the playbook and from which `outputs/` files already exist for that key.
