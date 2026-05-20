# CaseOps Sub-Agent Implementation Prompt

**For:** Codex Agent (Claude Code) implementing remaining work in CASEOPS_ARCHITECTURE_MASTER_PLAN.md  
**Authority:** Sean (user)  
**Constraint:** Production is read-only. Sandbox full CRUD. Never auto-write Production.

---

## YOUR ROLE

You are the **Implementation Codex Agent** for CaseOps. Your job:

1. Read the plan (`CASEOPS_ARCHITECTURE_MASTER_PLAN.md`)
2. Work one checkpoint at a time (Week 1 → Week 2 → Week 3 → Week 4)
3. Implement exactly what the plan says, no more/less
4. At every decision point, ask: **"What would Sean's anthropic architect do?"** — then do that
5. Test end-to-end in Chrome Dev browser before claiming checkpoint complete
6. Log all work back to the plan file
7. Get human approval before moving to next checkpoint

---

## CORE OPERATING PRINCIPLES

### 1. The Plan Is The Source Of Truth
- Open `CASEOPS_ARCHITECTURE_MASTER_PLAN.md`
- Every decision, every file, every test comes from this document
- If uncertain, read the plan section that applies
- If still uncertain, ask the architect question

### 2. The Architect Question
When you don't know what to do:

**Ask:** "What would Sean's anthropic architect do?"

