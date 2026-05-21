# CaseOps — Jira-to-Salesforce Support Automation

**CaseOps** is an AI-powered support case automation system that triages Jira issues, diagnoses Salesforce problems, implements fixes in Sandbox, and drafts customer responses.

## What It Does

1. **Syncs Jira** → Pulls assigned support issues
2. **Triages automatically** → Sorts by status (Closed, Escalated, Active)
3. **Diagnoses Salesforce** → Analyzes Production metadata and logs
4. **Implements fixes** → Modifies Sandbox metadata only
5. **Validates in Sandbox** → Deploys and tests changes
6. **Drafts responses** → Writes internal notes + customer-facing replies
7. **Escalates to Engineering** → Routes complex issues with full handoffs

All orchestrated by Claude Code via the `jira-salesforce-fix-pipeline` skill. No manual agent management required.

## Quick Start

### 1. Setup

```bash
# Copy and configure credentials
cp .env.jira.example .env.jira
# Edit: Jira credentials, org identifiers, magic links (optional)
```

### 2. Start the GUI

```bash
python app.py
# Opens: http://localhost:5000
```

### 3. Process Issues

**Option A: GUI Button (Recommended)**
1. Open http://localhost:5000
2. Click **"Run Pipeline For This Issue"** on any active issue
3. Watch real-time progress logs

**Option B: Claude Code CLI**
```
/jira-salesforce-fix-pipeline

Process HEAL-12345 through the full pipeline.
```

## Architecture

```
┌─────────────────────────────────────────────┐
│  Flask GUI (app.py)                         │
│  - Issue dashboard & detail views           │
│  - Investigation/notes/message editors      │
│  - Real-time pipeline progress tracking     │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│  Python Setup (run_pipeline.py)             │
│  - Sync Jira                                │
│  - Triage by status                         │
│  - Archive Closed/Escalated                 │
│  - Scaffold investigation records           │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│  Claude Skill: jira-salesforce-fix-pipeline │
│  (Steps 1–12 orchestration)                 │
│  - Spawns sub-agents for Steps 3,5,6,9,10  │
│  - Implements fixes in Sandbox (Step 8)     │
│  - Routes escalations to Engineering       │
└─────────────────────────────────────────────┘
```

## Configuration (.env.jira)

```env
# Jira
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=jira-api-token-here
CASEOPS_DEFAULT_ASSIGNEE=your-jira-username

# Salesforce
CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean      # Single writable Sandbox
CASEOPS_PRODUCTION_READ_ORG=10xhealth           # Production (read-only)

# Optional: Session URLs for UI investigation (auto-expire)
CASEOPS_SANDBOX_MAGIC_LINK=https://...
CASEOPS_PRODUCTION_MAGIC_LINK=https://...

# LLM Auth (choose one)
CASEOPS_LLM_AUTH=claude_code   # Use Claude Code CLI
# OR
CASEOPS_LLM_AUTH=api_key       # Use Anthropic API
ANTHROPIC_API_KEY=sk-...
```

## GUI Actions

| Action | What Happens |
|--------|--------------|
| **Fetch from Jira** | Full sync (Steps 1–2 setup only) |
| **Prepare Issues** | Sync + triage + scaffold (no AI) |
| **Run Pipeline For This Issue** | Full workflow Steps 1–12 (AI-powered) |
| **Sync This Issue** | Update single issue from Jira |
| **Auto-Process All** | Full pipeline on all active issues |

## Outputs

After processing, check:

| File | Contents |
|------|----------|
| `outputs/investigations/<KEY>.md` | Diagnosis record (issue understanding + metadata findings) |
| `outputs/internal-notes/<KEY>.md` | Root cause analysis + escalation decision |
| `outputs/jira-messages/<KEY>.md` | Customer-facing response draft (post to Jira manually) |
| `outputs/test-reports/<KEY>.md` | Sandbox validation results |
| `outputs/engineering-escalations/<KEY>.md` | Engineering handoff (if escalated) |
| `outputs/issue-summary-YYYY-MM-DD.md` | Daily rollup of all processed issues |

## Safety Constraints

✅ **Allowed:**
- Read Production metadata (diagnosis only)
- Write/deploy to `CASEOPS_SANDBOX_TARGET_ORG` only
- Test in Sandbox before promotion

❌ **Forbidden:**
- Direct Production writes
- Deploying to other Sandboxes
- Automatic Jira posting (you review & post manually)
- Automatic Production promotion (you use Gearset)

## Troubleshooting

**"Sync failed"**
- Check `.env.jira` Jira credentials
- Verify network access to `JIRA_BASE_URL`

**"Pipeline stalled"**
- Check `CASEOPS_SANDBOX_TARGET_ORG` is set and reachable
- Run: `sf org list` to verify Sandbox authentication

**"Links in investigation are broken"**
- Only raw Salesforce record IDs (15-18 char alphanumeric) are linkified
- API names require actual IDs from metadata queries

## Documentation

- **[CASEOPS_QUICKSTART.md](CASEOPS_QUICKSTART.md)** — User guide (setup, usage, workflow)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — System design & data flow
- **[API.md](API.md)** — Flask endpoints & webhook reference
- **[AGENTS.md](AGENTS.md)** — Skill & sub-agent architecture
- **[WORKSPACES.md](WORKSPACES.md)** — Multi-org setup
- **[NIGHTLY_SETUP.md](NIGHTLY_SETUP.md)** — Scheduled pipeline
- **[CLAUDE_LAUNCHER_GUIDE.md](CLAUDE_LAUNCHER_GUIDE.md)** — Claude Code CLI setup

## Recent Changes

- Fixed sync cache clearing for individual issue syncs
- Added real-time step progress indicators in GUI
- Improved artifact linkification (ID-based, no magic links)
- Added `/api/orgs` endpoint for org identifier access

## License

[Include your license here]
