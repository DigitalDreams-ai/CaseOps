# CaseOps Quick Start

**CaseOps** is a Jira-to-Salesforce support case automation system. It triages issues, diagnoses Salesforce problems, implements fixes in Sandbox, and drafts responses — all driven by Claude Code skills.

## 1. Setup

### Prerequisites
- Python 3.9+
- `sf` CLI (Salesforce)
- Claude Code subscription or `claude login`
- `.env.jira` file (copy from `.env.jira.example` and fill in Jira credentials + Salesforce orgs)

### Configure .env.jira

```bash
cp .env.jira.example .env.jira
```

**Required keys:**
```env
JIRA_BASE_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token
CASEOPS_DEFAULT_ASSIGNEE=your-username
CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean  # Single writable Sandbox
CASEOPS_PRODUCTION_READ_ORG=10xhealth      # Production (read-only)
CASEOPS_SANDBOX_MAGIC_LINK=https://...     # Optional: Sandbox session URL
CASEOPS_PRODUCTION_MAGIC_LINK=https://...  # Optional: Production session URL (read-only)
```

## 2. Start the GUI

```bash
python app.py
```

Open browser: `http://localhost:5000`

GUI features:
- **Sync** → Pull latest issues from Jira
- **Full Triage** → Sync + scaffold investigations (no AI processing)
- **Run Pipeline For This Issue** → Full AI workflow (Steps 1–12)
- View/edit investigations, internal notes, Jira messages
- Send comments to Jira
- Track deployment status

## 3. Process an Issue (Full Workflow)

### Path A: GUI Button (Recommended)

1. Go to the issue page
2. Click **"Run Pipeline For This Issue"**
3. Watch live logs as Claude processes through:
   - Step 3: Analyze issue
   - Step 5: Retrieve Production metadata
   - Step 6: Identify problem location
   - Step 7: Escalation decision
   - Step 8–9: Implement + Deploy to Sandbox (if Support-resolvable)
   - Step 10: Draft internal notes + Jira message
   - Step 11–12: Generate summary + report

### Path B: Claude Code CLI (Direct)

In Claude Code IDE at the repo root:

```
/jira-salesforce-fix-pipeline

Process HEAL-12345 through the full pipeline.
```

Claude will:
1. Read `CASEOPS_SANDBOX_TARGET_ORG` from `.env.jira`
2. Spawn sub-agents for analysis, metadata retrieval, deploy/test
3. Write outputs to `outputs/`:
   - `investigations/<KEY>.md` — diagnosis record
   - `internal-notes/<KEY>.md` — root cause + escalation decision
   - `jira-messages/<KEY>.md` — customer-facing response
   - `test-reports/<KEY>.md` — Sandbox validation results
   - `engineering-escalations/<KEY>.md` — Engineering handoff (if escalated)

## 4. Review Results

After processing, review in GUI or files:

| File | Purpose | Location |
|------|---------|----------|
| Investigation | Problem analysis, Salesforce diagnosis | `outputs/investigations/<KEY>.md` |
| Internal Notes | Root cause, escalation decision, implementation notes | `outputs/internal-notes/<KEY>.md` |
| Jira Message | Customer-facing response draft | `outputs/jira-messages/<KEY>.md` |
| Test Report | Sandbox deployment + validation results | `outputs/test-reports/<KEY>.md` |
| Eng Handoff | Engineering escalation summary | `outputs/engineering-escalations/<KEY>.md` |
| Dated Summary | Daily issue rollup | `outputs/issue-summary-YYYY-MM-DD.md` |

## 5. Post to Jira (Manual Step)

CaseOps **does not** auto-post to Jira. You review then post:

1. Open `outputs/jira-messages/<KEY>.md`
2. Copy the message
3. Post to Jira issue as a comment
4. In GUI: Mark issue as "Resolved" or use Jira transition if applicable

## 6. Deploy to Production (Manual Step)

**CaseOps validates only in Sandbox.** Production deploy is operator-driven:

- **If Support-fixed issue:** Use Gearset to promote Sandbox changes to Production
- **If Engineering-escalated:** Coordinate with Engineering team (handoff in `outputs/engineering-escalations/`)
- **Read-only fix (data/config/access only):** No Production deploy needed; issue resolved in Sandbox

Always confirm in the **Test Report** whether Production deploy is required ("Gearset: Yes / No / N/A").

