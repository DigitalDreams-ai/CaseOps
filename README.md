# CaseOps: Automated Salesforce Support Case Analysis & Fix Pipeline

CaseOps is an AI-powered platform for automating the investigation, analysis, and resolution of Salesforce support cases. It syncs cases from Jira, analyzes them using Claude AI, tests fixes in Salesforce sandboxes, and generates handoff documents for engineering teams.

## Quick Start

### Requirements
- Salesforce orgs (production + sandbox) with API access
- Jira instance with API token
- Claude Code CLI installed and a Claude Code subscription token
- Docker & docker-compose

### Setup (5 minutes)

1. **Clone & configure:**
   ```bash
   git clone <repo>
   cd CaseOps
   cp .env.jira.example .env.jira.nas
   ```

2. **Authenticate Salesforce and set tokens** (access tokens are valid for 8 hours):
   ```bash
   sf org login web --alias 10xhealth
   sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com

   sf org auth show-access-token -o 10xhealth --json
   sf org auth show-access-token -o 10xhealth-sean --json
   ```
   Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens` and paste each `result.accessToken`.
   For auto-refresh, also run `sf org auth show-sfdx-auth-url -o <alias> --json` and paste each `result.sfdxAuthUrl` into the matching refresh-token field.

3. **Set Claude authentication:**
   Run `claude setup-token`, then navigate to `http://localhost:5350/setup/claude-login` and paste the token printed by the CLI.

4. **Start the service:**
   ```bash
   docker-compose up -d
   ```

5. **Open dashboard:**
   http://localhost:5350

## Key Features

### 🔄 Automated Investigation Pipeline
- **Steps 1-2 — Setup (Sync + Triage):** Pulls active cases from Jira and classifies by status
- **Step 3 — Analysis:** Claude AI investigates root causes in Salesforce
- **Step 4 — Hypothesis:** Generates fix proposals with test plan
- **Steps 5-6 — Metadata Investigation:** Identifies exact artifact location and problem
- **Step 7 — Escalation Gate:** Decides if Support-resolvable or Engineering-required
- **Steps 8-9 — Implementation + Test:** Deploys fix to Sandbox and validates
- **Step 10 — Messaging:** Drafts customer message + internal notes + escalation doc (if needed)
- **Steps 11-12 — Summary + Report:** Generates daily rollup and completion report

### 📋 Badge System
- **✓ Synced** — Issue pulled from Jira
- **✓ Investigated** — Root cause analysis complete
- **✓ Notes** — Internal notes created
- **✓ Draft** — Customer message drafted
- **✓ Solution** — Fix tested and validated
- **📋 Needs Escalation** — File-based flag (pipeline decision)
- **🔀 Escalated to Engineering** — User explicitly escalated in Jira

### 🔐 Token Management (Auto-Refresh)
- Access tokens expire every **8 hours**
- Auto-refresh at **4-hour mark** using refresh tokens
- Manual refresh via dashboard if needed
- Safe startup: warns on expired tokens, doesn't crash

### 📱 Mobile-Responsive UI
- Hamburger menu for action buttons
- Collapsible sidebar on small screens
- Touch-friendly buttons and spacing
- Full functionality on iPhone/iPad

### 🛡️ Production Safety
- **Read-only** access to Production Salesforce
- All fixes tested in **Sandbox first**
- Manual authorization required for Production changes
- Detailed escalation audit trail

## Documentation

- **[USER_GUIDE.md](USER_GUIDE.md)** — How to use CaseOps, workflows, and token setup
- **[TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md)** — Architecture, APIs, token management, storage model
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System design and pipeline flow
- **[docs/DOCKER_SETUP.md](docs/DOCKER_SETUP.md)** — Docker/NAS setup
- **[INSTANCE_ROUTING.md](INSTANCE_ROUTING.md)** — Instance isolation and metadata workspace policy

## Common Tasks

### Run Pipeline on All Issues
1. Click **"Auto-Process All"** on dashboard
2. Monitor progress in logs
3. Issues flow through Steps 1-12 automatically

### Salesforce Metadata Workspace

Pipeline metadata is stored under the active instance's `.temp/metadata/` tree:

- `raw-production/<KEY>/` — read-only Production retrievals
- `sandbox-work/<KEY>/attempt-N/` — Sandbox baseline, candidate, and revert packages
- `confirmed/<KEY>/support-owned/` or `engineering-proposal/` — final tested package

Do not use root-level `temp*`, `retrieve*`, `deploy*`, or `metadata*` folders for runtime work.

### Manually Refresh Salesforce Tokens
1. Get fresh access tokens:
   ```bash
   sf org auth show-access-token -o 10xhealth --json
   sf org auth show-access-token -o 10xhealth-sean --json
   ```
2. Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens`
3. Paste each `result.accessToken`
4. Optional for auto-refresh: run `sf org auth show-sfdx-auth-url -o <alias> --json` and paste `result.sfdxAuthUrl` into the matching refresh-token field
5. Submit

### Set Up Claude Authentication
1. On your local machine, run `claude setup-token`
2. Copy only the token printed by the command
3. Navigate to `http://localhost:5350/setup/claude-login`
4. Paste the token and submit
5. CaseOps stores it as `CLAUDE_CODE_OAUTH_TOKEN` in the active env file

### Escalate an Issue
1. Click issue in sidebar
2. Click **"Settings"** (⚙ icon)
3. Change Jira status to **"Escalated to Engineering"**
4. Issue moves to engineering-escalations folder
5. Generate summary for handoff

## Troubleshooting

### "Salesforce tokens EXPIRED"
**Solution:** Refresh tokens via `/setup/refresh-salesforce-tokens` or provide refresh tokens for auto-refresh.

### "Claude Code auth token not configured"
**Solution:** Run `claude setup-token`, then save the token with `/setup/claude-login`.

### Pipeline stalled on Step 5
**Check:** Are Salesforce orgs reachable? Open Settings or call `/api/settings/status` to verify runtime preflight.

### Mobile layout broken
**Check:** Browser zoom is 100%, viewport meta tags loaded. See [CSS responsive rules](static/css/caseops.css#L1160).

## Support

- File issues: GitHub Issues
- Check logs: `docker logs caseops`
- SSH to NAS: `ssh docker@10.0.1.10`
- CaseOps files: `/volume1/docker/stacks/caseops`

## Architecture

CaseOps runs as a Flask app + Claude Code CLI subprocesses:
- **Flask** — REST API, dashboard, OAuth endpoints
- **Claude Code** — Skill execution (investigation, testing, messaging)
- **Jira API** — Issue sync, status updates
- **Salesforce API** — Metadata, deployments, queries
- **Docker** — Containerized on NAS at port 5350

See [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) for deep dive.

## License

Internal use only. Shulman Hill Medical Group.
