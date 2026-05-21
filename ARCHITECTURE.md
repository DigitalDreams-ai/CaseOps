# CaseOps Architecture

## System Overview

CaseOps is a three-tier system:

1. **Frontend Tier** — Flask GUI (app.py, templates/, static/)
2. **Python Setup Tier** — Deterministic scaffolding (run_pipeline.py, jira_sync.py)
3. **AI Orchestration Tier** — Claude Code skill (skills/jira-salesforce-fix-pipeline/)

## Data Flow

```
Jira API
   ↓
jira_sync.py → outputs/jira/
   ├── raw/<KEY>.json
   ├── summary/<KEY>.md
   └── manifest.csv
   ↓
run_pipeline.py → Triage → Scaffold
   ├── outputs/investigations/<KEY>.md (template)
   ├── outputs/closed-resolved/<KEY>.md
   ├── outputs/engineering-escalations/<KEY>.md
   └── outputs/issue-summary-YYYY-MM-DD.md
   ↓
Flask GUI (app.py)
   ├── /api/issues → manifest.csv
   ├── /api/issue/<key> → investigations/<KEY>.md
   ├── /api/file/<key>/<type> → various outputs
   └── /api/run → invoke pipeline
   ↓
Claude Code Skill (Steps 3,5,6,9,10)
   ├── Sub-agent: jira-issue-analysis
   ├── Sub-agent: salesforce-production-metadata-investigation
   ├── Sub-agent: salesforce-sandbox-deploy-test
   └── Sub-agent: jira-response-drafting
   ↓
Outputs (final)
   ├── investigations/<KEY>.md (complete diagnosis)
   ├── internal-notes/<KEY>.md (root cause + decision)
   ├── jira-messages/<KEY>.md (customer response draft)
   ├── test-reports/<KEY>.md (Sandbox validation)
   └── engineering-escalations/<KEY>.md (if escalated)
```

## Component Details

### Flask GUI (app.py)

**Responsibilities:**
- Serve HTML dashboard at http://localhost:5000
- Expose REST API for issue data, file access, and pipeline operations
- Stream real-time pipeline logs via Server-Sent Events (SSE)
- Cache Jira summaries & investigation records
- Handle Jira comment posting & issue transitions

**Key Routes:**
- `GET /` — Dashboard
- `GET /api/issues` — List all issues (from manifest.csv)
- `GET /api/issue/<key>` — Issue detail
- `GET /api/file/<key>/<type>` — File content (investigation, notes, message, etc.)
- `POST /api/run` — Start pipeline action (sync, triage, full, full_issue, etc.)
- `GET /api/stream` — SSE stream for real-time log updates
- `GET /api/orgs` — Org identifiers from .env.jira
- `POST /api/issue/<key>/send-canned-message` — Post canned comment to Jira

**Caching:**
- `jira_summary_cache` — Caches rendered investigation/notes/messages
- Cleared after sync/triage/full operations (global) or individual issue syncs
- Prevents stale data in UI after Jira/Salesforce changes

### Python Setup Pipeline (run_pipeline.py)

**Execution Flow:**

1. **Sync** (conditional, `--no-sync` skips)
   - Calls `jira_sync.py` to fetch from Jira
   - Outputs: raw/<KEY>.json, summary/<KEY>.md, manifest.csv

2. **Triage**
   - Reads manifest.csv
   - Classifies issues:
     - Closed/Resolved/Canceled → `outputs/closed-resolved/`
     - Escalated to Engineering → `outputs/engineering-escalations/`
     - Others → Active (proceed to next steps)

3. **Archive Closed**
   - Creates summary file for closed issues
   - Prevents reprocessing

4. **Archive Escalated**
   - Pre-escalated issues route to Engineering without processing

5. **Scaffold Investigations**
   - Creates empty `outputs/investigations/<KEY>.md` templates
   - AI agents fill these during Steps 3–10

6. **Dated Summary**
   - Generates `outputs/issue-summary-YYYY-MM-DD.md`
   - Tracks total, closed, escalated, active counts

