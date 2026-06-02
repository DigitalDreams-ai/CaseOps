# CaseOps Instance Routing

## Rule

Code is shared. Runtime state is instance-scoped.

The active instance is determined by Flask startup arguments and environment:

- `--workspace`
- `--outputs-dir`
- `--env-file`
- `CASEOPS_OUTPUTS_DIR`
- `CASEOPS_JIRA_ENV_FILE`

Claude Code subprocesses inherit the same paths from `app.py`.

## Current NAS Instance

```text
/app/instance1/outputs
/app/instance1/.temp/metadata
/app/.env.jira
```

Host paths:

```text
/volume1/docker/stacks/caseops/instance1/outputs
/volume1/docker/stacks/caseops/.env.jira.nas
```

## Allowed Runtime Writes

- `CASEOPS_OUTPUTS_DIR`
- `outputs/settings/canned-messages.json`
- `outputs/org-knowledge/`
- `outputs/pipeline-logs/`
- `CASEOPS_METADATA_ROOT`
- `CASEOPS_METADATA_RAW_PROD_DIR`
- `CASEOPS_METADATA_SANDBOX_WORK_DIR`
- `CASEOPS_METADATA_CONFIRMED_DIR`
- active env file `/app/.env.jira`

## Forbidden Runtime Writes

- root `outputs/`
- root `temp*`
- root `retrieve*`
- root `deploy*`
- root `metadata*`
- root `.sf`
- root `.sfdx`
- root `.claude`

Shared source folders such as `skills/`, `static/`, `templates/`, and `scripts/` are code. They should only change during source edits, not pipeline execution.

## Metadata Workspace

```text
${CASEOPS_METADATA_ROOT}/
  raw-production/<KEY>/
  sandbox-work/<KEY>/
    metadata-workspace.json
    attempt-001/
      baseline-sandbox/
      candidate/
      revert/
  confirmed/<KEY>/
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
