# CaseOps Docker Image Test Guide

Use this guide to validate a published CaseOps Docker image. Setup details live in [CaseOps Quickstart](CASEOPS_QUICKSTART.md) and [Docker Setup](DOCKER_SETUP.md); this file is the test checklist.

This guide is safe to share. Do not include private hostnames, internal filesystem paths, Jira issue keys, Salesforce org aliases, customer data, screenshots with credentials, or full logs in bug reports.

## Test Target

Use the published image tag provided by the maintainer. Prefer a numbered tag over `latest` when reporting issues:

```text
ghcr.io/digitaldreams-ai/caseops:0.1.15
```

Start from a clean Docker folder containing:

- `docker-compose.yml`
- `.env`

The compose file should run the app from the image and mount persistent data at `/data`.

## Setup Check

1. Start CaseOps with `docker compose up -d`.
2. Open `http://localhost:5350`, or the port configured by `CASEOPS_HOST_PORT`.
3. Open Settings and confirm the installed CaseOps version is shown next to the Settings title.
4. Confirm the app uses one env file, mounted inside the container as `/data/.env`.
5. Confirm `/data/outputs` is writable by syncing or saving a setting.

## Authentication Check

In Settings, configure and verify:

| Area | Expected Result |
| --- | --- |
| Jira | Base URL, email, and API token save and validate. |
| Salesforce Production | Read-only org token validates for SOQL and metadata reads. |
| Salesforce Sandbox | Sandbox target token validates and is the only writable org. |
| Claude | `claude setup-token` token saves and Claude Code auth validates. |

Salesforce org aliases, instance URLs, and Lightning URLs must come from the tester's own orgs. They must not be hardcoded.

## Jira Sync Check

1. Sync one approved test issue.
2. Confirm the issue appears in the dashboard.
3. Confirm Jira Summary includes current description, comments, status, labels, attachments, and forms when present.
4. Add or identify a newer Jira comment, then run `Sync This Issue`.
5. Confirm the new comment appears after sync.
6. Confirm Closed/Resolved issues are not included in normal active sync results.

## Dashboard Check

Verify issue filtering by:

- issue key,
- summary text,
- status text,
- tags.

In Select mode, confirm `Sync Selected` and `Run Pipeline` are visible immediately, even before selecting issues, and disabled until at least one issue is selected.

When a test issue has a confirmed Sandbox validation and `production_deploy_required=yes`, confirm the dashboard shows/searches the `Ready to Deploy` tag and does not show `Validated` as the active-list state label.

Confirm every issue has exactly one primary tag. Confirm `partial run` finds issues in `In Progress` or `Analyzed` state, and `needs engineering` finds issues requiring Engineering ownership.

## Issue Detail Check

Open a synced issue and verify available tabs render without errors:

- Similar Issues, when related issues exist
- Jira Summary
- Investigation
- Internal Notes
- Jira Message
- Test Report
- Generated Files, when present
- Needs Engineering, when present
- Pipeline Log

Generated files must appear under an issue-specific directory, not directly under the root outputs directory.

## Similar Issues Check

Use a safe group of approved test issues that are about the same problem.

Expected behavior:

1. CaseOps automatically groups similar current-user issues.
2. The Similar Issues tab shows open matches separately from closed/resolved matches.
3. Closed/resolved issues can appear as similarity context.
4. The current issue is not listed as a similar match to itself.
5. Evidence terms and reasons are visible enough to understand why issues were grouped.
6. The public-safe cluster summary link opens without exposing credentials or private org details.
7. Local correction buttons save and refresh the panel without posting to Jira.
8. Similarity context does not bypass Salesforce validation before any reuse or delta behavior.

## Pipeline Check

Run the pipeline only on an approved test issue.

Expected behavior:

- Preflight validates Jira, Claude, Production read access, and Sandbox target access.
- Similar issue context may appear in the resume plan, but unsafe reuse falls back to normal/full investigation.
- Production Salesforce is read-only.
- Sandbox is the only writable Salesforce org.
- The run log shows step progress.
- Pipeline artifacts are written under `/data/outputs`.
- `Auto-Process All` and `Reprocess All (No Sync)` skip Jira issues already marked `Escalated to Engineering`.
- The final global queue summary reports why the queue stopped, groups incomplete issues by repeated step/status blockers, and gives actionable incomplete reasons per issue.
- Stop Current Run stops an active pipeline cleanly.
- Pipeline State Repair/Rebuild is available for stale or inconsistent state after a stopped or failed run.

## Safety Rules

- Do not run pipeline actions on unapproved Jira issues.
- Do not allow any Production deploy, data update, permission assignment, or mutating Apex command.
- Do not use Salesforce frontdoor or magic links as API credentials.
- Treat access tokens and SFDX auth URLs as secrets.
- Review generated Jira messages before posting them.
- Production promotion must happen outside CaseOps through the normal change-control process.

## Troubleshooting

Check container status:

```bash
docker compose ps
```

Check recent logs:

```bash
docker compose logs --tail 100 caseops
```

Restart:

```bash
docker compose restart caseops
```

Update to the tag in the compose file:

```bash
docker compose pull
docker compose up -d
```

When reporting a problem, include:

- CaseOps version from Settings,
- image tag,
- browser and operating system,
- which checklist step failed,
- a short redacted screenshot or short redacted log excerpt.

Do not include credentials, full Jira issue contents, Salesforce record IDs, customer names, internal hostnames, or full pipeline logs.
