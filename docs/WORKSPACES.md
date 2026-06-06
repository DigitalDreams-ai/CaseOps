# CaseOps Workspaces

Workspaces are a logical label for separating cache keys and pipeline state. In Docker, isolation should primarily come from separate containers with separate `/data` mounts.

Repo-local `instance1/` and `instance2/` directories are legacy local-development artifacts and are not required for the Docker image.

## Docker Pattern

Use separate compose projects:

```text
caseops-primary/
  docker-compose.yml
  .env
  caseops-data/
caseops-test/
  docker-compose.yml
  .env
  caseops-data/
```

Each stack maps its own appdata to `/data` and uses a unique host port.

## Local Development

For a second local process, pass explicit paths outside tracked source:

```bash
python app.py --workspace job1 --outputs-dir .local/job1/outputs --env-file .local/job1/.env --port 5000
python app.py --workspace job2 --outputs-dir .local/job2/outputs --env-file .local/job2/.env --port 5351
```

`.local/` should stay ignored.

CaseOps uses `.env` as the single default env filename. Workspaces isolate outputs and cache state; they do not automatically select a different env file. Use `--env-file` only when you intentionally want a custom local path.

## Isolation

Each workspace should have its own:

- env file
- outputs directory
- metadata workspace
- port
- Sandbox allowlist

## Metadata

Metadata defaults under the active outputs directory:

```text
<outputs-dir>/metadata-cache/
<outputs-dir>/metadata-workspaces/
```

Do not share a metadata workspace between two active instances.

## Operational Guidance

- Keep one active pipeline per issue.
- Check `/api/status` before restarting or deleting state.
- Do not copy Salesforce auth caches between workspaces. Use env-token auth.
