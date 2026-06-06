# CaseOps Instance Routing

## Rule

Code is shared. Runtime state is instance-scoped.

The active instance is determined by Flask startup arguments and environment:

- `--workspace`
- `--outputs-dir`
- `--env-file`
- `CASEOPS_DATA_DIR`
- `CASEOPS_OUTPUTS_DIR`
- `CASEOPS_ENV_FILE`
- `CASEOPS_TEMP_DIR`

Claude Code subprocesses inherit the same paths from `app.py`.

## Current Docker Instance

```text
/data
/data/outputs
/data/outputs/metadata-cache
/data/outputs/metadata-workspaces
/data/.env
/tmp/caseops
```

Common compose mapping:

```yaml
volumes:
  - ./caseops-data:/data
  - ./.env:/data/.env
```

## Allowed Runtime Writes

- `CASEOPS_DATA_DIR`
- `CASEOPS_OUTPUTS_DIR`
- `outputs/settings/canned-messages.json`
- `outputs/org-knowledge/`
- `outputs/pipeline-logs/`
- `CASEOPS_METADATA_ROOT`
- `CASEOPS_METADATA_CACHE_DIR`
- `CASEOPS_METADATA_WORKSPACES_DIR`
- `CASEOPS_METADATA_RAW_PROD_DIR`
- `CASEOPS_METADATA_SANDBOX_WORK_DIR`
- `CASEOPS_METADATA_CONFIRMED_DIR`
- active env file, normally `/data/.env`
- temp directory, normally `/tmp/caseops`

## Forbidden Runtime Writes

- root `outputs/` in a containerized deployment
- root `temp*`
- root `retrieve*`
- root `deploy*`
- root `metadata*`
- root `force-app/` in the Git repo
- root `.sf`
- root `.sfdx`
- root `.claude`

Shared source folders such as `skills/`, `static/`, `templates/`, and `scripts/` are code. They should only change during source edits, not pipeline execution.

## Metadata Workspace

```text
${CASEOPS_METADATA_WORKSPACES_DIR}/
  <KEY>/
    metadata-workspace.json
    attempt-001/
      baseline-sandbox/
      candidate/
      revert/
    confirmed/
      support-owned/
      engineering-proposal/
```

## Runtime Checks

Inside the container:

```bash
env | grep CASEOPS_
sf org display --target-org "$CASEOPS_PRODUCTION_READ_ORG" --json
sf data query --target-org "$CASEOPS_PRODUCTION_READ_ORG" --query "SELECT Id FROM Organization LIMIT 1" --json
```

Do not test frontdoor or magic-link session IDs as API bearer tokens.