## 7. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Flask GUI (app.py)                                         │
│  - Dashboard, issue list, investigation viewer              │
│  - "Run Pipeline For This Issue" button                     │
│  - Jira comment UI, transitions                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Claude Code Skill: jira-salesforce-fix-pipeline            │
│  (orchestrator — Steps 1–2, 4, 7–8, 11–12)                 │
└─────────────────────────────────────────────────────────────┘
         ↓              ↓              ↓              ↓
    Step 3          Step 5–6         Step 9        Step 10
    Sub-agent       Sub-agent        Sub-agent     Sub-agent
    jira-issue-    salesforce-prod   sandbox-      jira-response-
    analysis       metadata-invest   deploy-test   drafting
```

**Why sub-agents?**
- Each sub-agent gets a clean context window (no token spillover from previous steps)
- Orchestrator keeps only compact summaries (~300 tokens each)
- Enables parallel processing if needed in future

## 8. Safety Constraints

**Production is read-only. Period.**
- ✗ Never deploy to Production from CaseOps
- ✗ Never modify Production metadata or records
- ✓ Read Production metadata to diagnose issues
- ✓ Use `CASEOPS_PRODUCTION_MAGIC_LINK` for UI investigation (read-only)

**Sandbox writes are allowlisted:**
- ✓ Deploy, test, modify metadata **ONLY** in `CASEOPS_SANDBOX_TARGET_ORG`
- ✓ That org is read from `.env.jira` at deploy time
- ✗ Deploying to any other org will be blocked
- If `.env.jira` is missing `CASEOPS_SANDBOX_TARGET_ORG`, processing stops with an error

## 9. Troubleshooting

### "Sync failed"
- Check `.env.jira` has valid Jira credentials
- Verify Jira is reachable from your network
- Try: `python jira_sync.py --env-file .env.jira`

### "Pipeline failed at Step 8"
- Check `CASEOPS_SANDBOX_TARGET_ORG` is set and reachable
- Run: `sf org list` to confirm Sandbox org is registered
- Check if magic links expired (refresh in `.env.jira`)

### "Sub-agent timed out"
- Check available context tokens (very large issues may exceed limits)
- Split into smaller investigation if needed
- Retry the step manually via CLI

### Investigation files are empty
- Full workflow not run yet; click "Run Pipeline For This Issue" button
- Or invoke `/jira-salesforce-fix-pipeline` skill in Claude Code

## 10. Files & Structure

```
CaseOps/
├── app.py                          # Flask GUI server
├── run_pipeline.py                 # Triage + scaffold (no agents)
├── jira_sync.py                    # Jira API sync
├── .env.jira                       # Configuration (gitignored)
├── skills/                         # Claude Code skills (canonical)
│   └── jira-salesforce-fix-pipeline/
│       ├── SKILL.md               # Orchestrator instructions
│       ├── references/
│       │   ├── workflow.md        # Steps 1–12 (authoritative)
│       │   ├── sub-agent-prompts.md
│       │   ├── safety-policy.md
│       │   └── quality-checklist.md
│       └── assets/                # Templates
├── .claude/skills/                 # Claude Code entrypoint (symlink)
│   └── jira-salesforce-fix-pipeline/
│       └── SKILL.md               # Points to canonical skills/
├── outputs/                        # Generated artifacts (gitignored)
│   ├── jira/                      # Raw Jira data + summaries
│   ├── investigations/            # Diagnosis records
│   ├── internal-notes/            # Internal memos
│   ├── jira-messages/             # Customer-facing drafts
│   ├── test-reports/              # Sandbox validation
│   ├── engineering-escalations/   # Engineering handoffs
│   ├── closed-resolved/           # Archived closed issues
│   └── pipeline-logs/             # Execution logs (JSONL)
└── deprecated/                     # Old Python agents (removed)
    └── *.py
```

## 11. Key Decisions

**Skill-based orchestration, not agent orchestration:**
- Skills = long-form Claude Code with tool access (browser, Bash, MCP)
- Sub-agents = clean context, compact summaries, parallel-ready
- Orchestrator (the Skill itself) = stitches outputs, makes routing decisions

**Sandbox-only deployment:**
- All fixes validated in single allowlisted Sandbox before considering Production
- No automatic Production promotion
- Operator owns final Production deploy via Gearset or manual

**Production read-only:**
- CaseOps can query, view, diagnose
- Cannot create, update, delete, or deploy anything in Production
- Separation of concerns: CaseOps for diagnosis, Gearset for promotion

---

**For more:** See `skills/jira-salesforce-fix-pipeline/references/workflow.md` (authoritative steps), `AGENTS.md` (architecture), and `safety-policy.md` (constraints).
