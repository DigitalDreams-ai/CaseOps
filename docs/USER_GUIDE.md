# CaseOps User Guide

## Open CaseOps

NAS pilot URL:

```text
http://10.0.1.10:5350
```

Local development URL:

```text
http://localhost:5000
```

## Dashboard

The dashboard lists synced Jira issues and their CaseOps artifacts. Select an issue to view:

- Jira summary
- Investigation
- Step 4 hypothesis
- Internal notes
- Jira message draft
- Test report
- Engineering handoff, if present
- Pipeline log

The Step 4 hypothesis artifact is used internally by the pipeline and is not shown as a normal issue tab.

## Pipeline Actions

Common actions:

| Action | Purpose |
| --- | --- |
| Sync from Jira | Refresh Jira issue data and manifest |
| Sync this issue | Refresh one Jira issue |
| Prepare issues | Triage and scaffold without a full AI run |
| Run pipeline for this issue | Run Steps 1-12 for one issue |
| Auto-process all | Run active issues sequentially |

The pipeline streams real-time progress lines and issue logs. Issue cards should advance beyond `Running: Step 3/12` as Claude emits `STEP_N` markers.

## Salesforce Authentication

Use Settings or `/setup/refresh-salesforce-tokens`.

On an authenticated local machine:

```bash
sf org login web --alias 10xhealth
sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com

sf org auth show-access-token -o 10xhealth --json
sf org auth show-access-token -o 10xhealth-sean --json
```

Paste each `result.accessToken`.

For automatic refresh, also run:

```bash
sf org auth show-sfdx-auth-url -o 10xhealth --json
sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
```

Paste each full `result.sfdxAuthUrl`. That Salesforce auth URL contains the refresh token. CaseOps extracts and stores only the refresh-token value in the active env file.

Auth notes:

- `sfdxAuthUrl` is Salesforce's current field name for this credential. It does not mean CaseOps uses legacy `sfdx force:*` deploy/retrieve commands.
- CaseOps authenticates `sf` inside Docker from tokens in `/app/.env.jira`.
- Host `~/.sf` and `~/.sfdx` are not mounted into the NAS container.

## Claude Authentication

Use Settings or `/setup/claude-login`.

On your local machine:

```bash
claude setup-token
```

Paste the token into CaseOps. CaseOps saves it as `CLAUDE_CODE_OAUTH_TOKEN` in the active env file.

The old interactive container login banner is no longer needed for normal Salesforce or Claude auth.

## Salesforce Safety

- Production is read-only.
- The only writable org is the value of `CASEOPS_SANDBOX_TARGET_ORG`.
- CaseOps does not deploy to Production.
- Use Gearset or your normal change-control process for Production promotion.
- Frontdoor/magic links are only for visual UI inspection when necessary.
- API, SOQL, retrieve, deploy, and tests must use `sf` CLI and authenticated org aliases.

## Metadata Workspace

Current runtime paths:

| Purpose | Path |
| --- | --- |
| Raw Production metadata, read-only | `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/` |
| Sandbox attempts | `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/` |
| Confirmed Support package | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/support-owned/` |
| Confirmed Engineering proposal | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/confirmed/engineering-proposal/` |

Current NAS values resolve under:

```text
/app/instance1/outputs/metadata-cache/
/app/instance1/outputs/metadata-workspaces/
```

Rules:

- Do not edit raw Production metadata.
- Capture `baseline-sandbox/` before every Sandbox deploy attempt.
- Put proposed deployable metadata under `candidate/`.
- Put rollback metadata or destructive changes under `revert/`.
- Revert failed or abandoned attempts before starting another attempt.
- Copy passed work to `<KEY>/confirmed/`.

## Org Knowledge

CaseOps seeds and reads reusable org knowledge under:

```text
instance1/outputs/org-knowledge/
```

The pipeline reads `index.json`, selects relevant topic files, and injects only those files into the Claude run. It does not bulk-read all knowledge files.

Seeded topics include:

- helper scripts
- fields and picklists
- layouts and record types
- access and visibility
- deploy and sandbox
- automation order
- query patterns
- deploy patterns

Durable, verified lessons can be added to the most specific topic file. Do not store secrets, raw tokens, frontdoor links, or customer-private narrative.

## Canned Messages

Canned message edits made in Settings are saved persistently at:

```text
instance1/outputs/settings/canned-messages.json
```

They survive container restarts and image rebuilds because they are stored in mounted appdata.

## Copy Pipeline Logs

The issue detail view has a copy-log button. If browser clipboard APIs are unavailable, CaseOps falls back to selecting/copying text through the page.

## Troubleshooting

Check active runs:

```bash
ssh docker@10.0.1.10 "curl -fsS http://127.0.0.1:5350/api/status"
```

Check container logs:

```bash
ssh docker@10.0.1.10 "/volume1/@appstore/ContainerManager/usr/bin/docker logs --tail 100 caseops"
```

Check Salesforce preflight from Settings. `/api/settings/status` is designed to return quickly and should not block Settings load on slow runtime checks.
