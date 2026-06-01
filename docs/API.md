# CaseOps REST API

All endpoints return JSON unless noted. Base URL: `http://localhost:5000`

## Core Operations

### GET /api/issues

List all synced issues from manifest.csv.

**Response:**
```json
{
  "issues": [
    {
      "key": "HEAL-33753",
      "summary": "Create workflow for email to send scheduling link...",
      "status": "In Progress",
      "created": "2026-05-21T09:33:27Z",
      "updated": "2026-05-21T14:15:21Z",
      "assignee": "Sean Bingham",
      "investigationExists": true,
      "notesExists": true,
      "messageExists": true,
      "testReportExists": false
    },
    ...
  ],
  "openCount": 12,
  "closedCount": 3,
  "escalatedCount": 1
}
```

### GET /api/issue/:key

Get single issue detail including summaries and investigation record.

**Response:**
```json
{
  "key": "HEAL-33753",
  "summary": "Create workflow for email to send scheduling link...",
  "status": "In Progress",
  "created": "2026-05-21T09:33:27Z",
  "updated": "2026-05-21T14:15:21Z",
  "assignee": "Sean Bingham",
  "jiraSummary": "<html>...rendered markdown...</html>",
  "investigation": "<html>...rendered investigation...</html>",
  "internalNotes": "<html>...rendered notes...</html>",
  "jiraMessage": "<html>...rendered message...</html>",
  "testReport": null
}
```

### GET /api/file/:key/:type

Get raw file content for a specific issue and type.

**Query Params:**
- `format` — `raw` (markdown) or `html` (rendered, default)

**Types:**
- `jira_summary` — From outputs/jira/summary/
- `investigation` — From outputs/investigations/
- `internal_notes` — From outputs/internal-notes/
- `jira_message` — From outputs/jira-messages/
- `test_report` — From outputs/test-reports/
- `engineering_escalation` — From outputs/engineering-escalations/

**Example:**
```bash
curl http://localhost:5000/api/file/HEAL-33753/investigation?format=raw
# Returns markdown content
```

### POST /api/run

Trigger a pipeline action.

**Request:**
```json
{
  "action": "full_issue|sync_issue|sync|triage|full|claude_instruction",
  "key": "HEAL-33753",  // optional (required for single-issue actions)
  "instruction": "..."  // optional (for claude_instruction action only)
}
```

**Actions:**

| Action | Purpose | Scope |
|--------|---------|-------|
| `sync` | Full Jira sync | Global (all issues) |
| `sync_new` | Sync new/updated only | Global |
| `sync_issue` | Sync single issue | Single issue |
| `triage` | Triage + scaffold (no AI) | Global |
| `full` | Sync + triage + scaffold (no AI) | Global |
| `full_issue` | Full pipeline Steps 1–12 with Claude | Single issue |
| `claude_instruction` | Custom Claude instruction | Single issue |

**Response:**
```json
{
  "started": true,
  "action": "full_issue",
  "key": "HEAL-33753",
  "run_key": "HEAL-33753"
}
```

**Errors:**
- `409` — Action already running on this key
- `400` — Missing required params (e.g., no instruction for claude_instruction)
- `500` — Subprocess failure

### GET /api/stream

Server-Sent Events (SSE) stream for real-time pipeline logs.

**Streaming Format:**
```
data: HEAL-33753|STEP_3 HEAL-33753
data: HEAL-33753|Reading jira-issue-analysis skill...
data: __done__|HEAL-33753
```

**Message Format:**
- `run_key|text` — Log line for a specific run
- `__done__|run_key` — Signals completion of run

**Usage (JavaScript):**
```javascript
const eventSource = new EventSource('/api/stream');
eventSource.onmessage = (event) => {
  const [runKey, line] = event.data.split('|');
  console.log(`[${runKey}] ${line}`);
};
```

### GET /api/status

Get current system status (running operations, etc.).

**Response:**
```json
{
  "idle": false,
  "activeRuns": ["HEAL-33753"],
  "uptime": "12 hours 34 min"
}
```

### GET /api/orgs

Get org identifiers from .env.jira for artifact linking.

**Response:**
```json
{
  "prod": "10xhealth",
  "sandbox": "10xhealth-sean"
}
```

**Usage:** Used by JavaScript to build Salesforce URLs without magic links.

## Jira Integration

### POST /api/issue/:key/send-canned-message

Post a canned message to a Jira issue comment.

**Request:**
```json
{
  "message_id": "escalate_to_tier2",
  "customText": "Additional context..."  // optional
}
```

**Canned Messages:**
- `confirm_receipt` — "Thanks for submitting..."
- `escalate_to_tier2` — "This requires advanced investigation..."
- `status_update` — "Here's what we found..."
- Custom messages from `outputs/settings/canned-messages.json` when saved through Settings, falling back to repo default `canned-messages.json`

**Response:**
```json
{
  "success": true,
  "commentId": "10001234",
  "created": "2026-05-21T15:30:00Z"
}
```

