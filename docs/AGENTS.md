# CaseOps Skills Architecture

## Overview

CaseOps uses **Claude Code Skills** for AI orchestration. A single skill (`jira-salesforce-fix-pipeline`) orchestrates the entire 12-step pipeline, spawning sub-agents for specialized steps.

## Skill Structure

```
skills/jira-salesforce-fix-pipeline/
├── SKILL.md                    # Orchestrator instructions (canonical)
├── references/
│   ├── workflow.md             # Steps 1–12 (authoritative)
│   ├── sub-agent-prompts.md    # Prompts for Steps 3, 5, 6, 9, 10
│   ├── safety-policy.md        # Safety constraints
│   ├── quality-checklist.md    # Pre-completion gates
│   └── orchestration-loop-controller.md
└── assets/                     # Markdown templates
    ├── investigation-record-template.md
    ├── internal-notes-template.md
    ├── jira-message-template.md
    ├── engineering-handoff-template.md
    ├── issue-summary-template.md
    ├── test-report-template.md
    ├── closed-resolved-log-template.md
    └── step-4-problem-hypothesis-template.md

.claude/skills/jira-salesforce-fix-pipeline/
└── SKILL.md                    # Entrypoint (symlink to canonical skill)
```

## The Skill: jira-salesforce-fix-pipeline

### Invocation

**Via Claude Code GUI:**
```
/jira-salesforce-fix-pipeline

Process HEAL-12345 through the full pipeline.
```

**Via CaseOps GUI Button:**
```
Click "Run Pipeline For This Issue" on issue card
→ Backend invokes _stream_full_issue() 
→ Runs Claude Code CLI with skill
```

### Orchestrator Pattern

The skill is **not** a headless agent — it's a long-form Claude Code prompt with tool access. It:

1. Reads SKILL.md and references/ for instructions
2. Executes Steps 1–2 and 4, 7, 8, 11–12 directly (Bash, Salesforce CLI, file ops)
3. Spawns **sub-agents** for Steps 3, 5, 6, 9, 10 (via `Agent` tool)
4. Stitches outputs together
5. Makes routing decisions (escalate vs fix)
6. Emits progress lines to stdout (e.g., `STEP_3 HEAL-33753`)

### Step Breakdown

| Step | Type | Responsibility |
|------|------|---|
| 1 | Orchestrator | Sync from Jira (`python jira_sync.py`) |
| 2 | Orchestrator | Triage by status (Bash, CSV read) |
| 3 | **Sub-agent** | Analyze Jira issue (`jira-issue-analysis` skill) |
| 4 | Orchestrator | Synthesize root cause hypothesis |
| 5 | **Sub-agent** | Query Production metadata (`salesforce-production-metadata-investigation`) |
| 6 | **Sub-agent** | Drill down to exact artifact location (metadata drilling) |
| 7 | Orchestrator | Gate: escalate or support-fix? |
| 8 | Orchestrator | Implement fix in Sandbox (`sf` CLI, web UI, etc.) |
| 9 | **Sub-agent** | Deploy & test in Sandbox (`salesforce-sandbox-deploy-test`) |
| 10 | **Sub-agent** | Draft internal notes + Jira message (`jira-response-drafting`) |
| 11 | Orchestrator | Generate dated summary (rollup) |
| 12 | Orchestrator | Return action report to user |

### Sub-Agent Prompts

Located in `references/sub-agent-prompts.md`:

- **Step 3 Prompt** — Issue analysis; returns Issue Understanding section
- **Step 5 Prompt** — Metadata investigation (flows, fields, validation rules, etc.)
- **Step 6 Prompt** — Drilling mode: pinpoint exact artifact + failure point
- **Step 9 Prompt** — Deploy to `CASEOPS_SANDBOX_TARGET_ORG`, run tests, report
- **Step 10 Prompt** — Draft two separate files: internal notes + customer message

Each prompt is:
- **Fully self-contained** (includes issue key, paths, context, expected output format)
- **Deterministic** (same input → same output)
- **Isolated** (no reliance on orchestrator state)

### Loop Control & Iteration

**Standard Flow:**
```
Step 3 → Step 4 → Step 5 → Step 6 → Step 7
         ↓
      Escalate? ← Yes → Route to Engineering (Step 10 → 12)
                        |
                        No (Support-resolvable)
                        ↓
                      Step 8 → Step 9 (Deploy & Test)
                               ↓
                            Passed? → Step 10 → 11 → 12
                               ↓
                               No (Failed)
                               ↓
                            Revise hypothesis (Step 4)
                            Re-investigate (Step 5–6)
                            Re-implement (Step 8)
                            Re-test (Step 9)
```

**Retry Logic:**
- On Step 9 deploy failure: Revise Step 4 hypothesis → loop back to Steps 5–6
- On Step 9 test failure: Same retry loop
- Max 2–3 iterations before escalation

### Progress Output Format

Must emit to stdout (not just internal log):

```
STEP_1 __sync__
Reading jira-sync.py...
[Bash] python jira_sync.py --env-file .env.jira
...sync output...

STEP_2 __triage__
[Read] outputs/jira/manifest.csv
...triage output...

STEP_3 HEAL-33753
[Agent] Spawning jira-issue-analysis sub-agent...
...analysis returns...

STEP_4 HEAL-33753
Synthesized root cause: ...
...
```

GUI parses regex `/STEP_(\d+)\s+(HEAL-\d+)/` from SSE stream → updates indicator in real-time.

## Safety Gates

### Before Step 9 Deployment

**Must verify:**
- `CASEOPS_SANDBOX_TARGET_ORG` is set in `.env.jira`
- Org is reachable (`sf org list` includes it)
- No write to any other org
- No Production deployments

