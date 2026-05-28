# Multi-Instance CaseOps (Architect-Approved Hybrid)

**Single codebase + isolated state per instance.** Code updates deploy once; state collisions are impossible.

---

## Architecture

```
CaseOps/                          ← shared code repo (git tracked)
  app.py
  requirements.txt
  ...all code files...
  
instance1/                        ← GITIGNORED (not tracked)
  .env.jira                       ← instance1 Jira/Salesforce config
  .sfdx/                          ← instance1 sf CLI auth + cache
  .claude/                        ← instance1 Claude Code state
  outputs/                        ← instance1 pipeline results
  launch.ps1                      ← instance1 launcher script
  
instance2/                        ← GITIGNORED (not tracked)
  .env.jira                       ← instance2 Jira/Salesforce config
  .sfdx/                          ← instance2 sf CLI auth + cache
  .claude/                        ← instance2 Claude Code state
  outputs/                        ← instance2 pipeline results
  launch.ps1                      ← instance2 launcher script
```

---

## Launch Both Instances

### Option 1: Automated (Recommended)

Run the launcher script to start both instances + comments poller:

```bash
.\scripts\start_gui.bat
```

This will:
1. Kill any existing processes on ports 5000 + 5351
2. Start comments poller (background)
3. Open Instance 1 in a new PowerShell window (port 5000)
4. Open Instance 2 in a new PowerShell window (port 5351)

Stop all instances:
```bash
.\scripts\stop_gui.bat
```

### Option 2: Manual

**Terminal 1 — Instance 1 (port 5000):**
```powershell
.\instance1\launch.ps1
```

**Terminal 2 — Instance 2 (port 5351):**
```powershell
.\instance2\launch.ps1
```

### Access

- Instance 1: http://localhost:5000
- Instance 2: http://localhost:5351

---

## State Isolation

Each instance is completely independent:

| Component | Instance 1 | Instance 2 |
|-----------|-----------|-----------|
| Jira/Salesforce auth | `instance1/.env.jira` | `instance2/.env.jira` |
| sf CLI state | `instance1/.sfdx/` | `instance2/.sfdx/` |
| Claude Code state | `instance1/.claude/` | `instance2/.claude/` |
| Pipeline outputs | `instance1/outputs/` | `instance2/outputs/` |
| Port | 5000 | 5351 |
| Workspace name | `instance1` | `instance2` |

**Zero cross-contamination:** One instance's sync, deploy, or Claude run cannot affect the other.

---

## Configuration

### Different Jira/Salesforce Org per Instance

Edit `instance2/.env.jira` with separate credentials:

```bash
# instance2/.env.jira
JIRA_BASE_URL=https://another-org.atlassian.net
JIRA_EMAIL=different-user@company.com
JIRA_API_TOKEN=...
CASEOPS_PRODUCTION_READ_ORG=different-prod-org
CASEOPS_SANDBOX_TARGET_ORG=different-sandbox-org
```

Instance 1 continues using root `.env.jira` config (copied to `instance1/.env.jira`).

### Same Org, Different Workstreams

Both instances can use the same Jira org + Salesforce orgs:
- Instance 1: handles support queue A
- Instance 2: handles support queue B
- Isolated outputs prevent file collisions

---

## Deployment & Updates

**Single code source = easy updates:**

```bash
# Pull latest from main
git pull

# Restart both instances (Ctrl+C in both terminals)
# Both instances now run updated code

# No separate deployments per instance; no code drift
```

---

## Scaling to 3+ Instances

Clone the pattern:

```bash
mkdir -p instance3/.sfdx instance3/.claude instance3/outputs
cp instance2/.env.jira instance3/.env.jira
cp instance2/launch.ps1 instance3/launch.ps1
```

Edit `instance3/launch.ps1`:
- Change `$Instance = "instance3"`
- Change `$Port = 5352` (or next available)

---

## Troubleshooting

**One instance blocked by another's port:**
- Check: `netstat -an | findstr :5000` or `:5351`
- Verify both instances are using different ports

**State files not isolated:**
- Verify `SF_DATA_DIR` and `CLAUDE_CODE_DIR` are set correctly (see launch.ps1 output)
- Check that `.sfdx/` and `.claude/` directories are in instanceN/, not repo root

**Instance can't find .env.jira:**
- Confirm file exists: `instance1/.env.jira`
- Verify launcher passes `--env-file` parameter

**One instance corrupted; need reset:**
```bash
# Clean instance1 state (keep code)
rm -r instance1/.sfdx/*
rm -r instance1/.claude/*
rm -r instance1/outputs/*

# Restart instance1
.\instance1\launch.ps1
```

---

## Files

### Code (Git tracked)
- `app.py` — Updated with `--outputs-dir` and `--env-file` parameters
- `.gitignore` — Updated to ignore all instance state directories
- `scripts/start_gui.bat` — Start both instances + comments poller
- `scripts/stop_gui.bat` — Stop both instances + comments poller

### Instance 1 (Git ignored)
- `instance1/launch.ps1` — Instance 1 launcher (port 5000)
- `instance1/.env.jira` — Instance 1 Jira/Salesforce config
- `instance1/.sfdx/` — Instance 1 sf CLI auth
- `instance1/.claude/` — Instance 1 Claude Code state
- `instance1/outputs/` — Instance 1 pipeline results

### Instance 2 (Git ignored)
- `instance2/launch.ps1` — Instance 2 launcher (port 5351)
- `instance2/.env.jira` — Instance 2 Jira/Salesforce config
- `instance2/.sfdx/` — Instance 2 sf CLI auth
- `instance2/.claude/` — Instance 2 Claude Code state
- `instance2/outputs/` — Instance 2 pipeline results
