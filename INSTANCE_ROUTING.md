# CaseOps Instance Routing Policy

## Critical Rule

Every runtime action must route through the active CaseOps instance. Code is shared; state is not.

The Flask process decides the active instance from `--workspace`, `--outputs-dir`, `--env-file`, and the mounted `.env.jira` file. Claude Code subprocesses inherit that same routing through environment variables set by `app.py`.

## Current Runtime Model

```
ROOT/                              # shared codebase
├── app.py
├── skills/
├── static/
├── templates/
├── scripts/
│
├── instance1/
│   ├── outputs/                   # issue artifacts, logs, settings overrides
│   └── .temp/
│       └── metadata/              # Salesforce metadata workspace
│           ├── raw-production/
│           ├── sandbox-work/
│           └── confirmed/
│
└── instance2/
    ├── outputs/
    └── .temp/
        └── metadata/
```

For the NAS deployment, the persistent host paths are:

- Stack/code/env: `/volume1/docker/stacks/caseops`
- App data as configured by compose: `/volume1/docker/appdata/caseops`
- Active container env file: `/app/.env.jira`, bind-mounted from `.env.jira.nas`

## Allowed Writes

- `OUTPUTS/...`
- `CASEOPS_OUTPUTS_DIR/...`
- `OUTPUTS/settings/canned-messages.json`
- `OUTPUTS/pipeline-logs/...`
- `OUTPUTS.parent/.temp/metadata/...`

Shared source folders such as `skills/`, `static/`, `templates/`, and `scripts/` are code and should only change during source edits, not during pipeline execution.

## Forbidden Runtime Writes

- `ROOT/outputs`
- `ROOT/temp*`
- `ROOT/retrieved_metadata*`
- `ROOT/retrieve-prod`
- `ROOT/.sfdx`
- `ROOT/.sf`
- `ROOT/.claude`
- Any ad hoc root-level `deploy*`, `retrieve*`, or `metadata*` directory

If metadata is being retrieved or deployed, use the metadata workspace variables below.

## Environment Variables

Set by Flask and inherited by Claude Code subprocesses:

| Variable | Purpose |
| --- | --- |
| `CASEOPS_OUTPUTS_DIR` | Instance output directory |
| `CASEOPS_JIRA_OUT_DIR` | Instance Jira output directory |
| `CASEOPS_JIRA_ENV_FILE` | Active env file for Jira/Salesforce/Claude settings |
| `CASEOPS_TEMP_DIR` | Instance runtime temp directory |
| `CASEOPS_METADATA_ROOT` | Instance Salesforce metadata workspace root |
| `CASEOPS_METADATA_RAW_PROD_DIR` | Read-only Production retrievals |
| `CASEOPS_METADATA_SANDBOX_WORK_DIR` | Per-issue, per-attempt Sandbox work |
| `CASEOPS_METADATA_CONFIRMED_DIR` | Confirmed Support or Engineering proposal packages |

Claude auth comes from `CLAUDE_CODE_OAUTH_TOKEN` in the active env file. Salesforce CLI auth is created inside the container from Salesforce tokens in the active env file. CaseOps no longer relies on per-instance `.claude`, `.sfdx`, or `.sf` directories under the repo.

## Metadata Workspace

Production retrievals and deployable metadata are not mixed.

```
${CASEOPS_METADATA_ROOT}/
├── raw-production/
│   └── HEAL-12345/                # Production metadata, read-only evidence
├── sandbox-work/
│   └── HEAL-12345/
│       ├── metadata-workspace.json
│       └── attempt-001/
│           ├── baseline-sandbox/  # Sandbox state before attempt
│           ├── candidate/         # Candidate metadata deployed for test
│           └── revert/            # Rollback package or destructive changes
└── confirmed/
    └── HEAL-12345/
        ├── support-owned/
        └── engineering-proposal/
```

Rules:

- Do not edit files under `raw-production/`.
- Capture `baseline-sandbox/` before every Sandbox deploy attempt.
- Revert failed or abandoned attempts before starting the next attempt.
- Copy passed packages to `confirmed/`.
- Keep `metadata-workspace.json` updated with attempt number, touched components, paths, outcome, and revert status.

## Validation Enforcement

`app.py` calls `_validate_instance_path(path, operation)` before critical writes. It hard-stops known shared-root paths and keeps generated files under the active instance.

Key checked areas:

- Pipeline log writes
- Manifest/status writes
- Generated issue artifacts
- Settings persistence such as canned messages

## Isolation Checks

### Outputs

```bash
ls -la instance1/outputs/pipeline-logs/
ls -la instance2/outputs/pipeline-logs/
```

### Metadata

```bash
ls -la instance1/.temp/metadata/raw-production/
ls -la instance1/.temp/metadata/sandbox-work/
ls -la instance1/.temp/metadata/confirmed/
```

### Salesforce Runtime

Use the runtime preflight in Settings or the API status endpoints. For CLI checks inside the container, verify `sf` sees the configured aliases and can query each org:

```bash
sf org display --target-org <alias> --json
sf data query --target-org <alias> --query "SELECT Id FROM Organization LIMIT 1" --json
```

Do not test frontdoor or magic-link session IDs as API bearer tokens.

## Incident Response

If cross-instance contamination is suspected:

1. Check whether writes are under `OUTPUTS` or `.temp/metadata`.
2. Check `CASEOPS_OUTPUTS_DIR`, `CASEOPS_JIRA_ENV_FILE`, and `CASEOPS_METADATA_ROOT` in the pipeline log preflight.
3. Search for root-level `temp*`, `retrieve*`, `deploy*`, or `metadata*` directories.
4. Move or archive needed evidence, then remove stale root-level runtime folders.
5. Add or tighten `_validate_instance_path` if a new unsafe path pattern appears.
