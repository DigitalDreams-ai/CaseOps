# Claude Code Launcher Guide

Normal CaseOps operation launches Claude Code from the Flask app. Manual launch is only for debugging.

## Auth

Use:

```bash
claude setup-token
```

Paste the token into CaseOps at:

```text
/setup/claude-login
```

CaseOps stores it as `CLAUDE_CODE_OAUTH_TOKEN` in the active env file.

## Manual CLI Run

From the repo root:

```bash
claude -p "Process HEAL-12345 through the full jira-salesforce-fix-pipeline skill."
```

The normal GUI path is preferred because it injects the current CaseOps prompt, output paths, org-knowledge context, and log parsing expectations.

## Manual IDE Run

In Claude Code:

```text
/jira-salesforce-fix-pipeline

Process HEAL-12345 through the full pipeline.
```

## Required Context

Manual launches still require:

- active `.env.jira`
- Jira outputs or Jira credentials
- configured Salesforce token auth
- `CASEOPS_SANDBOX_TARGET_ORG`
- Production read-only org
- current skill files under `skills/`

## Common Failures

`claude: command not found`:

```bash
npm install -g @anthropic-ai/claude-code
```

Auth failure:

```bash
claude setup-token
```

Then save the token through CaseOps Settings.
