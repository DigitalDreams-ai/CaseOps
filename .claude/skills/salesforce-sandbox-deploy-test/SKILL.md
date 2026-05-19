---
name: salesforce-sandbox-deploy-test
description: Mandatory for jira-salesforce-fix-pipeline after Support-owned implementation. Deploys only to the single allowlisted Sandbox from CASEOPS_SANDBOX_TARGET_ORG in .env.jira, tests against Jira acceptance criteria, and records results. Refuse any deploy or data write to any other org.
---

# CaseOps — Claude Code entrypoint

This folder exists so **Claude Code** can discover a skill named `salesforce-sandbox-deploy-test` under `.claude/skills/`.

**Canonical instructions are not edited here.** From the repository root, open and follow the full Agent Skills playbook:

- **Playbook:** `skills/salesforce-sandbox-deploy-test/SKILL.md`
- **References:** `skills/salesforce-sandbox-deploy-test/references/` (if present)
- **Assets:** `skills/salesforce-sandbox-deploy-test/assets/` (if present)

Read `skills/salesforce-sandbox-deploy-test/SKILL.md` end-to-end for authoritative workflow and requirements. **CRITICAL: Read the Hard Requirements section first — this skill has mandatory allowlist guards.**
