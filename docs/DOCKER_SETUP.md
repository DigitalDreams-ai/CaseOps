# CaseOps Docker Setup

## Current NAS Deployment

NAS access:

```bash
ssh docker@10.0.1.10
```

Paths:

```text
/volume1/docker/stacks/caseops      # stack, code, compose, env
/volume1/docker/appdata/caseops     # appdata reference
```

Container:

```text
caseops
```

Synology Docker binary:

```bash
/volume1/@appstore/ContainerManager/usr/bin/docker
```

## Compose Model

The pilot deployment bind-mounts source files for predictable updates:

```yaml
volumes:
  - ./instance1/outputs:/app/instance1/outputs
  - ./.env.jira.nas:/app/.env.jira
  - ./app.py:/app/app.py:ro
  - ./templates:/app/templates:ro
  - ./static:/app/static:ro
  - ./skills:/app/skills:ro
  - ./scripts:/app/scripts:ro
```

Current exposed port:

```text
host 5350 -> container 5000
```

## Start, Restart, Recreate

From the NAS stack directory:

```bash
cd /volume1/docker/stacks/caseops
/volume1/@appstore/ContainerManager/usr/bin/docker compose up -d caseops
/volume1/@appstore/ContainerManager/usr/bin/docker restart caseops
```

Use `compose up -d caseops` when `docker-compose.yml` mount definitions change. A plain restart is enough for `app.py`, `templates/`, `static/`, `skills/`, or `scripts/` changes because they are bind-mounted.

Use rebuild only for:

- `Dockerfile`
- Python dependencies
- npm/global CLI installs
- OS packages

```bash
cd /volume1/docker/stacks/caseops
/volume1/@appstore/ContainerManager/usr/bin/docker compose up -d --build caseops
```

## Authentication Files

NAS env file:

```text
/volume1/docker/stacks/caseops/.env.jira.nas
```

Container env file:

```text
/app/.env.jira
```

This file must be writable. CaseOps saves Salesforce token refreshes and Settings changes there.

## Claude Code Auth

On a local machine:

```bash
claude setup-token
```

Paste the token at:

```text
http://10.0.1.10:5350/setup/claude-login
```

CaseOps saves `CLAUDE_CODE_OAUTH_TOKEN` in the active env file. Do not mount host `~/.claude` into the container.

## Salesforce Auth

On an authenticated local machine:

```bash
sf org login web --alias 10xhealth
sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com

sf org auth show-access-token -o 10xhealth --json
sf org auth show-access-token -o 10xhealth-sean --json
sf org auth show-sfdx-auth-url -o 10xhealth --json
sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
```

Paste access tokens and optional full `result.sfdxAuthUrl` values at:

```text
http://10.0.1.10:5350/setup/refresh-salesforce-tokens
```

CaseOps authenticates `sf` inside the container from env tokens. Do not mount host `~/.sf` or `~/.sfdx`.

## Salesforce CLI Rules

Use modern `sf` CLI only. Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps retrieve/deploy.

The helper script is available inside Docker:

```bash
/volume1/@appstore/ContainerManager/usr/bin/docker exec caseops python /app/scripts/sf_caseops_helper.py --help
```

## Health Checks

Check active runs:

```bash
curl -fsS http://127.0.0.1:5350/api/status
```

Check logs:

```bash
/volume1/@appstore/ContainerManager/usr/bin/docker logs --tail 100 caseops
```

Check helper and syntax:

```bash
/volume1/@appstore/ContainerManager/usr/bin/docker exec caseops python /app/scripts/sf_caseops_helper.py --help
/volume1/@appstore/ContainerManager/usr/bin/docker exec caseops python -c "import py_compile; py_compile.compile('/app/app.py', cfile='/tmp/app.pyc', doraise=True)"
```

## Backups

Back up persistent issue artifacts:

```bash
tar czf ~/caseops-outputs.tgz -C /volume1/docker/stacks/caseops instance1/outputs
```

Back up persistent metadata cache and workspaces:

```bash
tar czf ~/caseops-metadata.tgz -C /volume1/docker/stacks/caseops instance1/outputs/metadata-cache instance1/outputs/metadata-workspaces
```
