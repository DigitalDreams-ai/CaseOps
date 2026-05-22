# Multi-Workspace CaseOps

Run two or more instances of CaseOps simultaneously, each serving a different Jira/Salesforce org with complete file isolation.

---

## Quick Start: Two Workspaces

### 1. Create Workspace Env Files

Copy `.env.jira` to create workspace-specific configs:

```bash
cp .env.jira .env.jira.job1
cp .env.jira .env.jira.job2
```

Edit `.env.jira.job1` and `.env.jira.job2` with the appropriate Jira/Salesforce credentials for each org.

### 2. Launch Two CaseOps Instances

**Terminal 1 (Job 1):**
```bash
CASEOPS_WORKSPACE=job1 python app.py --port 5000
```

**Terminal 2 (Job 2):**
```bash
CASEOPS_WORKSPACE=job2 python app.py --port 5001
```

### 3. Access Both Apps

- **Job 1:** http://localhost:5000 → reads/writes `outputs/job1/`, uses `.env.jira.job1`
- **Job 2:** http://localhost:5001 → reads/writes `outputs/job2/`, uses `.env.jira.job2`

Each topbar displays "CaseOps — job1" and "CaseOps — job2" respectively.

---

## File Isolation

Each workspace is completely isolated:

```
outputs/
  job1/
    jira/                    ← Jira summaries, manifest
    investigations/          ← Investigation records
    internal-notes/          ← Claude analysis
    jira-messages/           ← Draft Jira replies
    solutions/               ← Solution flags
    confidence-flags/        ← Confidence metadata
    ...
  job2/
    (same structure, completely separate data)
```

---

## Configuration Options

### Workspace Selection

**Option A — Environment Variable (recommended for scripts):**
```bash
export CASEOPS_WORKSPACE=job1
python app.py --port 5000
```

**Option B — CLI Argument:**
```bash
python app.py --workspace job1 --port 5000
```

**Option C — Both (CLI overrides env var):**
```bash
CASEOPS_WORKSPACE=default python app.py --workspace job1
# → uses job1 (CLI wins)
```

### Port Selection

**Option A — Environment Variable:**
```bash
export CASEOPS_PORT=5001
python app.py --workspace job2
```

**Option B — CLI Argument:**
```bash
python app.py --workspace job2 --port 5001
```

---

## Env File Resolution

When launching with `--workspace myorg`, CaseOps looks for:

1. `.env.jira.myorg` (preferred, workspace-specific)
2. `.env.jira` (fallback if #1 missing)

**If neither exists:** app logs a warning and proceeds with empty env (no Jira credentials).

---

## Command-Line Interface

Both `run_pipeline.py` and `step8_agent.py` respect workspace isolation via CLI args:

```bash
# Pipeline for job2
python run_pipeline.py --outputs-dir outputs/job2 --env-file .env.jira.job2

# Single issue agent for job2
python step8_agent.py --key HEAL-33150 --outputs-dir outputs/job2 --env-file .env.jira.job2
```

When launched from Flask (via app.py), these args are passed automatically.

---

## Process Isolation

Two separate Flask processes = two separate:
- Memory, caches, connections
- File handles, working directories
- Jira auth tokens, API quotas

**No cross-contamination.** One workspace's sync or agent can never write to another's outputs.

---

## Nightly Pre-Computation (Optional)

Adapt `nightly_scheduler.py` to loop over workspaces if desired:

```python
# In nightly_scheduler.py, inside run_precompute():
for workspace in ["job1", "job2"]:
    outputs_dir = Path("outputs") / workspace
    completed, failed = run_nightly_precompute(outputs_dir=outputs_dir)
    logger.info(f"[{workspace}] Pre-computation: {completed} OK, {failed} fail")
```

Or schedule separate Tasks in Windows Task Scheduler for each workspace at staggered times.

---

## Troubleshooting

**App fails to start:**
- Check port is not already in use: `netstat -an | findstr :5000` (Windows) or `lsof -i :5000` (Mac/Linux)
- Verify `.env.jira.{workspace}` exists and is readable
- Check `outputs/{workspace}/` is writable

**Cross-contamination suspected:**
- Verify topbars show correct workspace names
- Check output directories: `ls outputs/job1/jira/manifest.csv` vs `outputs/job2/jira/manifest.csv`
- Restart both apps (Flask caches in-memory)

**Env file not being read:**
- Confirm file name matches: `.env.jira.myworkspace` (lowercase)
- Check for hidden characters in file name
- Try fallback: use `.env.jira` (no suffix) as the workspace-specific file

---

## Examples

### Daily Workflow: Two Org Support

**Morning setup:**
```bash
# Terminal 1
CASEOPS_WORKSPACE=healthcare python app.py --port 5000

# Terminal 2
CASEOPS_WORKSPACE=retail python app.py --port 5001
```

**Throughout day:**
- Healthcare team uses port 5000, syncs from healthcare Jira
- Retail team uses port 5001, syncs from retail Jira
- Both teams can sync/triage/process in parallel without interference

**End of day:**
- Ctrl+C in both terminals to shut down
- Files remain in `outputs/healthcare/` and `outputs/retail/`
- Tomorrow's run picks up where you left off

### CI/CD Integration

Run multi-workspace pipeline in CI without GUI:

```bash
# Job 1: daily pre-compute
python run_pipeline.py --workspace job1 --no-sync

# Job 2: daily pre-compute
python run_pipeline.py --workspace job2 --no-sync
```

(Assumes CI environment has `.env.jira.job1` and `.env.jira.job2` configured as secrets.)

---

## Defaults

- `CASEOPS_WORKSPACE` (env var): defaults to `"default"` if unset
- `CASEOPS_PORT` (env var): defaults to `5000` if unset
- `--workspace` (CLI arg): defaults to value of `CASEOPS_WORKSPACE` env var
- `--port` (CLI arg): defaults to value of `CASEOPS_PORT` env var (or `5000`)
