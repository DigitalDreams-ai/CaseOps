# CaseOps Jira-Salesforce Fix Pipeline — Test Plan

**Date:** 2026-05-20  
**Objective:** Validate Steps 1–6 implementation for end-to-end orchestration readiness

---

## Test Scope

**In Scope (Steps 1–6):**
- Step 1: Jira sync via Python + `.env.jira`
- Step 2: Triage routing (Closed/Resolved, Escalated to Engineering, Active)
- Step 3: Sub-agent spawning (jira-issue-analysis)
- Step 4: Hypothesis synthesis and file creation
- Step 5: Sub-agent spawning (salesforce-production-metadata-investigation)
- Step 6: Sub-agent spawning (salesforce-production-metadata-investigation drilling mode)

**Out of Scope (Steps 7–12):**
- Full orchestration loop (requires sub-agents)
- Sandbox deploy/test iteration (Step 9 loop-back)
- File separation validation (Step 10)
- Summary generation (Step 11)

---

## Test Plan

### Test 1: Step 1 — Jira Sync

**Objective:** Verify jira_sync.py runs from Bash and populates outputs/jira/

**Preconditions:**
- `.env.jira` is configured with valid Jira credentials
- Network connectivity to Jira is available
- repo root contains `jira_sync.py`

**Test Case:**
```bash
cd /path/to/CaseOps
python jira_sync.py --env-file .env.jira
```

**Expected Results:**
- Exit code: 0
- Files created:
  - `outputs/jira/raw/HEAL-*.json` (at least 1 file)
  - `outputs/jira/summary/HEAL-*.md` (at least 1 file)
  - `outputs/jira/manifest.csv` (with headers: Key, Status, Summary, Updated)
- manifest.csv contains at least 3 rows (including header)

**Validation:**
- `ls outputs/jira/raw/ | wc -l` >= 2
- `ls outputs/jira/summary/ | wc -l` >= 2
- `head -1 outputs/jira/manifest.csv` contains "Key,Status,Summary,Updated"

---

### Test 2: Step 2 — Triage Routing

**Objective:** Verify run_pipeline.py reads manifest and routes issues correctly

**Preconditions:**
- Step 1 has completed (manifest.csv exists)
- At least one issue in each status category (Closed, Escalated, In Progress, etc.)

**Test Case:**
```bash
cd /path/to/CaseOps
python run_pipeline.py --no-agents --triage-only --no-sync
```

**Expected Results:**
- Exit code: 0
- Directories created:
  - `outputs/closed-resolved/` (with HEAL-*.md files for Closed/Resolved issues)
  - `outputs/engineering-escalations/` (with HEAL-*.md files for pre-escalated issues)
  - `outputs/investigations/` (with HEAL-*.md files for active issues)
- Count of active issues identified in stdout

**Validation:**
- `ls outputs/closed-resolved/ 2>/dev/null | wc -l` > 0 (if any Closed/Resolved exist)
- `ls outputs/investigations/ 2>/dev/null | wc -l` > 0 (at least 1 active issue)
- Log shows: "Issues routed to processing: N"

---

### Test 3: SKILL.md Documentation

**Objective:** Verify SKILL.md accurately documents Steps 1–6 integration

**Test Case:**
1. Read `SKILL.md` in full
2. Verify sections exist:
   - "Operator Setup"
   - "How to Run This Pipeline (Full Steps 1–12 Orchestration)"
   - "Step 1 — Sync from Jira (Orchestrator)"
   - "Step 2 — Triage and Route (Orchestrator)"
   - "Steps 3–6" (workflow documented)
   - "Safety Constraints" (Step 8–9 Sandbox checks)

**Expected Results:**
- All sections present and coherent
- No contradictions with workflow.md
- Safety constraints explicitly list `CASEOPS_SANDBOX_TARGET_ORG` check
- Sub-agent prompts referenced correctly

**Validation:**
- grep "Step 1 — Sync from Jira" SKILL.md
- grep "CASEOPS_SANDBOX_TARGET_ORG" SKILL.md
- grep "orchestration-loop-controller.md" SKILL.md (optional but recommended)

---

### Test 4: Loop Controller Documentation

**Objective:** Verify orchestration-loop-controller.md provides complete pseudocode

