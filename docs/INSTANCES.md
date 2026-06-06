# CaseOps Instances

CaseOps supports multiple instances by running the same image with different compose stack directories, ports, one `.env` file per stack, and appdata mounts.

The current Docker model does not require repo-local `instance1/` or `instance2/` directories. Runtime state should live in a mounted appdata directory and appear inside the container as `/data`.

## Docker Instance Pattern

Example host layout:

```text
caseops-primary/
  docker-compose.yml
  .env
  caseops-data/
    outputs/
caseops-test/
  docker-compose.yml
  .env
  caseops-data/
    outputs/
```

Each compose file should map its appdata to `/data`:

```yaml
volumes:
  - ./caseops-data:/data
  - ./.env:/data/.env
```

Each instance should have a unique host port:

```yaml
ports:
  - "5350:8080"
```

## Isolation

Each container has separate:

- `.env` file,
- `/data/.sf` and `/data/.sfdx`,
- `/data/outputs`,
- Jira manifest and issue artifacts,
- metadata cache and workspaces,
- pipeline logs,
- Sandbox allowlist settings.

## Runtime Paths

Inside the container:

```text
/data/
  .env
  .sf/
  .sfdx/
  outputs/
    metadata-cache/
    metadata-workspaces/
```

Temporary files should use `/tmp/caseops`.

## Local Development

For local non-Docker development, prefer `outputs/` in the repo root or a temp/appdata path passed with `--outputs-dir`. Do not commit local runtime directories.

## Reset One Instance

Stop the instance first, then archive or remove its state:

```bash
tar czf caseops-backup.tgz caseops-data
```

Do not delete state while a pipeline is active.
