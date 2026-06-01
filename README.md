# CaseOps: Automated Salesforce Support Case Analysis & Fix Pipeline

CaseOps is an AI-powered platform for automating the investigation, analysis, and resolution of Salesforce support cases. It syncs cases from Jira, analyzes them using Claude AI, tests fixes in Salesforce sandboxes, and generates handoff documents for engineering teams.

## Quick Start

### Requirements
- Salesforce orgs (production + sandbox) with API access
- Jira instance with API token
- Claude Code CLI authentication
- Docker & docker-compose

### Setup (5 minutes)

1. **Clone & configure:**
   ```bash
   git clone <repo>
   cd CaseOps
   cp .env.jira.example .env.jira.nas
   ```

2. **Set Salesforce tokens** (valid for 8 hours):
   ```bash
   sf org auth show-access-token -o 10xhealth --no-prompt     # prod
   sf org auth show-access-token -o 10xhealth-sean --no-prompt # sandbox
   ```
   Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens` and paste tokens.

3. **Set Claude authentication:**
   Navigate to `http://localhost:5350/setup/claude-login` and follow the wizard.

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

- **[USER_GUIDE.md](USER_GUIDE.md)** — How to use CaseOps, workflows, features
- **[TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md)** — Architecture, APIs, token management
- **[ARCHITECTURE_STRATEGY.md](ARCHITECTURE_STRATEGY.md)** — 7-skill pipeline design
- **[references/](references/)** — Detailed technical specs

## Common Tasks

### Run Pipeline on All Issues
1. Click **"Auto-Process All"** on dashboard
2. Monitor progress in logs
3. Issues flow through Steps 1-12 automatically

### Manually Refresh Salesforce Tokens
1. Get fresh access tokens:
   ```bash
   sf org auth show-access-token -o 10xhealth --no-prompt
   sf org auth show-access-token -o 10xhealth-sean --no-prompt
   ```
2. Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens`
3. Paste tokens (optional: add refresh tokens for auto-refresh)
4. Submit

### Set Up Claude Authentication
1. Navigate to `http://localhost:5350/setup/claude-login`
2. Step 1: Click link to log into Claude
3. Step 2: Run `cat ~/.claude/.credentials.json` on your local machine
4. Step 3: Paste the JSON output into the form
5. Submit — credentials saved and persisted

### Escalate an Issue
1. Click issue in sidebar
2. Click **"Settings"** (⚙ icon)
3. Change Jira status to **"Escalated to Engineering"**
4. Issue moves to engineering-escalations folder
5. Generate summary for handoff

## Troubleshooting

### "Salesforce tokens EXPIRED"
**Solution:** Refresh tokens via `/setup/refresh-salesforce-tokens` or provide refresh tokens for auto-refresh.

### "Claude credentials not found"
**Solution:** Run `/setup/claude-login` wizard to authenticate.

### Pipeline stalled on Step 5
**Check:** Are Salesforce orgs reachable? Run `/api/status` to verify auth.

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