**Test Case:**
1. Read `references/orchestration-loop-controller.md` in full
2. Verify sections:
   - "Loop Overview"
   - "Progress Tracking" (log file format)
   - "Loop Control Logic (Pseudocode)" (complete pseudocode with Steps 3–11)
   - "Escalation Gate Decision (Step 7)" (decision tree)
   - "Loop-Back Conditions" (Step 5/6 metadata loop, Step 8/9 hypothesis loop)
   - "Blocker Handling" (hard stops)
   - "Summary Generation (Step 11)"
   - "User Report (Step 12)"

**Expected Results:**
- Pseudocode is complete and executable (could be translated to Python/JavaScript)
- All loop-back scenarios documented
- Progress tracking format clear

**Validation:**
- Pseudocode includes FOR EACH loop
- Pseudocode includes WHILE loops (metadata discovery, deploy/test)
- Cap iterations documented (max 3 per loop)

---

### Test 5: Sub-Agent Prompt Templates

**Objective:** Verify Step 3, 5, 6, 9, 10 prompts are complete and self-contained

**Test Case:**
1. Read `references/sub-agent-prompts.md`
2. For each step (3, 5, 6, 9, 10), verify:
   - Prompt is fully self-contained (no missing context)
   - Input placeholders documented (`<KEY>`, `<hypothesis>`, etc.)
   - Output path documented (where sub-agent writes)
   - Return format specified (summary tokens, what to include)

**Expected Results:**
- Each step has dedicated prompt block
- All <placeholder> variables explained
- Output file paths clear
- Return format fits within 300–400 tokens

**Validation:**
- grep "## Step 3" sub-agent-prompts.md
- grep "outputs/investigations" sub-agent-prompts.md (appears 5+ times)
- grep "Return a compact summary" sub-agent-prompts.md (appears 5+ times)

---

### Test 6: Step 10 File Separation

**Objective:** Verify Step 10 prompt enforces file separation with validation checkpoints

**Test Case:**
1. Read `references/sub-agent-prompts.md` Step 10 section
2. Count validation checkpoints:
   - Checkpoint A: Draft Document 1 validation
   - Checkpoint B: Document 1 save verification
   - Checkpoint C: Draft Document 2 validation
   - Checkpoint D: Document 2 save verification
   - Checkpoint (Final): Orchestrator-level validation

**Expected Results:**
- Minimum 5 checkpoints present
- Forbidden keywords listed (e.g., "[INTERNAL]", "Hi [", "Thanks for")
- Validation is prescriptive (tells sub-agent to DELETE, not just "don't write")

**Validation:**
- grep "CHECKPOINT" sub-agent-prompts.md | wc -l >= 4
- grep "[INTERNAL]" sub-agent-prompts.md
- grep "DELETE if found" sub-agent-prompts.md | wc -l >= 5

---

### Test 7: Safety Policy

**Objective:** Verify SKILL.md documents Sandbox safety checks

**Test Case:**
1. Read SKILL.md "Safety Constraints" section
2. Verify:
   - Before Step 8: Read CASEOPS_SANDBOX_TARGET_ORG from .env.jira
   - Before Step 9: Verify Sandbox org is reachable
   - Step 9 sub-agent: Confirm CLI target matches before any deploy
   - All writes logged with timestamp

**Expected Results:**
- All checks documented as mandatory
- Blocker exits clear ("STOP if...")
- Audit trail format specified

**Validation:**
- grep "Before Step 8" SKILL.md
- grep "CASEOPS_SANDBOX_TARGET_ORG" SKILL.md | wc -l >= 3
- grep "STOP and report" SKILL.md

---

### Test 8: End-to-End Coherence Check

**Objective:** Verify Steps 1–6 form a coherent pipeline

**Test Case:**

1. **Step 1 → Step 2 handoff**
   - Step 1 outputs: `outputs/jira/manifest.csv`
   - Step 2 inputs: manifest.csv
   - Verification: manifest.csv format matches expected (Key, Status, Summary, Updated)

2. **Step 2 → Step 3 handoff**
   - Step 2 routes active issues
   - Step 3 receives issue key
   - Verification: Step 3 prompt has `<KEY>` placeholder

3. **Step 3 → Step 4 handoff**
   - Step 3 writes to: `outputs/investigations/<KEY>.md`
   - Step 4 reads from: Issue Understanding section
   - Verification: Step 4 hypothesis file path is `outputs/step-4-hypothesis/<KEY>.md`

