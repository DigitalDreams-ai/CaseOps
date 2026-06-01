# CaseOps Technical Overview

## Table of Contents
1. [Architecture](#architecture)
2. [Token Management System](#token-management-system)
3. [Pipeline Orchestration](#pipeline-orchestration)
4. [API Endpoints](#api-endpoints)
5. [Database & Storage](#database--storage)
6. [Security & Access Control](#security--access-control)
7. [Deployment](#deployment)
8. [Troubleshooting](#troubleshooting)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│  Flask Web App (app.py)                                     │
│  - REST API endpoints                                       │
│  - Dashboard rendering                                      │
│  - Token management & refresh                               │
│  - Salesforce/Jira API clients                              │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼───┐  ┌────▼────┐  ┌───▼─────┐
   │  Jira  │  │Salesforce│  │ Claude  │
   │  API   │  │   API    │  │  CLI    │
   └────────┘  └──────────┘  └─────────┘
        │            │            │
   ┌────▼─────────────┴────────────▼─────────┐
   │  Outputs Directory Structure             │
   │  instance1/                              │
   │  ├── outputs/                            │
   │  │   ├── jira/                           │
   │  │   ├── investigations/                 │
   │  │   ├── internal-notes/                 │
   │  │   ├── jira-messages/                  │
   │  │   ├── test-reports/                   │
   │  │   ├── engineering-escalations/        │
   │  │   └── pipeline-logs/                  │
   │  └── .temp/                              │
   └──────────────────────────────────────────┘
```

### Request Flow

```
1. User clicks "Auto-Process All" on dashboard
   ↓
2. Flask receives POST /api/run with action="full"
   ↓
3. Flask spawns: `claude -p <orchestrator prompt>`
   ↓
4. Claude Code subprocess:
   - Reads `skills/jira-salesforce-fix-pipeline/SKILL.md` and `references/workflow.md`
   - Executes jira_sync.py (Step 1)
   - Calls sub-agents for Steps 3, 5, 6, 9, and 10
   - Collects outputs
   - Exits
   ↓
5. Flask reads pipeline-logs/__global__.jsonl
   ↓
6. Dashboard updates with results
   - Badge states change
   - New files appear
   - Issue detail panel refreshes
```

---

## Token Management System

### Access Token Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│  0h: Token Issued (Valid)                                │
│  - Access token: ~1000 char OAuth token                  │
│  - Refresh token: Separate long-lived token              │
│  - Stored: .env.jira (SF_PROD_ACCESS_TOKEN etc.)         │
│  - SF_TOKENS_REFRESHED_AT = current timestamp            │
└──────────────────────────────────────────────────────────┘
                       │
                       │ (4h of operation)
                       ▼
┌──────────────────────────────────────────────────────────┐
│  4h: Auto-Refresh Window (Warning Threshold)             │
│  - Startup check: if age > 4h, trigger refresh           │
│  - Call: _refresh_salesforce_token_from_refresh_token()  │
│  - New token obtained via OAuth2 refresh_token grant     │
│  - Update .env.jira with new token + new timestamp       │
│  - App continues without interruption                    │
└──────────────────────────────────────────────────────────┘
                       │
                       │ (4h more)
                       ▼
┌──────────────────────────────────────────────────────────┐
│  8h: Token Expiration (Hard Deadline)                    │
│  - If no refresh token: token becomes invalid            │
│  - If refresh token: already refreshed at 4h mark        │
│  - Without refresh: Pipeline cannot access Salesforce    │
│  - With refresh: Already renewed, operating normally     │
└──────────────────────────────────────────────────────────┘
```

### Token Refresh Mechanism

**File:** `app.py`, functions:
- `_refresh_salesforce_token_from_refresh_token()` (line 147)
- `_check_and_refresh_salesforce_tokens()` (line 176)
- `_attempt_token_refresh()` (line 240)

**Flow:**

1. **Startup:**
   ```python
   _check_and_refresh_salesforce_tokens(env_file_path)
   ```
   - Reads SF_TOKENS_REFRESHED_AT from .env.jira
   - If missing: initialize to now + attempt refresh
   - If age > 8h: warn (don't crash), attempt refresh
   - If age > 4h: attempt refresh
   - Update .env.jira with new timestamp

2. **OAuth Token Refresh:**
   ```
   POST <configured-login-or-instance-url>/services/oauth2/token
   grant_type=refresh_token
   refresh_token=<refresh_token>
   client_id=PlatformCLI
   ```
   - Returns new access_token
   - Old token immediately invalidated
   - New token valid for 8 more hours

3. **Persistence:**
   - Write to `/app/.env.jira`
   - Docker mounts from NAS: `/volume1/docker/stacks/caseops/.env.jira.nas`
   - Survives container restarts
   - Next startup reads fresh tokens

### Auto-Refresh Configuration

**With Refresh Tokens (Recommended):**
```env
SF_PROD_ACCESS_TOKEN=<current access token>
SF_PROD_REFRESH_TOKEN=<long-lived refresh token>
CASEOPS_PRODUCTION_INSTANCE_URL=https://login.salesforce.com
SF_SANDBOX_ACCESS_TOKEN=<current access token>
SF_SANDBOX_REFRESH_TOKEN=<long-lived refresh token>
CASEOPS_SANDBOX_INSTANCE_URL=https://test.salesforce.com
SF_TOKENS_REFRESHED_AT=<unix timestamp>
```
- Startup auto-refreshes at 4h mark
- No manual intervention needed
- Pipeline runs indefinitely

**Without Refresh Tokens:**
```env
SF_PROD_ACCESS_TOKEN=<current access token>
# SF_PROD_REFRESH_TOKEN=<missing>
SF_TOKENS_REFRESHED_AT=<unix timestamp>
```
- Manual refresh required every 8h
- User navigates to /setup/refresh-salesforce-tokens
- Must re-authenticate locally: `sf org login web --alias 10xhealth`

### Token Sources

| Source | Method | Duration | Refresh? |
|--------|--------|----------|----------|
| `sf org auth show-access-token --json` | Access token only (`result.accessToken`) | 8h | Manual |
| `sf org auth show-sfdx-auth-url --json` | SFDX auth URL containing refresh token (`result.sfdxAuthUrl`) | 8h + refresh-token lifetime | Auto |
| Salesforce CLI auth cache (`~/.sf/`, older `~/.sfdx/`) | Local OAuth material used by `sf` | Depends on org policy | Local CLI only |
| `.env.jira` | Manual paste | 8h | Manual or Auto |

**Best practice:** Use `sf org login web`, then paste `result.accessToken` from `sf org auth show-access-token --json` and `result.sfdxAuthUrl` from `sf org auth show-sfdx-auth-url --json` into the CaseOps refresh page. CaseOps stores only the access token plus extracted refresh token in `.env.jira`.

---

## Pipeline Orchestration

### Pipeline Steps (1-12)

| Step | Name | Owner | Input | Process | Output | Time |
|------|------|-------|-------|---------|--------|------|
| 1-2 | Setup (Sync + Triage) | Orchestrator | Jira API | Fetch + classify cases | `jira/*.md` + folders | 3m |
| 3 | Analysis | Sub-agent | Jira + SF | Root cause research | Context summary | 3m |
| 4 | Hypothesis | Orchestrator | Analysis | Synthesize fix proposal | `step-4-hypothesis/*.md` | 2m |
| 5 | Metadata Retrieval | Sub-agent | Hypothesis | Retrieve Production metadata | Context summary | 2m |
| 6 | Problem Location | Sub-agent | Metadata | Drill to exact artifact | Context summary | 2m |
| 7 | Escalation Gate | Orchestrator | Problem location | Decide: Support or Engineering | Routing decision | 1m |
| 8 | Implement | Orchestrator | Hypothesis | Code local changes (both paths) | Investigation notes | 1m |
| 9 | Deploy + Test | Sub-agent | Hypothesis + Routing | Deploy to Sandbox + test (both paths) | `test-reports/*.md` | 3m |
| 10 | Messaging | Sub-agent | Results + Routing | Draft customer + internal + escalation | `jira-messages/*.md` + `engineering-escalations/*.md` (if escalating) | 1m |
| 11 | Summary | Orchestrator | All steps | Rollup report | `issue-summary-YYYY-MM-DD.md` | 1m |
| 12 | Return to User | Orchestrator | Summary | Print completion | Console output | 0m |

### Sub-Agent Architecture

**Skill files:** `skills/jira-salesforce-fix-pipeline/`

Specialized steps run as **sub-agents** with specific prompts and context:
- `jira-issue-analysis` — Step 3
- `salesforce-production-metadata-investigation` — Step 5
- `salesforce-production-metadata-investigation` drilling mode — Step 6
- `salesforce-sandbox-deploy-test` — Step 9
- `jira-response-drafting` — Step 10
- Orchestrator runs Steps 1, 2, 4, 7, 8, 11, and 12

### Pipeline State Machine

```
UNTRIAGED
   │
   ├─→ [Step 3: Investigation]
   │
   ▼
INVESTIGATING
   │
   ├─→ [Step 4: Hypotheses]
   │
   ▼
ANALYZED
   │
   ├─→ [Step 6: Sandbox Test]
   │
   ▼
VALIDATED
   │
   ├─→ [If eng_handoff file exists]
   │
   ▼
ESCALATED_TO_ENGINEERING
   │
   └─→ (Handoff to Engineering)
```

**Transitions triggered by:**
- File existence: `investigations/HEAL-*.md` → INVESTIGATING
- File existence: `step-4-hypothesis/HEAL-*.md` → ANALYZED
- File existence: `test-reports/HEAL-*.md` → VALIDATED
- File existence: `engineering-escalations/HEAL-*.md` + `eng_handoff/HEAL-*.md` → ESCALATED

---

## API Endpoints

### Issue & Pipeline

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/issues` | List all issues with flags |
| GET | `/api/issue/<key>` | Single issue detail + files |
| POST | `/api/run` | Trigger pipeline action |
| GET | `/api/pipeline-log/<key>` | Streaming pipeline output |
| POST | `/api/pipeline-log/clear` | Delete log file |

### Token Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/setup/refresh-salesforce-tokens` | HTML form for manual refresh |
| POST | `/api/setup/refresh-salesforce-tokens` | Save tokens + refresh |
| POST | `/api/setup/salesforce-auth` | Auth SF CLI orgs |
| GET | `/api/status` | Get active issues + LLM backend info |

### Claude Authentication

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/setup/claude-login` | HTML wizard for saving a Claude Code OAuth token |
| POST | `/api/setup/claude-credentials` | Save `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` |

### System

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Dashboard |
| GET | `/settings` | Settings page |
| POST | `/api/restart` | Graceful restart |

---

## Database & Storage

### File Structure

```
outputs/
├── jira/
│   ├── raw/HEAL-*.json          # Raw Jira issue JSON
│   ├── summary/HEAL-*.md        # Parsed issue summaries
│   └── manifest.csv             # Issue list + metadata
├── investigations/
│   └── HEAL-*.md                # Root cause analysis
├── internal-notes/
│   └── HEAL-*.md                # Engineering notes
├── jira-messages/
│   └── HEAL-*.md                # Customer message draft
├── test-reports/
│   └── HEAL-*.md                # Sandbox test results
├── engineering-escalations/
│   └── HEAL-*.md                # Handoff docs
├── step-4-hypothesis/
│   └── HEAL-*.md                # Fix proposals
├── pipeline-logs/
│   ├── __global__.jsonl         # Full pipeline log
│   ├── HEAL-*.jsonl             # Per-issue logs
│   └── YYYY-MM-DD-*.log         # Timestamped runs
└── issue-summary-YYYY-MM-DD.md  # Daily rollup
```

### Salesforce Metadata Workspace

Salesforce metadata is managed outside `outputs/` so user-facing reports stay separate from raw and deployable metadata:

```
.temp/metadata/
├── raw-production/
│   └── HEAL-*/                    # Read-only Production retrievals
├── sandbox-work/
│   └── HEAL-*/
│       ├── metadata-workspace.json
│       └── attempt-001/
│           ├── baseline-sandbox/  # Sandbox state before deploy
│           ├── candidate/         # Candidate metadata deployed for this attempt
│           └── revert/            # Rollback package for failed attempts
└── confirmed/
    └── HEAL-*/
        ├── support-owned/         # Passed Support-owned package
        └── engineering-proposal/  # Passed proposal for Engineering handoff
```

Raw Production files are read-only evidence. Modified metadata is always issue-scoped and attempt-scoped. Failed or abandoned attempts must be reverted from `baseline-sandbox/` before another candidate is tested.

### Pipeline Log Format (JSONL)

Each line is JSON:
```json
{
  "ts": "2026-06-01T12:51:46.406337+00:00",
  "run_key": "HEAL-30437",
  "kind": "line|done|error",
  "text": "Investigation starting..."
}
```

**Types:**
- `line` — Status/progress message
- `done` — Task completed
- `error` — Failure (stops pipeline)

### Manifest Structure

File: `outputs/jira/manifest.csv`

```csv
Key,Status,Summary,Priority,Assignee,Updated,Due,HasNewComments
HEAL-30437,In Progress,Automate Shopify Network Order Release Process,Medium,sean@example.com,2026-05-29T11:08:58.216-0400,,true
```

Used for: Issue list, status tracking, SLA calculations.

---

## Security & Access Control

### Salesforce Access Control

**Production (10xhealth):**
- **Read-only** API calls
- Can query: metadata, org config, user data
- Cannot deploy, execute scripts, modify data
- Used for: Investigation, metadata analysis

**Sandbox (10xhealth-sean):**
- **Full deploy access**
- Can deploy metadata changes
- Can run test code
- Used for: Testing fixes before Production

CaseOps does not promote metadata to Production. Passed Sandbox packages are saved under `.temp/metadata/confirmed/<KEY>/...` for operator-controlled Gearset or standard change control.

### Token Security

**Storage:**
- Never logged or printed (redacted in debug output)
- Stored in `.env.jira` (restricted permissions: 0o600)
- Loaded by Docker from the active env file
- NAS storage: restricted to docker user only

**Rotation:**
- Access tokens: 8h automatic rotation
- Refresh tokens: Indefinite (user controls revocation)
- Immediate invalidation on refresh

**Audit:**
- All SF API calls logged with timestamp
- User who ran pipeline recorded
- Escalation docs include investigation audit trail

### Claude Code Security

**Credentials:**
- Preferred auth is `CLAUDE_CODE_OAUTH_TOKEN`, generated by `claude setup-token`
- Stored in the active env file (`/app/.env.jira` in Docker; `.env.jira.nas` on the NAS host)
- Passed only to Claude Code CLI subprocesses; `ANTHROPIC_API_KEY` is removed in `claude_code` mode so it cannot override subscription auth
- Legacy credential files and `CLAUDE_CREDENTIALS_B64` are not used; missing `CLAUDE_CODE_OAUTH_TOKEN` blocks runtime preflight

**Capabilities:**
- Can invoke Claude API (limited to registered skills)
- Can read Jira + Salesforce APIs
- Cannot directly access Production data (read-only Salesforce token)
- All sub-agent prompts reviewed + approved

---

## Deployment

### Docker Setup

**File:** `docker-compose.yml`

```yaml
services:
  caseops:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "5350:5000"
    env_file:
      - .env.jira.nas
    volumes:
      - ./instance1/outputs:/app/instance1/outputs
      - ./.env.jira.nas:/app/.env.jira
    environment:
      CASEOPS_OUTPUTS_DIR: /app/instance1/outputs
      CASEOPS_WORKSPACE: default
```

**Key points:**
- The NAS container bind-mounts `app.py`, `templates/`, `static/`, and `skills/` read-only for predictable source and playbook updates
- Source/skill changes require sync to `/volume1/docker/stacks/caseops` plus container restart
- Dockerfile, dependency, npm/global CLI, or OS package changes require sync plus image rebuild and restart
- `.env.jira.nas` mounted writable because token refresh and Settings update `/app/.env.jira`
- Outputs directory volume-mounted (persistent across restarts)
- Port 5350 on host → 5000 in container

### Dockerfile

**File:** `Dockerfile`

Base image: `python:3.11`

Installs:
- Python dependencies: Flask, requests, etc.
- Salesforce CLI (sf)
- Claude Code CLI
- Git

Entrypoint: `docker-entrypoint.sh` → `python app.py`

### Multi-Instance Support

Two instances can run simultaneously:

**Instance 1 (default):**
```bash
docker-compose up -d
# Outputs: instance1/outputs/
# Port: 5350
# Env: CASEOPS_WORKSPACE=instance1
```

**Instance 2+ (separate containers):**
Create a second docker-compose override with different:
```yaml
services:
  caseops:
    ports:
      - "5351:5000"
    environment:
      - CASEOPS_WORKSPACE=instance2
    volumes:
      - ./instance2/outputs:/app/instance2/outputs
```

Each instance:
- Isolated outputs directory
- Separate .env.jira config (or shared)
- Separate Jira query (if needed)
- Optional: Different Salesforce orgs

---

## Troubleshooting

### Token Debugging

**Check current token age:**
```bash
ssh docker@10.0.1.10
docker exec caseops python -c "
import os, time, re
env = open('/app/.env.jira').read()
ts = int(re.search(r'SF_TOKENS_REFRESHED_AT=(\d+)', env).group(1))
age_h = (time.time() - ts) / 3600
print(f'Token age: {age_h:.1f}h')
"
```

**Check refresh token exists:**
```bash
docker exec caseops grep "SF_PROD_REFRESH_TOKEN=" /app/.env.jira
# If empty, no auto-refresh available
```

**Manual refresh trigger:**
```bash
docker exec caseops python -c "
from app import _check_and_refresh_salesforce_tokens
from pathlib import Path
_check_and_refresh_salesforce_tokens(Path('/app/.env.jira'))
"
```

### Salesforce API Issues

**Check org accessibility:**
```bash
sf org display --target-org <alias> --json
sf data query --target-org <alias> --query "SELECT Id FROM Organization LIMIT 1" --json
```

**If 401 INVALID_SESSION_ID:**
- Salesforce CLI access token expired or invalid
- Do not test frontdoor/magic-link SIDs as API bearer tokens; frontdoor links are browser UI sessions only
- Run token refresh
- Verify token format (check for typos)

### Pipeline Debugging

**Watch real-time logs:**
```bash
ssh docker@10.0.1.10
docker logs -f caseops | grep -E "ERROR|WARN|Step"
```

**Check specific issue logs:**
```bash
tail -f /volume1/docker/stacks/caseops/instance1/outputs/pipeline-logs/HEAL-30437.jsonl
```

**Inspect investigation file:**
```bash
cat /volume1/docker/stacks/caseops/instance1/outputs/investigations/HEAL-30437.md
```

### Container Restart

**Graceful:**
```bash
curl -X POST http://10.0.1.10:5350/api/restart
# Waits 1s, then kills app (Docker restarts)
```

**Force:**
```bash
ssh docker@10.0.1.10
cd /volume1/docker/stacks/caseops
docker-compose restart caseops
```

---

## Performance Tuning

### Caching

**Investigation cache** (in-memory):
- Stores: `has_investigation`, `has_solution` flags
- TTL: 1000 entries (auto-evict oldest)
- Rebuilt on app restart
- Located: `investigation_cache` dict in app.py

**SF Org list cache:**
- Caches: `sf org list --json` output
- TTL: 10 minutes
- Prevents repeated CLI calls
- Located: `_sf_orgs_cache` dict

### Optimization Tips

1. **Batch operations:** Run "Auto-Process All" instead of per-issue
2. **Off-peak runs:** Pipeline uses significant API quota (200+ Jira calls)
3. **Refresh tokens:** Enable auto-refresh to avoid manual interruptions
4. **Clean outputs:** Archive old `instance1/outputs/` directories (keep latest)

---

## Further Reading

- See [USER_GUIDE.md](USER_GUIDE.md) for operational docs
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design
- See [INSTANCE_ROUTING.md](INSTANCE_ROUTING.md) for instance isolation and metadata workspace rules
- See [skills/jira-salesforce-fix-pipeline/references/workflow.md](skills/jira-salesforce-fix-pipeline/references/workflow.md) for the authoritative pipeline workflow
