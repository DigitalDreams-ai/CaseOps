# CaseOps Technical Overview

## Runtime Model

CaseOps is a Flask application that launches Claude Code CLI subprocesses for AI-assisted pipeline work.

Core components:

- `app.py` - Flask routes, settings, runtime preflight, pipeline launching, log streaming, path validation.
- `jira_sync.py` - Jira API sync into the active outputs directory, normally `/data/outputs/jira/`.
- `caseops_paths.py` - path helpers.
- `templates/` and `static/` - dashboard UI.
- `skills/` - Claude Code skills and sub-agent prompts.
- `scripts/sf_caseops_helper.py` - deterministic Salesforce helper for common metadata mechanics.

## Docker Runtime

The container runs as `caseops` and exposes Flask on container port `8080`. The default compose template maps host port `5350` to `8080`.

Mounted runtime paths:

- `/data` - persistent appdata
- `/data/.env` - writable env file managed by Settings
- `/data/.sf` and `/data/.sfdx` - Salesforce CLI state
- `/data/outputs` - Jira data, generated artifacts, logs, metadata cache, and metadata workspaces
- `/tmp/caseops` - disposable temp files

The application code lives inside the image. Do not bind-mount source files for normal tester/shared-image deployments.

The legacy repo-local `instance1/` and `instance2/` directories are not part of the Docker runtime model.

## Authentication

### Claude

CaseOps uses Claude Code CLI with:

```env
CASEOPS_LLM_AUTH=claude_code
CLAUDE_CODE_OAUTH_TOKEN=<token from claude setup-token>
```

The token is saved through `/setup/claude-login`.

### Salesforce

CaseOps stores Salesforce access and refresh tokens in the active env file and authenticates `sf` inside the container on demand.

Important env keys:

```env
CASEOPS_PRODUCTION_READ_ORG=prod-read
CASEOPS_SANDBOX_TARGET_ORG=sandbox
CASEOPS_PRODUCTION_INSTANCE_URL=https://login.salesforce.com
CASEOPS_SANDBOX_INSTANCE_URL=https://test.salesforce.com
SF_PROD_ACCESS_TOKEN=...
SF_SANDBOX_ACCESS_TOKEN=...
SF_PROD_REFRESH_TOKEN=...
SF_SANDBOX_REFRESH_TOKEN=...
SF_TOKENS_REFRESHED_AT=...
```

The access token can be copied from:

```bash
sf org auth show-access-token -o <alias> --json
```

The refresh token source can be copied from:

```bash
sf org auth show-sfdx-auth-url -o <alias> --json
```

`result.sfdxAuthUrl` is Salesforce's current auth URL field. CaseOps extracts the refresh token from it. This auth terminology is separate from legacy `sfdx force:*` commands, which CaseOps does not use.

## Salesforce Command Contract

CaseOps uses modern `sf` CLI commands only.

Allowed:

```bash
sf org display --target-org <alias> --json
sf data query --target-org <alias> --query "SELECT Id FROM Organization LIMIT 1" --json
sf project retrieve start --target-org <alias> --metadata CustomField:Case.Field__c --output-dir <dir> --json
sf project retrieve start --target-org <alias> --source-dir <path> --output-dir <dir> --json
sf project deploy start --target-org <sandbox> --source-dir <candidate> --json
sf project deploy start --target-org <sandbox> --metadata-dir <dir> --single-package --json
```

Forbidden for routine CaseOps retrieve/deploy:

- legacy `sfdx force:*`
- `package.xml`
- `--manifest`
- API calls using frontdoor/magic-link session IDs

## Pipeline

The pipeline is implemented by `skills/jira-salesforce-fix-pipeline`.

Sub-agents:

- Step 3: `jira-issue-analysis`
- Step 5: `salesforce-production-metadata-investigation`
- Step 6: `salesforce-production-metadata-investigation` drilling mode
- Step 9: `salesforce-sandbox-deploy-test`
- Step 10: `jira-response-drafting`

The orchestrator keeps sub-agent summaries compact and relies on files for detailed artifacts.

## Metadata Workspace

Current implementation:

```text
/data/outputs/metadata-cache/
  production/<org>/<api-version>/
    raw/<KEY>/
    summaries/
/data/outputs/metadata-workspaces/
  <KEY>/
    metadata-workspace.json
    attempt-N/
      baseline-sandbox/
      candidate/
      revert/
    confirmed/
      support-owned/
      engineering-proposal/
```

These paths are exposed to Claude subprocesses through:

- `CASEOPS_METADATA_ROOT`
- `CASEOPS_METADATA_CACHE_DIR`
- `CASEOPS_METADATA_WORKSPACES_DIR`
- `CASEOPS_METADATA_RAW_PROD_DIR`
- `CASEOPS_METADATA_SANDBOX_WORK_DIR`
- `CASEOPS_METADATA_CONFIRMED_DIR`

Runtime guards in `app.py` reject known unsafe root-level paths such as `temp*`, `retrieve*`, `deploy*`, and root `metadata*` folders.

## Org Knowledge

`/data/outputs/org-knowledge/` is persistent appdata. On startup, CaseOps seeds default files and non-destructively merges new required rules and index topics.

Current seeded areas:

- `helper-scripts.md`
- `run-rules.md`
- `salesforce-gotchas/*`
- `query-patterns/*`
- `deploy-patterns/*`
- `lessons-learned.md`

The orchestrator selects relevant files by keyword matching against the active issue and caps the injected context.

## Settings Persistence

Settings writes use the active env file or mounted outputs:

- Salesforce and Claude tokens: `/app/.env`
- Canned messages: `outputs/settings/canned-messages.json`
- Org knowledge: `outputs/org-knowledge/`

## Logging

Pipeline logs stream to the browser through SSE and are persisted under:

```text
outputs/pipeline-logs/
```

Log sanitization strips ANSI terminal control sequences and redacts Salesforce access-token patterns.