4. **Step 4 → Step 5 handoff**
   - Step 4 outputs: hypothesis in `outputs/step-4-hypothesis/<KEY>.md`
   - Step 5 input: paste hypothesis from Step 4 file
   - Verification: Step 5 prompt accepts `<paste from outputs/step-4-hypothesis/<KEY>.md>`

5. **Step 5 → Step 6 handoff**
   - Step 5 appends to: `outputs/investigations/<KEY>.md`
   - Step 6 input: "Production metadata: <paste the Summary from Step 5>"
   - Verification: Step 6 can accept Step 5 summary as input

**Expected Results:**
- All handoffs are clean (output of one step = input of next)
- No missing intermediate files
- Paths are consistent

**Validation:**
- Create a trace map: Step 1 output → Step 2 input → Step 3 input → ... → Step 6 output
- Verify no gaps or missing files

---

## Browser Demo Validation (Future)

Once Steps 7–12 are implemented, the following browser demo should work:

**Setup:**
1. Open Claude Code with this repo
2. Run: `/jira-salesforce-fix-pipeline` (or skill invocation)
3. Observe:
   - Step 1 runs (Jira sync)
   - Step 2 runs (triage)
   - Step 3–6 spawned for first active issue
   - Progress logged in real-time
   - Step 10 creates two separate files
   - Step 11 generates dated summary

**Validation checklist:**
- [ ] Step 1 completes without error
- [ ] manifest.csv populated with issues
- [ ] Closed/Resolved issues routed correctly
- [ ] Active issues processed
- [ ] Jira messages saved (customer-facing only)
- [ ] Internal notes saved (no customer greeting)
- [ ] Dated summary file created
- [ ] User report generated with next-action list

---

## Success Criteria

**Steps 1–6 implementation is complete when:**

1. ✓ SKILL.md documents full Steps 1–12 orchestration
2. ✓ SKILL.md includes Step 1–2 integration (Python calls via Bash)
3. ✓ Sub-agent loop controller documented in orchestration-loop-controller.md
4. ✓ Sub-agent prompts (Step 3, 5, 6, 9, 10) all self-contained and tested
5. ✓ Sandbox safety checks documented and mandatory
6. ✓ Step 10 file separation enforced with validation checkpoints
7. ✓ Steps 11–12 (summary + user report) documented
8. ✓ All 8 tests above pass
9. ✓ MASTER_IMPLEMENTATION_PLAN.md updated with ✓ COMPLETED

---

## Test Execution Log

| Test # | Name | Status | Notes |
|--------|------|--------|-------|
| 1 | Step 1 — Jira Sync | ⏳ PENDING | Run when .env.jira is ready |
| 2 | Step 2 — Triage Routing | ⏳ PENDING | Depends on Test 1 |
| 3 | SKILL.md Documentation | ⏳ PENDING | Manual review |
| 4 | Loop Controller Docs | ⏳ PENDING | Manual review |
| 5 | Sub-Agent Prompts | ⏳ PENDING | Manual review |
| 6 | Step 10 File Separation | ⏳ PENDING | Manual review |
| 7 | Safety Policy | ⏳ PENDING | Manual review |
| 8 | End-to-End Coherence | ⏳ PENDING | Integration test |

---

## Recommendations for Full Implementation (Steps 7–12)

Once Steps 1–6 are verified, implement Steps 7–12:

1. **Step 7 (Orchestrator):** Decision logic (escalate vs support-resolvable)
2. **Step 8 (Orchestrator):** Implementation stubbed (Salesforce changes)
3. **Step 9 (Sub-agent):** Deploy/test sub-agent spawning
4. **Step 10 (Sub-agent):** Message drafting sub-agent spawning
5. **Step 11 (Orchestrator):** Dated summary generation
6. **Step 12 (Orchestrator):** User report generation

Each step should follow the same discipline: fully self-contained, error handling, logging.

---

## Notes

- Tests 1–2 require live Salesforce/Jira connectivity
- Tests 3–8 are static documentation/code review
- Browser demo requires full Steps 1–12 implementation
- Token budget: Each sub-agent call should return max 300–400 tokens summary
- Loop iterations: Cap at 3 per loop-back scenario (metadata discovery, deploy/test failure)