7. **Handoff to Claude Code Skill**
   - Prints handoff message for AI processing
   - (Or skipped with `--no-agents`, requires manual skill invocation)

**Command Examples:**
```bash
# Full setup + handoff to AI
python run_pipeline.py

# Sync only one issue, merge into manifest
python run_pipeline.py --issue HEAL-12345

# Triage from existing manifest (no sync)
python run_pipeline.py --no-sync

# Dry run (show counts, write nothing)
python run_pipeline.py --dry-run
```

### Jira Sync (jira_sync.py)

**Responsibilities:**
- Query Jira API for assigned issues
- Serialize to JSON (raw details preserved)
- Create markdown summaries (human-readable)
- Update/merge manifest.csv
- Support incremental sync (`--incremental` flag)

**Outputs:**
- `outputs/jira/raw/<KEY>.json` — Full issue JSON from Jira
- `outputs/jira/summary/<KEY>.md` — Stripped-down markdown (title, status, summary, comments)
- `outputs/jira/manifest.csv` — Index of all keys, statuses, summaries

### Claude Code Skill (jira-salesforce-fix-pipeline)

**Orchestrator Architecture:**

The skill runs Steps 1–12 sequentially:

| Step | Type | Action |
|------|------|--------|
| 1 | Orchestrator | `python jira_sync.py` (in skill context) |
| 2 | Orchestrator | Read manifest, classify issues |
| 3 | Sub-agent | Analyze Jira issue (`jira-issue-analysis`) |
| 4 | Orchestrator | Synthesize hypothesis from Step 3 output |
| 5 | Sub-agent | Query Production metadata (`salesforce-production-metadata-investigation`) |
| 6 | Sub-agent | Identify exact problem location (metadata drilling) |
| 7 | Orchestrator | Decide: Support-resolvable or escalate? |
| 8 | Orchestrator | Implement fix in Sandbox (web UI, CLI, declarative) |
| 9 | Sub-agent | Deploy & test in Sandbox (`salesforce-sandbox-deploy-test`) |
| 10 | Sub-agent | Draft internal notes + Jira message (`jira-response-drafting`) |
| 11 | Orchestrator | Generate dated summary (rollup of all processed issues) |
| 12 | Orchestrator | Return action report to user |

**Sub-agents:**
- Each spawned via `Agent` tool
- Clean context window (no spillover from prior steps)
- Return compact summaries (~300–500 tokens)
- Write outputs to `outputs/` (orchestrator reads artifacts, not context)

**Progress Tracking:**
- Emits `STEP_N <ISSUE_KEY>` to stdout (e.g., `STEP_3 HEAL-33753`)
- GUI parses via SSE stream regex: `/STEP_(\d+)\s+(HEAL-\d+)/`
- Updates step indicator on issue card in real-time

**Safety Gates:**
- Before Step 9: Confirms `CASEOPS_SANDBOX_TARGET_ORG` is set
- Before any write: Validates target org matches allowlist
- Production read-only: All queries use `CASEOPS_PRODUCTION_READ_ORG`
- No Production deploys, ever

## File Organization