### Production Read-Only

**Allowed:**
- Query Production metadata (flows, validation rules, fields, etc.)
- Use `CASEOPS_PRODUCTION_READ_ORG` for org context
- Use `CASEOPS_PRODUCTION_MAGIC_LINK` for UI investigation

**Forbidden:**
- Any write to Production
- Modifying Production records or metadata
- Deploying to Production

### Artifact Linkification

All generated artifacts (investigation, notes, messages) include Salesforce links:
- Format: `sf://15or18-charRecordId`
- GUI converts to: `https://org/recordId` (direct access)
- Only raw IDs linkify; typed format (sf://field/Name) is not supported

## Sub-Agent Details

### jira-issue-analysis

**Input:** Jira issue key + full issue JSON

**Output:** ~300-token summary containing:
- Issue Understanding (what user is asking for, context, impact)
- Key details from comments, description, attachments

**Stored at:** `outputs/investigations/<KEY>.md` (Issue Understanding section)

### salesforce-production-metadata-investigation

**Input:** Issue Understanding + hypothesis from Step 4

**Output:** ~400-token summary containing:
- Relevant metadata found (flows, validation rules, fields, etc.)
- Gaps (what's missing or misconfigured)
- Potential root causes

**Stored at:** `outputs/investigations/<KEY>.md` (Root Cause section)

### salesforce-sandbox-deploy-test

**Input:** Implementation changes + Sandbox org

**Output:** ~300-token summary containing:
- Deploy success/failure
- Test results (did the fix work?)
- Gearset promotion readiness

**Stored at:** `outputs/test-reports/<KEY>.md`

### jira-response-drafting

**Input:** Full diagnosis + test results

**Output:** Two separate files:
- `outputs/internal-notes/<KEY>.md` — Root cause + decision (no customer-facing text)
- `outputs/jira-messages/<KEY>.md` — Customer-friendly response draft

## Orchestrator Best Practices

### Writing Step Prompts

1. **Make it self-contained** — Don't assume sub-agent knows prior steps
2. **Include acceptance criteria** — What success looks like
3. **Specify output format** — Markdown sections, tables, code blocks, etc.
4. **Provide examples** — Sample good vs bad outputs
5. **Set token budget** — Aim for ~300–500 token summaries (not full context)

### Handling Sub-Agent Outputs

1. **Read the artifact**, not the summary — Summary is compact; full details are in files
2. **Validate** — Check test-reports before marking success
3. **Don't nest** — Don't load full investigation into orchestrator; read outputs/ files only
4. **Summarize for next step** — Pass ~200 tokens to next sub-agent, not full context

### Error Handling

- **Sub-agent timeout** — Log and retry once; if timeout again, escalate
- **Sub-agent malformed output** — Ask sub-agent to reformat and resubmit
- **Deployment failure** — Trigger iteration loop (revise hypothesis → re-investigate → re-implement)
- **Unrecoverable error** — Escalate to Engineering with full diagnostic trail

## Templates (assets/)

All templates live in `assets/` and are loaded by steps:

- **investigation-record-template.md** — Scaffold for Step 3 (Issue Understanding section)
- **internal-notes-template.md** — Scaffold for Step 10 (internal diagnosis)
- **jira-message-template.md** — Scaffold for Step 10 (customer message)
- **engineering-handoff-template.md** — Used for Step 7 escalations
- **test-report-template.md** — Scaffold for Step 9 test results
- **issue-summary-template.md** — Used for Step 11 dated rollup
- **step-4-problem-hypothesis-template.md** — Worksheet for Step 4 hypothesis

## Disallowed Patterns

❌ **Don't:**
- Call deprecated Python agents (run_7_skills_for_issue, etc.)
- Hard-code org names; read from `.env.jira`
- Assume magic links are fresh; they expire
- Deploy to Production
- Load full investigation into orchestrator context
- Process multiple issues in a single Agent call

✅ **Do:**
- Spawn one sub-agent per step per issue
- Emit `STEP_N` progress lines to stdout
- Read artifact files, not summaries
- Validate test-reports before success claims
- Use structured templates for output files
- Batch similar operations (e.g., Steps 5–6 can drill together for same issue)

## Testing Skills Locally

**Test a single step:**
```bash
# Test sync (Step 1)
python jira_sync.py --env-file .env.jira

# Test triage (Step 2)
python run_pipeline.py --no-sync --dry-run

# Test sub-agent (Step 3)
# Copy Step 3 prompt from references/sub-agent-prompts.md
# Invoke via Claude Code: /agent [paste prompt]
```

**Test full pipeline:**
```bash
# Via GUI
http://localhost:5000
Click "Run Pipeline For This Issue"

# Via CLI
/jira-salesforce-fix-pipeline
Process HEAL-33753 through the pipeline.
```

## Monitoring & Logs

**Pipeline logs:**
- Real-time: `http://localhost:5000` → log pane
- Persistent: `outputs/pipeline-logs/<RUN_ID>.jsonl` (streaming events)

**Check sub-agent execution:**
```bash
tail -f outputs/pipeline-logs/HEAL-33753.jsonl | jq '.text'
# Shows all log lines for issue
```

**Trace sub-agent activity:**
- Look for `[Agent]` lines in log
- Sub-agent output starts with `[Skill]` tag
- Summaries captured after each sub-agent completes

## Future: Multi-Issue Parallelization

Currently: Process issues **sequentially** (Steps 3–11 for each)

Planned: **Batch processing**
- Spawn Steps 3, 5, 6 sub-agents for multiple issues in parallel
- Merge results before proceeding to Step 7+
- Should reduce 12-issue full run from ~60 min to ~20 min

Architectural change will be transparent to SKILL.md (no prompt changes needed).
