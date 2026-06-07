# CaseOps User Guide

## Open CaseOps

Default Docker URL:

```text
http://localhost:5350
```

If `CASEOPS_HOST_PORT` is changed in `.env`, use that port.

## Dashboard

The dashboard lists synced Jira issues and their CaseOps state. Select an issue to view:

- Similar Issues
- Jira Summary
- Investigation
- Internal Notes
- Jira Message
- Test Report
- Generated Files
- Engineering Handoff, when present
- Pipeline Log

The issue filter can search by issue key, summary text, status text, and tags.

Common tags include:

- `new comments`
- `not triaged`
- `data only`
- `blocked`
- `validated`
- `needs escalation`

## Issue Actions

Common actions:

| Action | Purpose |
| --- | --- |
| Sync from Jira | Refresh Jira issue data and manifest |
| Sync This Issue | Refresh one Jira issue, including comments and forms |
| Run Pipeline | Run the guided investigation pipeline for one issue |
| Stop Current Run | Stop an active pipeline subprocess |
| Repair/Rebuild Pipeline State | Rebuild resume state from existing artifacts |
| Send Canned Message | Post a configured Jira message |
| Transition Issue | Apply an available Jira transition |

Run pipeline actions only on approved issues.

## Similar Issues

The Similar Issues tab shows other issues that appear to share the same problem pattern.

CaseOps automatically builds these clusters from synced Jira data and CaseOps artifacts for the current configured user. Closed and resolved issues are included for context because they may contain a previous diagnosis or fix.

The tab separates:

- open matches,
- closed/resolved matches,
- evidence terms,
- match reasons,
- stale/current artifact status,
- public-safe cluster summary links.

Available local correction actions include marking a match as the same root cause, marking it not related, detaching the current issue from a cluster, or making an issue canonical for the cluster.

These correction actions update CaseOps appdata only. They do not post to Jira and do not write to Salesforce.

Similarity context can inform the pipeline, but it should not replace issue-specific validation. Delta/reuse behavior is gated by model adjudication, fresh Salesforce validation, and stale-artifact checks.

## Settings

Settings shows the installed CaseOps version beside the page title.

Use Settings to configure and verify:

- Jira credentials,
- Salesforce Production read access,
- Salesforce Sandbox target access,
- Claude Code OAuth token,
- pipeline timeout and parallelism settings,
- similar issue clustering controls,
- canned messages,
- restart and state repair tools.

## Jira Setup

Required:

- Jira base URL
- Jira email
- Jira API token

Optional:

- default assignee,
- cloud ID,
- bearer token or auth-header command for advanced setups.

After updating Jira settings, run `Sync This Issue` on a known issue before running a pipeline.

## Salesforce Setup

CaseOps uses two Salesforce roles:

| Role | Purpose |
| --- | --- |
| Production read org | Read-only SOQL and metadata retrieval |
| Sandbox target org | Deploy and test candidate fixes |

The org aliases are configured in Settings or `.env`; they are not hardcoded.

On a machine where Salesforce CLI is authenticated:

```bash
sf org auth show-access-token -o <production-read-alias> --json
sf org auth show-access-token -o <sandbox-target-alias> --json
```

Paste each `result.accessToken`.

For token refresh support:

```bash
sf org auth show-sfdx-auth-url -o <production-read-alias> --json
sf org auth show-sfdx-auth-url -o <sandbox-target-alias> --json
```

Paste each full `result.sfdxAuthUrl`. It contains a refresh token and must be treated as a secret.

Also configure the Production and Sandbox instance or Lightning URLs so CaseOps can build correct links and validate auth clearly.

## Claude Setup

Use Claude Code auth for the full pipeline.

On a machine with Claude Code installed:

```bash
claude setup-token
```

Paste the printed token into the Claude section in Settings.

`CASEOPS_LLM_AUTH=claude_code` is recommended. API-key mode is text-only and does not provide the same tool execution behavior.

## Salesforce Safety

- Production is read-only.
- The only writable org is `CASEOPS_SANDBOX_TARGET_ORG`.
- CaseOps does not deploy to Production.
- Use your normal change-control process for Production promotion.
- Frontdoor or magic links are only for visual browser inspection when needed.
- API, SOQL, retrieve, deploy, and tests must use Salesforce CLI auth.

## Generated Files

Generated files are stored under an issue-specific directory and shown on the `Generated Files` tab for that issue.

Examples include reports, spreadsheets, or other files created during investigation.

## Canned Messages

Canned messages are configured in Settings. They are stored in persistent appdata so they survive container restarts and image updates.

Review every message before posting to Jira.

## Pipeline Logs

Each issue has a pipeline log. Use the copy-log button when reporting a problem, but redact:

- customer information,
- Jira issue keys,
- Salesforce record IDs,
- org aliases,
- token values,
- internal hostnames or paths.

## Troubleshooting

Check container status:

```bash
docker compose ps
```

Check logs:

```bash
docker compose logs --tail 100 caseops
```

Restart:

```bash
docker compose restart caseops
```

If Jira comments look stale:

1. Click `Sync This Issue`.
2. Reopen the issue.
3. Confirm the CaseOps version in Settings.
4. Check logs if the summary still does not update.

If a pipeline times out:

1. Use `Stop Current Run`.
2. Use `Repair/Rebuild Pipeline State`.
3. Increase timeout settings only if the issue legitimately needs a longer metadata/deploy/test cycle.
