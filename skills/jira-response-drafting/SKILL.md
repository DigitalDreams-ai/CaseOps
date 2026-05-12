---
name: jira-response-drafting
description: Drafts internal implementation notes, Engineering handoff notes, and concise Jira responses after a Salesforce fix has been validated or escalated. Use when the user needs final notes, status details, handoff text, or text to paste into Jira.
---

# Jira Response Drafting

## Use This Skill When

- The Salesforce fix has been validated in Sandbox.
- The issue has been diagnosed and needs Engineering escalation.
- The user needs internal notes.
- The user needs a Jira-ready message.
- The `jira-salesforce-fix-pipeline` delegates notes and message drafting as Step 9.

## Workflow

1. Read the investigation record and test report.
2. Summarize the root cause.
3. Summarize the fix or Engineering escalation reason.
4. List changed metadata/code, or affected metadata/code for Engineering.
5. Summarize Sandbox testing or read-only validation evidence.
6. Draft internal notes. For Engineering escalations, the handoff file at `outputs/engineering-escalations/<KEY>.md` was already created by the pipeline's escalation gate — read it for context and append any additional details that emerged during analysis, but do not recreate it.
7. Draft a concise Jira message.

## Assets

- `assets/internal-notes-template.md`: Internal notes format.
- `assets/engineering-handoff-template.md`: Engineering handoff format.
- `assets/jira-message-template.md`: Jira response format.

## Quality Checks

- Keep the Jira message concise and factual.
- Do not claim Production deployment unless it happened.
- Include Sandbox validation details.
- For Engineering escalations, the handoff file is created by the pipeline escalation gate, not this skill. Only append details if new information emerged during drafting.
- Include any remaining risks or follow-up.
