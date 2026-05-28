# CaseOps Multi-Instance Routing Policy

## Critical Rule
**Every action from any source must route to the associated instance.**

All file operations, API calls, subprocess executions, and Skill runs must enforce instance isolation through path routing.

## Architecture

```
ROOT (shared, read-only codebase)
├── force-app/          (shared Salesforce source)
├── skills/             (shared playbooks/workflow)
├── static/             (shared CSS/JS)
├── templates/          (shared HTML)
├── scripts/            (shared scripts)
├── app.py              (shared Flask app)
│
├── instance1/          (isolated state)
│   ├── outputs/        (instance1 outputs — all issues, investigations, notes, etc.)
│   ├── temp-retrieve/  (instance1 metadata retrieve, deploy artifacts)
│   ├── .sfdx/          (instance1 Salesforce CLI config, org aliases)
│   ├── .claude/        (instance1 Claude Code state)
│   └── .env.jira       (instance1 credentials: CASEOPS_PRODUCTION_READ_ORG=10xhealth)
│
└── instance2/          (isolated state)
    ├── outputs/        (instance2 outputs)
    ├── temp-retrieve/  (instance2 metadata retrieve, deploy artifacts)
    ├── .sfdx/          (instance2 Salesforce CLI config, org aliases)
    ├── .claude/        (instance2 Claude Code state)
    └── .env.jira       (instance2 credentials: CASEOPS_PRODUCTION_READ_ORG=shulman)
```

## Allowed Patterns (Safe)

### Read Operations
- ROOT/force-app, ROOT/skills, ROOT/static, ROOT/templates, ROOT/scripts (shared codebase — read-only)
- OUTPUTS / ... (instance-specific outputs)
- CASEOPS_OUTPUTS_DIR / ... (environment variable pointing to instance-specific outputs)
- instance1/.sfdx, instance2/.sfdx (via SF_DATA_DIR env var override)
- instance1/.claude, instance2/.claude (via CLAUDE_CODE_DIR env var override)

### Write Operations
- OUTPUTS / ... (instance-specific, auto-routed)
- ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve (instance-specific metadata/deploy)
- instance1/outputs, instance2/outputs (explicit instance routing)
- instance1/.sfdx, instance2/.sfdx (org configs, set via SF_DATA_DIR)

## Forbidden Patterns (HARD STOP)

✗ **Write to ROOT/outputs** — use OUTPUTS (instance-specific) instead
✗ **Write to ROOT/temp** — use ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve
✗ **Write to ROOT/temp-retrieve** — use ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve
✗ **Write to ROOT/temp_retrieve** — use ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve
✗ **Write to ROOT/Ctemp-sf-retrieve** — use ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve
✗ **Write to ROOT/retrieved_metadata** — use instance-specific output dir
✗ **Write to ROOT/retrieved_metadata_sharing** — use instance-specific output dir
✗ **Write to ROOT/retrieve-prod** — use instance-specific output dir
✗ **Write to ROOT/temp_admin_team** — use instance-specific output dir
✗ **Write to ROOT/.sfdx** — use SF_DATA_DIR env var (set by launcher)
✗ **Write to ROOT/.claude** — use CLAUDE_CODE_DIR env var (set by launcher)
✗ **Write to shared codebase** (skills/, static/, templates/, scripts/) — read-only

## Instance Routing In Practice

### Flask API Routes
- All file reads/writes checked via `_validate_instance_path(path, "write")`
- OUTPUTS global is set at startup to instance-specific path (from --outputs-dir)
- Manifest, investigations, notes, messages written to OUTPUTS (routed correctly)

### Claude Code Skill Subprocess
- Environment variables set by app.py:
  - `CASEOPS_OUTPUTS_DIR = str(OUTPUTS)` (instance-specific)
  - `CASEOPS_JIRA_OUT_DIR = str(OUTPUTS / "jira")` (instance-specific)
  - `CASEOPS_JIRA_ENV_FILE = path to instance-specific .env.jira` (instance-specific)
  - `SF_DATA_DIR = instance1/.sfdx or instance2/.sfdx` (from launcher)
  - `CLAUDE_CODE_DIR = instance1/.claude or instance2/.claude` (from launcher)
- Prompt injected with:
  - Instance output directory path (substitutes hardcoded "outputs/" with "${CASEOPS_OUTPUTS_DIR}/../...")
  - Instance .env.jira file path (tells Skill to read from correct org config)
  - Metadata temp directory (tells Skill where to write retrieved metadata/deploys)

### Sub-agent Spawning (Steps 5, 6, 9)
- Sub-agent prompts (in sub-agent-prompts.md) specify:
  - `${CASEOPS_OUTPUTS_DIR}/../temp-retrieve` for metadata retrieval
  - `--output-dir "${CASEOPS_OUTPUTS_DIR}/../temp-retrieve"` for all sf commands
- Sub-agents inherit environment variables from parent Skill subprocess
- Instance routing enforced at sub-agent prompt level

## Validation Enforcement

Function: `_validate_instance_path(path, operation)`
- Called before all critical writes (jira-message, internal-notes, manifest, logs)
- Raises RuntimeError if path violates routing rules
- HARD STOP — prevents cross-instance contamination

