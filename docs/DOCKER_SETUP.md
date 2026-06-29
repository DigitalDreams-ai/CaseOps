# CaseOps Docker Setup

This is the generic Docker setup for someone testing or running CaseOps from a published image.

## Image

Current image:

```text
ghcr.io/digitaldreams-ai/caseops:0.1.49
```

You can also use `ghcr.io/digitaldreams-ai/caseops:latest`, but a numbered tag is easier to support.

## Compose File

Use the provided `docker-compose.example.yml` as `docker-compose.yml`.

The important model is:

- the application runs from the image,
- `/data` is persistent runtime data,
- `.env` is mounted at `/data/.env` so Settings can update tokens,
- the app listens on container port `8080`,
- the default host port is `5350`.

Example:

```yaml
services:
  caseops:
    image: ghcr.io/digitaldreams-ai/caseops:0.1.49
    ports:
      - "${CASEOPS_HOST_PORT:-5350}:8080"
    env_file:
      - .env
    environment:
      CASEOPS_PORT: "8080"
      CASEOPS_DATA_DIR: /data
      CASEOPS_OUTPUTS_DIR: /data/outputs
      CASEOPS_JIRA_OUT_DIR: /data/outputs/jira
      CASEOPS_ENV_FILE: /data/.env
      CASEOPS_TEMP_DIR: /tmp/caseops
      CLAUDE_CODE_TMPDIR: /tmp/caseops/claude-code
      HOME: /home/caseops
      SF_DATA_DIR: /data/.sf
      SFDX_DIR: /data/.sfdx
    volumes:
      - ./caseops-data:/data
      - ./.env:/data/.env
    restart: unless-stopped
```

## Env File

Copy:

```bash
cp .env.example .env
```

Fill in:

- Jira base URL, email, and API token.
- Default Jira assignee, if you use issue assignment filtering.
- Production read org alias.
- Sandbox target org alias.
- Production and Sandbox Salesforce URLs.
- Claude auth mode, normally `CASEOPS_LLM_AUTH=claude_code`.

You can leave Salesforce and Claude tokens blank initially and paste them through Settings.

Upgrade note: CaseOps now uses `.env` as the single env filename. If an older local setup has a Jira-specific env filename, rename or copy it to `.env` before starting.

## Start

```bash
docker compose pull
docker compose up -d
```

Open:

```text
http://localhost:5350
```

## Image Smoke Test

Before deploying a newly built or newly pulled image, you can verify that the
image contains the required CaseOps modules, scripts, and knowledge files:

```bash
docker run --rm --entrypoint python3 ghcr.io/digitaldreams-ai/caseops:0.1.49 /app/scripts/docker_image_smoke.py
```

Use `--entrypoint python3` so Docker runs the smoke test directly instead of
starting the normal CaseOps service entrypoint.

## Stop, Restart, Update

Stop:

```bash
docker compose down
```

Restart:

```bash
docker compose restart caseops
```

Update to the image tag in your compose file:

```bash
docker compose pull
docker compose up -d --force-recreate
```

`latest` is a mutable Docker tag. If you choose to use `ghcr.io/digitaldreams-ai/caseops:latest`,
run `docker compose pull` before recreating the container. Otherwise Docker may reuse the
locally cached `latest` image and the running container may stay on an older build.

Confirm the updated image is running:

```bash
docker compose ps
docker compose logs --tail 100 caseops
curl -fsS http://localhost:5350/health
```

Then open Settings and confirm the displayed CaseOps version matches the image tag you intended to run.

Switch to a specific version:

```bash
CASEOPS_IMAGE=ghcr.io/digitaldreams-ai/caseops:0.1.49 docker compose up -d
```

On Windows PowerShell:

```powershell
$env:CASEOPS_IMAGE="ghcr.io/digitaldreams-ai/caseops:0.1.49"
docker compose up -d
```

## Logs and Health

Container status:

```bash
docker compose ps
```

Logs:

```bash
docker compose logs --tail 100 caseops
```

Health endpoint:

```bash
curl -fsS http://localhost:5350/health
```

Settings status:

```bash
curl -fsS http://localhost:5350/api/settings/status
```

## Persistent Data

The `caseops-data` folder contains runtime data:

- Jira raw bundles and summaries,
- issue artifacts,
- pipeline logs,
- generated files,
- metadata cache and workspaces,
- Salesforce CLI state,
- Settings-managed token updates.

Back it up before deleting the deployment folder.

## Authentication Notes

Salesforce:

```bash
sf org auth show-access-token -o <production-read-alias> --json
sf org auth show-access-token -o <sandbox-target-alias> --json
sf org auth show-sfdx-auth-url -o <production-read-alias> --json
sf org auth show-sfdx-auth-url -o <sandbox-target-alias> --json
```

Claude:

```bash
claude setup-token
```

Paste values in Settings. Do not commit `.env`, share tokens, or paste token values into bug reports.
