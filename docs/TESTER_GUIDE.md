# CaseOps Tester Guide

This guide is safe to share with a tester. It avoids private hostnames, internal paths, Jira issue keys, Salesforce org aliases, customer data, and credentials.

## What CaseOps Does

CaseOps is a Dockerized web app for Jira-to-Salesforce support work. It can:

- sync Jira issues and comments,
- show issue artifacts and generated files,
- run a guided Claude Code investigation pipeline,
- read Salesforce Production metadata and data for diagnosis,
- deploy and test candidate fixes only in the configured Sandbox,
- draft internal notes and customer-facing Jira messages.

CaseOps must not write to Salesforce Production. Production access is read-only.

## Files You Need

Use either a published image from GHCR or a provided image archive.

Recommended files:

- `docker-compose.yml`
- `.env.example`
- this guide

If using GHCR, the compose file should reference:

```text
ghcr.io/sdbingham/caseops:0.1.8
```

If using an archive, load it first:

```bash
docker load -i caseops-image.tar.gz
```

## First-Time Setup

1. Create a clean folder for CaseOps.
2. Put `docker-compose.yml` and `.env.example` in that folder.
3. Copy `.env.example` to `.env`.
4. Fill in your own Jira site, Jira API token, Salesforce org names, and Salesforce URLs.
5. Start the app:

```bash
docker compose pull
docker compose up -d
```

Open:

```text
http://localhost:5350
```

If you changed `CASEOPS_HOST_PORT`, use that port instead.

## Configure Settings

Open Settings in CaseOps.

### Jira

Enter:

- Jira base URL
- Jira email
- Jira API token
- default assignee, if used

Sync one issue first before syncing everything.

### Salesforce

Use your own Production read alias and Sandbox target alias. These are not hardcoded.

On a machine where Salesforce CLI is authenticated, run:

```bash
sf org auth show-access-token -o <production-read-alias> --json
sf org auth show-access-token -o <sandbox-target-alias> --json
sf org auth show-sfdx-auth-url -o <production-read-alias> --json
sf org auth show-sfdx-auth-url -o <sandbox-target-alias> --json
```

Paste the access token and SFDX auth URL values into Settings. Also provide the Production and Sandbox instance or Lightning URLs shown in your org.

The SFDX auth URL contains a refresh token. Treat it as a secret.

### Claude

On a machine with Claude Code installed:

```bash
claude setup-token
```

Paste the printed token into Settings. This enables the full pipeline.

## What To Test

1. Confirm the app opens and Settings shows the installed CaseOps version.
2. Confirm Settings status checks pass for Jira, Claude, Production, and Sandbox.
3. Run `Sync This Issue` for one approved Jira issue.
4. Confirm new Jira comments appear in the Jira Summary tab after sync.
5. Use the Issue filter to search by key, summary text, and tags.
6. Open an issue and check tabs:
   - Jira Summary
   - Investigation
   - Internal Notes
   - Jira Message
   - Test Report
   - Generated Files, when present
   - Engineering Handoff, when present
7. Run the pipeline only on an issue approved for testing.
8. Watch the run log and step indicator.
9. Use Stop Current Run if a pipeline gets stuck.
10. Use Pipeline State Repair/Rebuild only after stopping a stale or failed run.

## Expected Results

The app should:

- keep the issue list responsive,
- refresh Jira comments after issue sync,
- keep status/tags consistent with Jira,
- store generated files under issue-specific directories,
- show generated files inside the issue detail view,
- keep pipeline logs readable and bounded,
- mark stopped or failed runs clearly,
- reconnect after restart without showing a misleading error.

## Safety Rules

- Do not run pipeline actions on unapproved Jira issues.
- Do not paste real credentials into chat, screenshots, logs, or tickets.
- Do not use Salesforce frontdoor links as API tokens.
- Do not allow any Production deploy, data update, permission assignment, or mutating Apex command.
- Sandbox is the only writable Salesforce org.
- Production promotion should happen outside CaseOps through the normal change-control process.

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

Update to the latest published image:

```bash
docker compose pull
docker compose up -d
```

If Jira Summary looks stale, click `Sync This Issue` and refresh the issue. If it is still stale, report the CaseOps version shown in Settings and the time of the sync.

## What Not To Share

Do not include these in bug reports unless explicitly requested:

- Jira issue keys,
- customer names or summaries,
- Salesforce org aliases,
- Salesforce record IDs,
- access tokens or refresh tokens,
- internal hostnames, IP addresses, or filesystem paths,
- full pipeline logs.

Use cropped or redacted screenshots when possible.