Checked locations:
- _save_claude_output (lines 851, 862): jira-message, internal-notes writes
- api_issue_mark_viewed (line 1620): manifest write
- _persist_pipeline_record (line 369): pipeline log write

## Environment Variables (Single Source of Truth)

Set by Flask app at startup, inherited by subprocesses:

| Variable | Set By | Value | Purpose |
|----------|--------|-------|---------|
| CASEOPS_WORKSPACE | --workspace CLI arg | instance1 or instance2 | Workspace name |
| CASEOPS_OUTPUTS_DIR | app.py _do_stream_claude_code_cli | instance{N}/outputs | Instance output directory for Skill |
| CASEOPS_JIRA_OUT_DIR | app.py _claude_process_env | instance{N}/outputs/jira | Jira data directory |
| CASEOPS_JIRA_ENV_FILE | app.py _claude_process_env | instance{N}/.env.jira path | Instance credentials file |
| SF_DATA_DIR | instance{N}/launch.ps1 | instance{N}/.sfdx | Salesforce CLI org aliases |
| CLAUDE_CODE_DIR | instance{N}/launch.ps1 | instance{N}/.claude | Claude Code state directory |

## Testing Instance Isolation

### Verify Outputs Routing
```bash
# Instance1 logs should be in instance1/outputs/pipeline-logs/
ls -la instance1/outputs/pipeline-logs/
# Instance2 logs should be in instance2/outputs/pipeline-logs/
ls -la instance2/outputs/pipeline-logs/
```

### Verify Metadata Separation
```bash
# Instance1 metadata should be in instance1/temp-retrieve/
ls -la instance1/temp-retrieve/
# Instance2 metadata should be in instance2/temp-retrieve/
ls -la instance2/temp-retrieve/
```

### Verify Salesforce Org Queries
```bash
# Instance1 queries should use --target-org 10xhealth
grep "target-org 10xhealth" instance1/outputs/pipeline-logs/*.jsonl

# Instance2 queries should use --target-org shulman
grep "target-org shulman" instance2/outputs/pipeline-logs/*.jsonl
```

### Verify .env.jira Usage
```bash
# Instance1 should have CASEOPS_PRODUCTION_READ_ORG=10xhealth
grep CASEOPS_PRODUCTION_READ_ORG instance1/.env.jira

# Instance2 should have CASEOPS_PRODUCTION_READ_ORG=shulman
grep CASEOPS_PRODUCTION_READ_ORG instance2/.env.jira
```

## Cross-Instance Contamination Prevention

### Outputs
✅ Instance-specific via OUTPUTS global, passed to Skill as CASEOPS_OUTPUTS_DIR

### Credentials
✅ Instance-specific via instance{N}/.env.jira, passed to Skill as CASEOPS_JIRA_ENV_FILE

### Salesforce Orgs
✅ Instance-specific via CASEOPS_PRODUCTION_READ_ORG in .env.jira

### Jira Data
✅ Instance-specific via CASEOPS_JIRA_OUT_DIR in Skill environment

### Retrieved Metadata
✅ Instance-specific via ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve in sub-agent prompts

### Deploy Artifacts
✅ Instance-specific via ${CASEOPS_OUTPUTS_DIR}/../temp-retrieve in sub-agent prompts

### Pipeline Logs
✅ Instance-specific via OUTPUTS_PIPELINE_LOGS global, validated via _validate_instance_path

### Org Aliases (.sfdx)
✅ Instance-specific via SF_DATA_DIR environment variable (set by launcher)

### Claude Code State (.claude)
✅ Instance-specific via CLAUDE_CODE_DIR environment variable (set by launcher)

## Deployment Checklist

- [ ] Instance launchers set SF_DATA_DIR, CLAUDE_CODE_DIR, CASEOPS_WORKSPACE
- [ ] Flask app accepts --workspace, --outputs-dir, --env-file CLI args
- [ ] _validate_instance_path enforces routing rules (HARD STOP on violation)
- [ ] All subprocess calls inherit instance env vars (CASEOPS_OUTPUTS_DIR, etc.)
- [ ] Sub-agent prompts specify --output-dir for all sf commands
- [ ] Pipeline logs written to OUTPUTS_PIPELINE_LOGS (instance-specific)
- [ ] Manifest operations write to OUTPUTS (instance-specific)
- [ ] Jira data synced to CASEOPS_JIRA_OUT_DIR (instance-specific)
- [ ] No hardcoded ROOT paths in instance operations (except shared codebase)

## Incident Response

If cross-instance contamination suspected:
1. **Check paths**: Is operation using OUTPUTS or instance-specific directories?
2. **Check env vars**: Are CASEOPS_OUTPUTS_DIR, CASEOPS_JIRA_OUT_DIR set correctly?
3. **Check prompts**: Are sub-agent prompts injecting correct output directory?
4. **Check .env.jira**: Are CASEOPS_PRODUCTION_READ_ORG correct in each instance?
5. **Review logs**: Do sf CLI commands have correct --target-org flag?
6. **Search ROOT**: Is any data accumulating in ROOT/temp-retrieve or ROOT/retrieved_metadata?

If found:
- Clean up the shared directory (ROOT/temp-retrieve, etc.)
- Verify _validate_instance_path is called before that write
- Add validation check if missing
- Re-test instance isolation
