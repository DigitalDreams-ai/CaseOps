# CaseOps API

Base URL in Docker:

```text
http://localhost:5350
```

Base URL locally:

```text
http://localhost:5000
```

## Core

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Dashboard |
| `GET` | `/api/issues` | List synced issues with tags/artifact status |
| `GET` | `/api/issue/<key>` | Issue detail and rendered artifact content |
| `GET` | `/api/file/<key>/<type>` | Raw or rendered issue file |
| `POST` | `/api/run` | Start sync, triage, issue pipeline, or custom instruction |
| `GET` | `/api/stream` | Server-Sent Events stream for pipeline logs |
| `GET` | `/api/status` | Active run status |

## `/api/run`

Common actions:

| Action | Scope | Purpose |
| --- | --- | --- |
| `sync` | Global | Full Jira sync |
| `sync_new` | Global | Incremental Jira sync |
| `sync_issue` | Single issue | Refresh one Jira issue |
| `triage` | Global | Triage/scaffold without AI |
| `full` | Global | Sync plus triage/scaffold |
| `full_issue` | Single issue | Run Steps 1-12 through Claude |
| `claude_instruction` | Single issue | Run a custom instruction against one issue |

Example:

```json
{
  "action": "full_issue",
  "key": "ISSUE-12345"
}
```

## File Types

`/api/file/<key>/<type>` supports:

- `jira_summary`
- `investigation`
- `internal_notes`
- `jira_message`
- `test_report`
- `engineering_escalation`
- `closed_resolved`
- `pipeline_log`

Use `?format=raw` for raw markdown/text.

## Settings And Auth

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/settings` | Read masked settings |
| `POST` | `/api/settings` | Save supported settings |
| `GET` | `/api/settings/status` | Fast runtime readiness summary |
| `POST` | `/api/setup/salesforce-auth` | Authenticate container `sf` from saved tokens |
| `POST` | `/api/setup/refresh-salesforce-tokens` | Save Salesforce access/refresh tokens from Settings |
| `GET` | `/setup/claude-login` | Claude Code token form |
| `POST` | `/api/setup/claude-credentials` | Save `CLAUDE_CODE_OAUTH_TOKEN` |

Salesforce auth is entered from `/settings`. Refresh token input may be either a raw refresh token or the full `result.sfdxAuthUrl` from `sf org auth show-sfdx-auth-url --json`.

## Canned Messages

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/settings/canned-messages` | Read canned message config |
| `POST` | `/api/settings/canned-messages` | Save custom canned messages |
| `POST` | `/api/settings/canned-messages/reset` | Remove custom override |
| `POST` | `/api/issue/<key>/send-canned-message` | Post selected canned message to Jira |

Custom canned messages are saved to:

```text
outputs/settings/canned-messages.json
```

## Jira

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/issue/<key>/comments` | Read cached Jira comments |
| `GET` | `/api/issue/<key>/transitions` | List available Jira transitions |
| `POST` | `/api/issue/<key>/transition` | Change Jira status |

CaseOps drafts Jira messages. Posting is manual unless the user explicitly invokes a post action.

## Logs

`/api/stream` emits:

```text
run_key|log line
__done__|run_key
```

The frontend uses this stream for live logs and step indicators.