```
CaseOps/
├── app.py                          # Flask GUI & API
├── run_pipeline.py                 # Python setup (Steps 1–2, 4, 7, 8, 11–12 prep)
├── jira_sync.py                    # Jira API client
├── caseops_paths.py                # Constants (repo paths, defaults)
│
├── templates/                      # HTML/Jinja2
│   └── index.html                  # Main SPA dashboard
│
├── static/
│   ├── css/
│   │   └── caseops.css             # Styling (dark theme)
│   ├── favicon.svg
│   └── logo.svg
│
├── skills/jira-salesforce-fix-pipeline/
│   ├── SKILL.md                    # Orchestrator instructions (canonical)
│   ├── references/
│   │   ├── workflow.md             # Steps 1–12 (authoritative)
│   │   ├── sub-agent-prompts.md    # Copy-paste prompts for Steps 3,5,6,9,10
│   │   ├── safety-policy.md        # Safety constraints & rules
│   │   ├── quality-checklist.md    # Pre-completion gates
│   │   └── orchestration-loop-controller.md
│   └── assets/                     # Templates (markdown)
│       ├── investigation-record-template.md
│       ├── internal-notes-template.md
│       ├── jira-message-template.md
│       ├── engineering-handoff-template.md
│       └── ...
│
├── .claude/skills/jira-salesforce-fix-pipeline/
│   └── SKILL.md                    # Symlink to canonical skill
│
├── outputs/                        # Generated artifacts (gitignored)
│   ├── jira/
│   │   ├── raw/<KEY>.json
│   │   ├── summary/<KEY>.md
│   │   └── manifest.csv
│   ├── investigations/<KEY>.md
│   ├── internal-notes/<KEY>.md
│   ├── jira-messages/<KEY>.md
│   ├── test-reports/<KEY>.md
│   ├── engineering-escalations/<KEY>.md
│   ├── closed-resolved/<KEY>.md
│   ├── issue-summary-YYYY-MM-DD.md
│   ├── pipeline-logs/<RUN_ID>.jsonl (streaming progress)
│   └── ...
│
├── deprecated/                     # Removed agents (archived for reference)
│   ├── agent_*.py
│   └── ...
│
├── .env.jira                       # Configuration (gitignored)
├── .env.jira.example               # Template
└── .gitignore
```

## Execution Models

### Model 1: GUI Button (Recommended)

```
User clicks "Run Pipeline For This Issue"
  ↓
app.py /api/run → action="full_issue", key="HEAL-12345"
  ↓
_stream_full_issue(key, run_key)
  ↓
_build_claude_prompt(key, instruction) → context-rich prompt
  ↓
_do_stream_claude() → Claude Code CLI
  ↓
claude -p "prompt..." --output-format stream-json
  ↓
Parses stream-json events
  ↓
Emits STEP_N lines via _log_emit_line() → SSE queue
  ↓
Browser receives SSE stream → regex matches STEP_N → updateStepIndicator()
  ↓
GUI updates step badge in real-time
```

### Model 2: CLI Direct

```
User: /jira-salesforce-fix-pipeline (in Claude Code IDE)
  ↓
Claude reads SKILL.md (canonical)
  ↓
Executes Steps 1–12 orchestration
  ↓
Emits logs to stdout
  ↓
(No GUI; user sees raw Claude output)
```

## State Management

**Issue States:**
- `Closed` / `Resolved` / `Canceled` → Archived, not reprocessed
- `Escalated to Engineering` → Archived with handoff, not reprocessed
- Active (all others) → Processed through Steps 3–12

**Pipeline State:**
- `_active_keys` (in-memory set) → Prevents concurrent runs on same issue
- `pipelineProgress` (JS) → Tracks step per issue for UI indicator
- `jira_summary_cache` (Python) → Caches rendered artifacts (cleared post-sync)

## Error Handling

**Sync Failures:**
- Credential errors → Stop, ask user to verify `.env.jira`
- Network errors → Stop, ask user to check connectivity
- Retry not automatic; user must run again

**Pipeline Failures:**
- Sub-agent timeouts → Logged, can retry specific step
- Implementation errors → Recorded in test-report, escalation decision made
- Sandbox deploy failures → Iteration loop (revise hypothesis → Step 5–6 → Step 8–9)

**Safety Violations:**
- Production write detected → Stop immediately, exit with error
- Wrong org target → Stop, validate `CASEOPS_SANDBOX_TARGET_ORG`

## Performance Considerations

- **Sync:** ~2–5 sec for 20 issues (depends on Jira API rate limits)
- **Triage:** ~100ms
- **Full Pipeline per issue:** ~5–15 min (depends on Salesforce metadata size, sub-agent latency)
- **Cache:** Reduces latency for repeated issue views by ~90% (avoids re-rendering)
- **Parallel:** Not yet implemented; processes issues sequentially

## Future Roadmap

- Parallel sub-agent execution (batch 3+ issues together)
- Webhook integration (Jira → auto-trigger CaseOps)
- Metric dashboards (resolution time, escalation rate, etc.)
- Custom rules engine for routing & escalation logic
