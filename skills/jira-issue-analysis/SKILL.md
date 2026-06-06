---
name: jira-issue-analysis
description: Retrieves, normalizes, and analyzes Jira issues for Salesforce implementation work. Use when the user provides Jira keys, URLs, JQL, exports, or pasted issue details that need to be turned into problem statements, acceptance criteria, and implementation questions.
---

# Jira Issue Analysis

## Use This Skill When

- The user asks to retrieve or understand Jira issues.
- Jira issue data needs to be converted into Salesforce implementation requirements.
- Acceptance criteria, reproduction steps, or missing details need to be extracted.
- The `jira-salesforce-fix-pipeline` delegates issue analysis as Step 3.

## Workflow

1. Retrieve Jira issue data using the active env file: `python jira_sync.py --env-file "$CASEOPS_ENV_FILE"`. If `CASEOPS_ENV_FILE` is not set, ask the operator to configure it or use available Jira tools, exports, URLs, or pasted content.
2. Identify issue key, summary, description, comments, attachments, labels, components, priority, and status.
3. Extract observed behavior, expected behavior, acceptance criteria, reproduction steps, and constraints.
4. Identify missing information that blocks Salesforce diagnosis.
5. Output a structured issue analysis.
   - Standalone: write to `outputs/investigations/<KEY>.md` using `assets/issue-analysis-template.md`.
   - When invoked by `jira-salesforce-fix-pipeline`: populate the **Issue Understanding** section of `outputs/investigations/<KEY>.md` using `assets/investigation-record-template.md` from the pipeline skill's assets.

## Available Scripts

- `jira_sync.py`: Syncs Jira issues into `outputs/jira/` as raw JSON, markdown summaries, attachments, forms, and a manifest. Run from the repo root with the active env file from `CASEOPS_ENV_FILE`. Use `--issue KEY` for one issue or `--jql "..."` for a query.

## References

- `references/issue-analysis-guide.md`: Field mapping and analysis guidance.

## Assets

- `assets/issue-analysis-template.md`: Structured output template.

## Quality Checks

- Do not infer acceptance criteria if the issue contradicts itself.
- Mark assumptions clearly.
- Preserve issue keys and links exactly.