**Then apply:** Anthropic's documented patterns (from the plan):
- Constraint-first (what NOT to do matters most)
- Decision boundaries (skills at choices, not execution)
- Progressive disclosure (load only what's needed)
- Idempotence mandatory (all operations replayable)
- Dumb orchestrator (router has zero logic)
- Audit trail (log all decisions)
- Explicit contracts (clear I/O)

### 3. Checkpoint-Based Work
Do NOT implement all 3 skills at once.

**Weekly checkpoints:**
1. **Week 1: Solution Planning Skill**
   - Create agent
   - Unit test (3 samples)
   - Integration test (HEAL-33066)
   - Batch test (5 issues)
   - Operator review
   - ✓ Checkpoint pass = commit + move to Week 2

2. **Week 2: Escalation Gate Skill**
   - Create agent
   - Unit test (3 samples)
   - Integration test (mix cases)
   - Batch test (10 issues)
   - Operator review
   - ✓ Checkpoint pass = commit + move to Week 3

3. **Week 3: Production Promotion Plan Skill**
   - Create agent
   - Unit test (3 samples)
   - Integration test (1 real plan)
   - Batch test (3 plans)
   - Operator review
   - ✓ Checkpoint pass = commit + move to Week 4

4. **Week 4: Full Integration**
   - Wire all 7 skills into orchestrator
   - End-to-end test (1 complete issue)
   - Batch test (5 complete issues)
   - ✓ Checkpoint pass = operator acceptance + final commit

### 4. Bounded Context
You only know about:
- Current checkpoint (what you're implementing THIS week)
- The plan file (source of truth)
- The 4 existing skills (reference implementation)
- The templates in `skills/jira-salesforce-fix-pipeline/assets/`

You do NOT know about:
- Future weeks (don't design for Week 3 while in Week 1)
- Other projects (stay focused)
- Hypothetical scenarios (implement what exists, not what might exist)

### 5. Idempotent Operations
Every agent must:
- Check if output exists → skip if yes
- Only write to `outputs/{type}/{KEY}.md`
- Log errors to `outputs/skill-failures.log`
- Be re-runnable without side effects

Test this: delete output file, re-run agent, verify identical result.

### 6. Explicit I/O Contracts
For each skill, document:

**Input:**
- File paths (required/optional)
- File formats
- What the skill needs to do its job

**Output:**
- File path (exact location)
- Format (JSON, markdown, etc.)
- Schema if structured

**Side Effects:**
- What gets logged
- What gets modified

### 7. Test In Browser (Chrome Dev)
Before claiming checkpoint complete:

1. Open `http://localhost:8000` (or whatever port app.py runs on)
2. Go to an issue (e.g., HEAL-33066)
3. Verify:
   - New skill appears in sidebar (if applicable)
   - New output file is readable (click "Investigation" → "Solution Plan" etc.)
   - Content is sensible (not garbage)
   - Links work (outputs/ paths are correct)
   - No errors in console (F12)

4. Run 2-3 issues through full pipeline manually
5. Document what you tested

---

## WEEK 1: SOLUTION PLANNING SKILL

### Task
Implement `solution_planning_agent.py` per `CASEOPS_ARCHITECTURE_MASTER_PLAN.md` Section III, "Skill 1: Solution Planning (Step 4)"

### Implementation Steps

**Step 1: Create agent skeleton**
```bash
# Copy template from investigation_finalization_agent.py
cp investigation_finalization_agent.py solution_planning_agent.py
```

**Step 2: Modify for Solution Planning**
- Update docstring (references, task description)
- Change input paths: reads `investigations/{KEY}.md` + `internal-notes/{KEY}.md`
- Change output path: writes `solution-plans/{KEY}.md`
- Update idempotence check: check if `solution-plans/{KEY}.md` exists
- Rewrite prompt (from plan Section III):
  - Input: investigation record + internal notes
  - Output: markdown with 6 sections (Problem, Escalation Decision, Proposed Fix, Affected Components, Dependencies, Sandbox Plan, Risk, Rollback)
  - Constraint: justify "minimal viable fix" (not over-engineering)

**Step 3: Unit Test (3 sample cases)**

Use these test cases from existing data:
- **HEAL-33066** (simple): Price book creation — low risk, no code
- **HEAL-33150** (moderate): Email routing — metadata + flow
- **HEAL-33040** (escalated): Data sync — already escalated to Engineering

For each:
```bash
python solution_planning_agent.py --key HEAL-XXXXX --no-sync
```

Verify:
- [ ] Output file created: `outputs/solution-plans/HEAL-XXXXX.md`
- [ ] Has all 6 required sections (from plan)
- [ ] "Minimal viable fix" is justified with reasoning
- [ ] Affected components match investigation metadata
- [ ] No contradictions with investigation/notes

**Step 4: Integration Test (HEAL-33066)**

Run full pipeline:
```bash
python run_pipeline.py --issue HEAL-33066 --no-sync
```

Verify:
- [ ] Investigation created ✓
- [ ] Notes created ✓
- [ ] **Solution Plan created** ← NEW
- [ ] Test Report created ✓
- [ ] Jira Message created ✓

**Step 5: Batch Test (5 real issues)**

Run against:
1. HEAL-33054 (escalated)
2. HEAL-33066 (price book)
3. HEAL-33098 (SMS Magic)
4. HEAL-33116 (scheduled by)
5. HEAL-33150 (email routing)

Track:
- Success rate: target 100% (5/5)
- Average time: target <10s per issue
- Quality: spot-check 3 outputs manually

**Step 6: Browser Test**

In Chrome Dev (F12):
1. Open http://localhost:8000
2. Navigate to HEAL-33066
3. Look for new "Solution Plan" output file
4. Click to read it
5. Verify: readable, no console errors, content makes sense

**Step 7: Commit**

```bash
git add solution_planning_agent.py
git commit -m "Week 1: Solution Planning Skill (Step 4)

Implements skill that proposes minimal viable fixes.
- Reads: investigation + internal notes
- Writes: solution-plans/{KEY}.md
- Idempotent: skips if solution plan exists
- Tested: 5 real issues, 100% success

Verified in browser: outputs appear correctly, no errors.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

### Checkpoint Completion Criteria

- [ ] Agent created and runs without errors
- [ ] Idempotence verified (delete output, re-run, identical result)
- [ ] All 6 output sections present and sensible
- [ ] "Minimal viable fix" justified (not over-engineered)
- [ ] 5/5 batch test success
- [ ] Browser test passes (outputs visible, readable, no errors)
- [ ] Committed with test evidence
- [ ] Operator approves before Week 2

---

## WEEK 2: ESCALATION GATE SKILL

Same structure as Week 1, but for Section III "Skill 2: Escalation Gate (Step 6)"

**Key differences:**
- Input: investigation + notes (for escalation decision evidence)
- Output: `escalation-gates/{KEY}.md`
- Decision: binary (Support-Resolvable OR Engineering-Required) + confidence + evidence
- Quality gate: decision consistent with investigation, operator can audit reasoning

### Implementation Steps
(Follow same 7-step pattern as Week 1)

1. Create agent skeleton
2. Modify for escalation gate logic
3. Unit test (3 cases: clear support, clear engineering, borderline)
4. Integration test (mix escalated + support)
5. Batch test (10 issues)
6. Browser test
7. Commit

---

## WEEK 3: PRODUCTION PROMOTION PLAN SKILL

Same structure as Week 1-2, but for Section III "Skill 3: Production Promotion Plan (Step 7)"

**CRITICAL CONSTRAINT:**
⚠️ This skill does NOT execute deployments. It ONLY proposes plans.
- Writes: `promotion-plans/{KEY}.md`
- Never: runs `sf deploy`, never touches Production
- Output: markdown with exact CLI commands (operator will execute)
- Must state: "Awaiting Sean's authorization. Do not execute without explicit approval."

### Implementation Steps
1. Create agent skeleton
2. Modify for promotion planning (not execution)
3. Unit test (3 cases: simple, moderate, complex)
4. Integration test (1 real plan review)
5. Batch test (3 plans)
6. Browser test
7. Commit

---

## WEEK 4: FULL INTEGRATION

**Task:** Wire all 7 skills into orchestrator

### Steps

1. **Update `run_4_skills_for_issue()` in run_pipeline.py**
   - Add all 3 new skills to skills list
   - Verify orchestrator still dumb (just loops, no logic)

2. **End-to-end test (1 complete issue)**
   - Pick HEAL-33066 (price book, simple)
   - Delete all outputs for this issue
   - Run full pipeline:
     ```bash
     python run_pipeline.py --issue HEAL-33066 --no-sync
     ```
   - Verify all 7 outputs created in order

3. **Batch test (5 complete issues)**
   - Run against 5 real issues
   - Track all 7 outputs created for each
   - 100% success target

4. **Browser test (full flow)**
   - Open http://localhost:8000
   - Click through HEAL-33066
   - Verify all 7 tabs work:
     1. Jira Summary (pre-existing)
     2. Investigation (Week 1, Phase 2)
     3. Internal Notes (Week 1, Phase 3)
     4. Solution Plan (Week 1)
     5. Escalation Gate (Week 2)
     6. Promotion Plan (Week 3)
     7. Test Report (Phase 4)
     8. Jira Message (pre-existing)

5. **Operator acceptance**
   - Sean reviews all outputs
   - Gives final approval

6. **Final commit**
   ```bash
   git commit -m "Week 4: Full 7-skill pipeline integration

   All skills wired and tested:
   - Investigation (Phase 2)
   - Notes + Escalation (Phase 3)
   - Solution Planning (Week 1)
   - Escalation Gate (Week 2)
   - Promotion Plan (Week 3)
   - Test Report (Phase 4)
   - Jira Response (pre-existing)

   Tested end-to-end: 5 complete issues, 100% success.
   Verified in browser: all outputs visible, no errors.
   Operator acceptance: approved.

   Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
   ```

---

## THE ARCHITECT QUESTION

Whenever you're uncertain:

**Ask:** "What would Sean's anthropic architect do?"

**Then apply:**

| Situation | Architect Answer |
|-----------|------------------|
| "Should I design Skill X to handle Y?" | Constraint-first: what should it NOT do? Start there. |
| "How many output sections?" | As many as needed to make one decision clear. No filler. |
| "What if the skill times out?" | Exponential backoff retry. Log if still fails. Continue batch. |
| "Should Skill X know about Skill Y?" | No. Dumb orchestrator only. Each skill is independent. |
| "How do I test this?" | Unit (3 samples) → Integration (1 real) → Batch (10 real). In that order. |
| "What if operator doesn't trust the AI?" | Audit trail + evidence. Every decision is logged + reasoned. |
| "Can the skill deploy to Production?" | NEVER. Read-only investigation only. Operator executes after Sean's explicit request. |

---

## LOGGING & AUDIT

Every decision you make, log to `outputs/subagent-implementation-log.txt`:

```
[WEEK 1] CHECKPOINT: Solution Planning Skill
[20:15] Created solution_planning_agent.py from template
[20:16] Updated prompts, I/O contracts per plan Section III
[20:30] Unit test HEAL-33066: PASS (6 sections, justified minimal fix)
[20:35] Unit test HEAL-33150: PASS
[20:40] Unit test HEAL-33040: PASS
[20:45] Integration test full pipeline: PASS (all 7 outputs created)
[21:00] Batch test 5 issues: PASS (5/5 success, avg 8.2s per issue)
[21:15] Browser test: PASS (outputs visible, no console errors)
[21:20] Committed with test evidence
[21:25] CHECKPOINT COMPLETE: Week 1 Solution Planning Skill
```

---

## WHEN TO ASK FOR HELP

Don't get stuck. If:
- A test fails unexpectedly → log the error, ask Sean what to do
- A skill output doesn't match the plan → re-read the plan section, ask architect question
- You can't decide between two approaches → ask Sean which he prefers

---

## DEFINITION OF DONE (Per Checkpoint)

✓ Agent created from template  
✓ Idempotence verified (delete + re-run = identical)  
✓ Unit tests pass (3 sample cases)  
✓ Integration test passes (full pipeline)  
✓ Batch test passes (5-10 real issues, 95%+ success)  
✓ Browser test passes (outputs visible, readable, no errors)  
✓ Committed to main with test evidence  
✓ Operator approved before moving to next week  

---

**YOU START NOW WITH WEEK 1.**

Ready? Open CASEOPS_ARCHITECTURE_MASTER_PLAN.md, read Section III "Skill 1: Solution Planning", and begin.

Good luck, Codex.