**Errors:**
- `404` — Issue not found or Jira API unreachable
- `400` — Invalid message_id

### POST /api/issue/:key/transition

Change Jira issue status.

**Request:**
```json
{
  "transition": "In Progress",  // or "Done", "Escalated", etc.
  "comment": "..."              // optional
}
```

**Response:**
```json
{
  "success": true,
  "oldStatus": "To Do",
  "newStatus": "In Progress"
}
```

### GET /api/issue/:key/transitions

List available status transitions for an issue.

**Response:**
```json
{
  "current": "In Progress",
  "available": [
    {
      "id": "11",
      "name": "Done",
      "description": "Mark as complete"
    },
    {
      "id": "12",
      "name": "Escalated",
      "description": "Escalate to Engineering"
    }
  ]
}
```

### GET /api/issue/:key/comments

Get all comments on a Jira issue (from cached summary).

**Response:**
```json
{
  "total": 3,
  "comments": [
    {
      "author": "Sean Bingham",
      "body": "Hi...",
      "created": "2026-05-21T09:42:00Z",
      "updated": "2026-05-21T09:42:00Z"
    }
  ]
}
```

## Deployment & Testing

### GET /api/issue/:key/deployment-status

Get Sandbox deployment and Production readiness status.

**Response:**
```json
{
  "supportResolvable": true,
  "sandboxDeployed": true,
  "sandboxOrg": "10xhealth-sean",
  "productionReady": "Yes",  // Yes, No, TBD
  "productionChangeSet": null,  // Gearset deployment link (if applicable)
  "notes": "All validation passed. Ready for Gearset promotion."
}
```

### POST /api/issue/:key/deployment-status

Update deployment readiness metadata for an issue.

## Settings & Auth

### GET /api/settings

Return current persisted settings with secrets masked.

### POST /api/settings

Update supported settings in the active env file.

### GET /api/settings/status

Return runtime readiness, including Claude auth, Salesforce CLI availability, configured orgs, token age, and exact pipeline preflight status.

### POST /api/setup/salesforce-auth

Authenticate the Salesforce CLI inside the container from access tokens saved in the active env file. Uses `sf org login access-token` with `SF_ACCESS_TOKEN` in the subprocess environment.

### GET /setup/refresh-salesforce-tokens

HTML form for pasting Salesforce access tokens and SFDX auth URLs.

### POST /api/setup/refresh-salesforce-tokens

Save current Salesforce access tokens and optional SFDX auth URLs. CaseOps extracts refresh tokens from the full SFDX auth URL.

### GET /setup/claude-login

HTML form for saving the Claude Code OAuth token generated by `claude setup-token`.

### POST /api/setup/claude-credentials

Save `CLAUDE_CODE_OAUTH_TOKEN` into the active env file.

### GET /api/settings/canned-messages

Return canned message definitions. Customizations are read from `outputs/settings/canned-messages.json`.

### POST /api/settings/canned-messages

Save customized canned messages to `outputs/settings/canned-messages.json`.

### POST /api/settings/canned-messages/reset

Remove the custom canned message override and return to repo defaults.

## Caching & Performance

**Cached Resources:**
- Jira summaries (invalidated after `/api/run` sync)
- Investigation/notes/message HTML (invalidated after pipeline run)

**Cache Invalidation:**
- Global actions (sync, triage, full) → Clear all caches
- Single-issue operations → Clear that issue's cache
- Manual: Use browser refresh or `/api/file` with `?cache=bust` (not implemented)

## Pagination & Filtering

**Issue List Filtering (GET /api/issues):**
- `?status=In%20Progress` — Filter by status
- `?assignee=Sean%20Bingham` — Filter by assignee
- `?search=workflow` — Search summary text
- Combined: `?status=In%20Progress&search=workflow`

**Limit & Offset:**
- `?limit=20&offset=0` — Pagination (default 100)

## Error Responses

**4xx Errors:**
```json
{
  "error": "Issue HEAL-99999 not found",
  "code": 404
}
```

**5xx Errors:**
```json
{
  "error": "Jira API unreachable. Check .env.jira credentials.",
  "code": 500
}
```

## Rate Limiting

- **Jira API:** Depends on your Jira instance (typically 100–200 req/min)
- **CaseOps API:** No rate limiting; runs enforce sequential operation locks

## CORS

CORS is NOT enabled by default (single-origin usage). To enable:
```python
# In app.py
from flask_cors import CORS
CORS(app)
```

## WebHooks (Future)

Not yet implemented. Planned for:
- Jira → CaseOps (auto-trigger on issue created/updated)
- Salesforce → CaseOps (notify of Production errors)

## Debugging

**Enable request logging:**
```bash
FLASK_ENV=development FLASK_DEBUG=1 python app.py
```

**Check SSE stream:**
```bash
curl -N http://localhost:5000/api/stream
# Watch live events (Ctrl+C to stop)
```

**List running operations:**
```bash
curl http://localhost:5000/api/status
```
