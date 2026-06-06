# Jira Issue Analysis Guide

Capture the issue in implementation-ready form.

Required sections:

- Issue identity.
- Business problem.
- Observed behavior.
- Expected behavior.
- Acceptance criteria.
- Reproduction steps.
- Affected Salesforce area.
- Missing information.
- Implementation notes.

If Jira access is unavailable, ask for an export or pasted issue details instead of inventing issue content.

## Local Retrieval

Use the repo-level Jira sync script when Jira credentials are available. Use the active env file from `CASEOPS_ENV_FILE`. Always run from the repo root:

```text
python jira_sync.py --env-file "$CASEOPS_ENV_FILE" --issue ISSUE-123 --no-attachments --no-forms
```

For the default queue:

```text
python jira_sync.py --env-file "$CASEOPS_ENV_FILE" --max-issues 10 --no-attachments --no-forms
```

Outputs:

- `outputs/jira/raw/<KEY>.json`
- `outputs/jira/summary/<KEY>.md`
- `outputs/jira/manifest.csv`
- `outputs/jira/field-map.json`

Use `--no-attachments --no-forms` for a lightweight first pass. Download attachments and forms when they are needed to understand the issue.
