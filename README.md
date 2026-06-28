# CaseOps

CaseOps is a Dockerized web app for Jira-to-Salesforce support work. It syncs Jira issues, runs a guided Claude Code investigation pipeline, validates candidate fixes in a configured Salesforce Sandbox, and drafts internal notes or customer-facing Jira replies.

CaseOps is built for workflows where Salesforce Production must stay read-only and all write/deploy activity must happen in an explicitly configured Sandbox.

## Status

- Distribution: Docker image
- Current image: `ghcr.io/digitaldreams-ai/caseops:0.1.32`
- Default URL: `http://localhost:5350`
- Runtime data: Docker-mounted `/data`
- Production Salesforce: read-only
- Sandbox Salesforce: only configured writable org

## Features

- Jira issue sync, including comments, attachments, forms, labels, and status.
- Searchable issue dashboard with status and CaseOps tags.
- Similar Issues clustering for current-user issues, including open and closed/resolved issue context.
- Settings UI for Jira, Salesforce, Claude Code, canned messages, pipeline controls, and runtime status.
- Claude Code powered 12-step investigation pipeline.
- Read-only Production Salesforce metadata and SOQL investigation.
- Sandbox deploy/test/revert workflow for candidate fixes.
- Generated artifacts for investigations, hypotheses, internal notes, Jira drafts, test reports, pipeline logs, metadata workspaces, and generated files.
- Public-safe issue-cluster summaries and local correction state for related issues.
- Docker-first runtime with persistent appdata under `/data`.

## Safety Model

- CaseOps does not deploy to Salesforce Production.
- Production access is for read-only SOQL, metadata retrieval, and visual inspection only.
- The configured Sandbox target is the only writable Salesforce org.
- Salesforce frontdoor or magic links must not be used as API credentials.
- Credentials, Jira issue data, Salesforce CLI state, generated files, and logs belong in mounted appdata, not in the image or source repo.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose.
- Jira API token access.
- Salesforce CLI access to:
  - one Production org for read-only investigation,
  - one Sandbox org for deploy and test.
- Claude Code access. Run `claude setup-token` and paste the printed token in CaseOps Settings.

## Quickstart

Create a deployment folder and copy the example files:

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
```

Edit `.env` with your Jira credentials, Salesforce aliases, and Salesforce URLs.

Start CaseOps:

```bash
docker compose pull
docker compose up -d
```

Open:

```text
http://localhost:5350
```

Then open Settings and complete:

1. Jira connection.
2. Salesforce Production read auth.
3. Salesforce Sandbox target auth.
4. Claude Code token from `claude setup-token`.

See [CaseOps Quickstart](docs/CASEOPS_QUICKSTART.md) for the short setup path.

## Configuration

CaseOps uses one active env file. In Docker, that file is mounted as:

```text
/data/.env
```

Start from [.env.example](.env.example). The main values are:

| Variable | Purpose |
| --- | --- |
| `JIRA_BASE_URL` | Jira site URL. |
| `JIRA_EMAIL` | Jira account email. |
| `JIRA_API_TOKEN` | Jira API token. |
| `CASEOPS_LLM_AUTH` | Usually `claude_code`. |
| `CASEOPS_PRODUCTION_READ_ORG` | Salesforce Production alias for read-only investigation. |
| `CASEOPS_SANDBOX_TARGET_ORG` | Only Salesforce org CaseOps may write/deploy to. |
| `CASEOPS_PRODUCTION_INSTANCE_URL` | Production Salesforce instance URL. |
| `CASEOPS_SANDBOX_INSTANCE_URL` | Sandbox Salesforce instance URL. |

You can leave Salesforce and Claude token values blank initially and paste them through Settings.

## Docker Operations

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs --tail 100 caseops
```

Restart:

```bash
docker compose restart caseops
```

Update to the image tag in `docker-compose.yml`:

```bash
docker compose pull
docker compose up -d
```

Health check:

```bash
curl -fsS http://localhost:5350/health
```

## Runtime Data

The container stores persistent runtime state under `/data`:

- `/data/.env` - Settings-managed configuration and tokens.
- `/data/outputs/jira` - Jira sync data.
- `/data/outputs/pipeline-logs` - streamed pipeline logs.
- `/data/outputs/generated-files` - issue-specific generated reports and files.
- `/data/outputs/issue-clusters` - public-safe similar-issue cluster summaries and local correction state.
- `/data/outputs/metadata-cache` - read-only Production metadata retrievals.
- `/data/outputs/metadata-workspaces` - Sandbox attempts, rollback evidence, and confirmed packages.
- `/data/.sf` and `/data/.sfdx` - Salesforce CLI state.

Do not commit runtime outputs, credentials, Salesforce metadata retrievals, Jira issue data, screenshots, or logs.

## Repository Layout

```text
app.py                         Flask app, APIs, Settings, pipeline launcher
jira_sync.py                   Jira sync helper
caseops_paths.py               Runtime path helpers
skill_registry.py              Skill metadata loader
docker-compose.example.yml     Compose template
Dockerfile                     Published image build
docker/                        Docker-only runtime files
templates/                     HTML templates
static/                        CSS and static assets
skills/                        Canonical CaseOps Claude Code skills
scripts/                       Runtime helper scripts
docs/                          Shareable user and Docker docs
```

## Documentation

- [CaseOps Quickstart](docs/CASEOPS_QUICKSTART.md)
- [Docker Setup](docs/DOCKER_SETUP.md)
- [User Guide](docs/USER_GUIDE.md)
- [Docker Image Test Guide](docs/TESTER_GUIDE.md)
- [Project Overview](docs/PROJECT_OVERVIEW.md)
- [Documentation Index](docs/README.md)

## Development Notes

Canonical CaseOps skills live in `skills/`.

The Docker image copies only product files: app source, templates, static assets, skills, scripts, Docker runtime files, and sanitized examples. Local planning notes, Claude runtime state, retrieved metadata, generated outputs, and private tests are intentionally excluded from the shareable source.

Before publishing a new image, verify:

```bash
python -m unittest discover tests
python -m py_compile app.py jira_sync.py skill_registry.py caseops_paths.py scripts/sf_caseops_helper.py issue_clusters.py
```

Also run a container smoke test and confirm `/health` returns `{"ok": true}` before pushing a numbered image tag and `latest`.

## Security

Never commit or share:

- `.env`
- Jira API tokens
- Salesforce access tokens or refresh tokens
- SFDX auth URLs
- Salesforce frontdoor/session URLs
- Jira issue exports with customer data
- Salesforce record IDs from real orgs
- full pipeline logs

If a secret is committed or shared, rotate it immediately.

## Support

When reporting an issue, include:

- CaseOps version from Settings,
- Docker image tag,
- Docker host OS,
- browser and version,
- the checklist step or action that failed,
- a short redacted log excerpt.

Do not include credentials, customer names, internal hostnames, private Jira keys, Salesforce record IDs, or full logs.
