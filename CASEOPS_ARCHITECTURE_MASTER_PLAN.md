# CaseOps Architecture Master Plan
## Constraint-Driven Skill Separation Strategy

**Date:** 2026-05-19  
**Status:** Foundation Complete (4-skill pipeline). Next: 3 skills planned.  
**Architect:** Claude (Anthropic patterns)

---

## ⚠️ PRODUCTION SAFETY — CRITICAL CONSTRAINT

**MANDATORY RULE:**
> CaseOps has ZERO authority to write, edit, change, upsert, insert, or delete anything in Production.
> 
> - Production access is read-only by default (investigation only)
> - Sandbox access is full CRUD (authorized for testing only)
> - CaseOps can PROPOSE Production changes via promotion plans
> - **ONLY Sean can authorize Production changes by explicitly requesting execution**
> - Promotion plans are proposals; they do NOT auto-execute
> - Any Production change requires a separate explicit user request: "go ahead and deploy this"

**Code Audit Required:**
Before deploying any skill, verify:
- [ ] Zero `sf deploy` or `sfdx deploy` commands in skill code
- [ ] Zero Production API writes (all writes go to `outputs/`)
- [ ] All Production access uses read-only credentials/methods
- [ ] Promotion plans only write `.md` files, never execute anything
- [ ] Error logs never imply Production was modified

---

## I. Core Principles (Non-Negotiable)

### 1. Constraint-First Design
**What we DON'T want (matters more than what we DO):**
- ✗ Context bloat (tokens used ≠ better decisions; smaller context often wins)
- ✗ Mixed responsibilities (one skill = one decision OR one irreducible workflow)
- ✗ Side effects (every operation must be replayable/idempotent)
- ✗ Ambiguous contracts (skill output format must be explicitly defined)
- ✗ Orchestrator logic (keep router dumb; decisions stay in skills)
- ✗ Untested abstractions (test against real data before generalizing)
- ✗ **CRITICAL: NEVER auto-write to Production.** Production is read-only by default. Only Sean can authorize Production writes. CaseOps PROPOSES deployments, operator EXECUTES after explicit approval.

### 2. Decision Boundary Alignment
Skills exist at **decision points**, not execution boundaries:
- Investigation → Decision (does this escalate?)
- Notes + Escalation Decision → Decision (what's the minimal fix?)
- Solution Plan → Decision (deploy to Sandbox or manual steps?)
- Test Results → Decision (production ready?)

Execution (run Sandbox deploy, run CLI commands) stays in orchestrator or in dedicated execution scripts.

### 3. Idempotence Mandatory
Every skill must safely re-run:
- Input: issue key, outputs directory
- Output: specific file path
- Behavior: if output exists, skip gracefully
- No state mutations, no partial writes, no retry loops in skill itself

### 4. Progressive Disclosure
Load only what the skill needs, when it needs it:
- Investigation skill: reads Jira summary only (not full issue history)
- Notes skill: reads investigation file only (not Jira + investigation + prior runs)
- Solution planning: reads investigation + notes (not full artifacts)

Token budgets per skill: 300–500 tokens input + focused prompt.

### 5. Explicit I/O Contracts
Each skill documents:
- Input files (paths, required/optional)
- Output files (paths, format, schema if JSON)
- Side effects (what it logs, what it modifies)
- Error conditions (what can fail, how failure manifests)
- Re-playability (what happens if run twice)

---

## II. Current State (Foundation Complete)

### Deployed: 4-Skill Pipeline
| Phase | Skill | Agent | Input | Output | Status |
|-------|-------|-------|-------|--------|--------|
| 5B | Investigation Finalization | `investigation_finalization_agent.py` | Jira summary | `investigations/{KEY}.md` | ✓ Live |
| 8B | Notes & Escalation | `notes_and_escalation_agent.py` | Investigation | `internal-notes/{KEY}.md`<br/>`engineering-escalations/{KEY}.md` | ✓ Live |
| 8D | Test Report | `test_report_agent.py` | Internal notes | `test-reports/{KEY}.md` | ✓ Live |
| 9 | Jira Response | `jira_response_drafting.py` | Investigation + Notes | `jira-messages/{KEY}.md` | ✓ Pre-existing |

**Orchestration:** `run_4_skills_for_issue()` in `run_pipeline.py`
- Runs skills sequentially (not parallel)
- Retry: exponential backoff per skill
- Error logging: `skill-pipeline-failures.log`
- Tested: HEAL-33054, HEAL-33066, HEAL-33098, HEAL-33116, HEAL-33150 ✓

**Quality metrics:**
- Idempotence: ✓ (all 4 skills skip if output exists)
- Output quality: ✓ (verified against 5 real issues)
- Error recovery: ✓ (retry + log + continue batch)
- Integration: ✓ (full 4-skill flow tested end-to-end)

---

## III. Next Phase: 3 Skills (Planned)

### Skill 1: Solution Planning (Step 4)
**Decision Boundary:** "What is the minimal viable fix?"

**Constraints:**
- ✗ Don't load full Jira history (use investigation summary)
- ✗ Don't decide on escalation (take escalation decision as input)
- ✗ Don't propose over-engineered fixes (justify "minimal")
- ✗ Don't assume Production state (investigation has verified facts)

**Input Contract:**
- `outputs/investigations/{KEY}.md` (required)
- `outputs/internal-notes/{KEY}.md` (required, for escalation decision)

**Output Contract:**
```json
{
  "solution_plan": "markdown with sections:
    - Problem Statement (from investigation)
    - Escalation Decision (from notes)
    - Proposed Fix (smallest viable)
    - Affected Components (list: fields, flows, validation rules, etc.)
    - Dependencies (what else must change if this changes)
    - Sandbox Plan (deployment strategy)
    - Risk Assessment (will this break other things?)
    - Rollback Plan (how to undo if needed)"
}
```

**File:** `outputs/solution-plans/{KEY}.md`

**Staging:**
1. Unit test: sample investigation + notes → expected fix plan
2. Integration: run against HEAL-33054 (price book—low risk)
3. Batch: run against 5 issues (mix of escalated + support-resolvable)
4. Rollback test: remove output, re-run, verify identical

**Quality Gate:**
- ✓ Has all 6 sections
- ✓ "Minimal viable" is justified (not over-engineering)
- ✓ Affected components match investigation metadata
- ✓ Sandbox plan is concrete (not vague)

---

### Skill 2: Escalation Gate (Step 6)
**Decision Boundary:** "Support-resolvable OR Engineering-required?"

**Constraints:**
- ✗ Don't make the decision alone (investigate fact, present evidence)
- ✗ Don't ignore investigation evidence (if investigation says "Engineering", honor it)
- ✗ Don't be ambiguous (confidence score + reasoning)
- ✗ Don't skip audit trail (log decision + evidence for human review)

**Input Contract:**
- `outputs/investigations/{KEY}.md` (required)
- `outputs/internal-notes/{KEY}.md` (required, has escalation draft)

**Output Contract:**
```json
{
  "escalation_decision": "markdown with sections:
    - Decision (Support-Resolvable / Engineering-Required)
    - Confidence (High / Medium / Low with reasoning)
    - Key Evidence (facts from investigation that support decision)
    - Gate Check (any red flags for human review?)
    - Next Step (if Support: propose fix; if Engineering: handoff brief)"
}
```

**File:** `outputs/escalation-gates/{KEY}.md`

**Staging:**
1. Unit test: clear cases (metadata bug → Support; Apex flow → Engineering)
2. Integration: run against borderline case (HEAL-33150)
3. Batch: run against 10 mixed issues
4. Human review: operator spot-checks decisions, flags misclassifications

**Quality Gate:**
- ✓ Decision is binary (no "maybe")
- ✓ Confidence is explicit with evidence
- ✓ No contradictions with investigation
- ✓ Operator can audit reasoning

---

### Skill 3: Production Promotion Plan (Step 7)
**Decision Boundary:** "How would we safely promote Sandbox changes to Production? (PROPOSAL ONLY — Sean must explicitly authorize execution)"

**CRITICAL CONSTRAINT:**
⚠️ **This skill ONLY PROPOSES deployment plans. It NEVER executes any Production changes.**
- CaseOps has ZERO authority to write to Production
- Only Sean can authorize Production changes
- User must explicitly ask ("go ahead and deploy this") before operator executes
- All Production access is read-only by default (investigation only)
- Sandbox access is full CRUD (authorized for testing)

**Constraints:**
- ✗ NEVER execute Production change without explicit user request
- ✗ Don't skip validation (include pre-deploy verification steps)
- ✗ Don't ignore org-specific deployment method (respect `CASEOPS_DEPLOY_METHOD`)
- ✗ Don't forget rollback (always include undo steps)
- ✗ Don't assume auto-anything (write plan, operator executes after user approval)

**Input Contract:**
- `outputs/internal-notes/{KEY}.md` (required, has deployment plan)
- `outputs/solution-plans/{KEY}.md` (required, affected components)
- `outputs/test-reports/{KEY}.md` (required, validation proof in Sandbox)

**Output Contract:**
```json
{
  "promotion_plan": "markdown with sections:
    - Summary (what metadata will change in Production)
    - Pre-Deployment Checklist (verify current Production state)
    - Promotion Steps (exact CLI/Gearset commands — operator will execute)
    - Validation Steps (post-deploy smoke test — operator will run)
    - Rollback Plan (if validation fails, revert with these steps)
    - Risk Assessment (what could break?)
    - Sign-Off Criteria (how do we know Production is good?)
    - EXPLICIT: 'Awaiting Sean's authorization to proceed. Do not execute without explicit approval.'"
}
```

**File:** `outputs/promotion-plans/{KEY}.md` (named explicitly to avoid confusion with deploy-plans)

**Staging:**
1. Unit test: generate promotion plan for HEAL-33066 (price book—simple)
2. Integration: operator reviews plan, confirms with Sean before executing
3. Batch: 3 real production promotions (after Sean approves each)
4. Metric: zero unplanned changes, zero Production impact without approval

**Quality Gate:**
- ✓ Steps are concrete (exact Gearset package ID or exact CLI command)
- ✓ Validation is testable (not "looks good"; exact checks: "verify field exists + FLS matches")
- ✓ Rollback is documented and tested
- ✓ Explicitly states "requires Sean's authorization"
- ✓ Zero auto-execution code paths

---

## IV. Orchestration Changes (When All 3 Skills Exist)

Current `run_4_skills_for_issue()` flow:
```
Investigation → Notes → Test Report → (Optional Jira Response)
```

New flow (when 3 skills added):
```
Investigation → Notes → Escalation Gate → Solution Planning → Promotion Plan (PROPOSAL) → Test Report → Jira Response
```

**Orchestrator stays dumb:**
```python
skills = [
  ("investigation", investigation_finalization_agent.py),
  ("notes", notes_and_escalation_agent.py),
  ("escalation", escalation_gate_agent.py),              # NEW
  ("solution_plan", solution_planning_agent.py),         # NEW
  ("promotion_plan", production_promotion_agent.py),     # NEW (PROPOSAL ONLY)
  ("test_report", test_report_agent.py),
  ("jira_response", jira_response_drafting.py),
]
for skill_name, script in skills:
  run_agent_with_retry(script, key, out_dir)
```

No conditional logic. No branching. Router only loops.

⚠️ **CRITICAL:** Skill 7 (promotion_plan) ONLY WRITES PROPOSAL PLANS. It does NOT execute any Production changes. Sean must explicitly authorize execution in a separate request.

---

## V. Testing Strategy (Applies to All 3 Skills)

### Unit Testing
Create sample inputs for each skill type:
- **Simple:** HEAL-33066 (price book—no code, straightforward)
- **Moderate:** HEAL-33150 (email routing—metadata + flow)
- **Complex:** HEAL-33040 (data sync—architecture question)
- **Escalated:** HEAL-33054 (already decided → Engineering)

### Integration Testing
Run full pipeline 1 skill at a time:
1. Investigation alone (5 issues)
2. Investigation + Notes (5 issues)
3. Add Escalation Gate (3 escalated, 2 support)
4. Add Solution Plan (2 support-resolvable)
5. Add Deploy Plan (1 after sandbox validation)
6. Full 7-skill flow (1 complete issue)

### Batch Testing
Run all 3 new skills against 10 real open issues. Track:
- Success rate per skill
- Average time per skill
- Error rate (permanent vs transient)
- Output quality (spot-check 3 samples)

### Regression Testing
After each skill is added, re-run the 4 existing skills:
- All should still pass
- No cross-skill interference
- Outputs should be identical to baseline

---

## VI. Quality & Monitoring

### Per-Skill Metrics
Track for each run:
- Input size (tokens consumed)
- Output size (lines generated)
- Time taken
- Retries (if any)
- Errors (if any)
- Confidence (high/medium/low if applicable)

Log to: `outputs/skill-metrics-{YYYY-MM-DD}.json`

### Audit Trail
Every decision skill must log:
- Issue key
- Decision made
- Confidence/evidence
- Timestamp
- Operator who triggered it (if applicable)

Log to: `outputs/audit-log.jsonl` (one entry per decision)

### Quality Gates (Go/No-Go Criteria)

**Before moving skill to production:**
- [ ] Unit tests pass (all 3 sample cases)
- [ ] Integration tests pass (5+ real issues)
- [ ] Batch tests pass (10 real issues, 95%+ success)
- [ ] Operator spot-check pass (3 samples verified manually)
- [ ] Error recovery verified (retry + fallback works)
- [ ] Rollback tested (re-run produces identical output)
- [ ] Documentation complete (SKILL.md + examples)
- [ ] No regressions (4 existing skills still pass)

---

## VII. Rollout Timeline

**Week 1 (This week): Solution Planning**
- Day 1: Create `solution_planning_agent.py` + unit tests
- Day 2: Integration test against HEAL-33066
- Day 3: Batch test (5 issues) + operator review
- Day 4: Fix issues, re-test, commit

**Week 2: Escalation Gate**
- Day 1: Create `escalation_gate_agent.py` + unit tests
- Day 2: Integration test (mix escalated + support)
- Day 3: Batch test (10 issues) + operator review
- Day 4: Fix issues, commit

**Week 3: Production Deployment**
- Day 1: Create `production_deployment_agent.py` + unit tests
- Day 2: Integration test (1 real prod deploy)
- Day 3: Batch test (3 prod deploys) + operator review
- Day 4: Fix issues, commit

**Week 4: Full Integration**
- Day 1: Wire all 7 skills into orchestrator
- Day 2: Full pipeline test (1 complete issue end-to-end)
- Day 3: Batch test full pipeline (5 complete issues)
- Day 4: Operator acceptance + documentation

---

## VIII. Risk Mitigation

### Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **CRITICAL: Accidental Production write** | NO skill has Production write capability. Promotion plan is proposal only. Sean must explicitly authorize any Production change in a separate request. Code audit required to verify zero auto-write paths. |
| Skill timeout (API slow) | Exponential backoff retry; if 2 fails, log + continue batch |
| Malformed output (JSON parse error) | Catch parse error, log details, skip issue, operator reviews later |
| Skill contradicts investigation | Quality gate: escalation gate explicitly checks consistency |
| Orchestrator becomes complex | Keep it dumb—no conditional logic, just loop |
| Too many commits | One skill = one commit; group related tests in single commit |
| Operator doesn't trust AI decisions | Audit trail + evidence always included; gate checks exist |
| Promotion plan gets auto-executed | CANNOT HAPPEN: skill only writes file, never executes. Execution requires separate explicit user request. Audit: grep codebase for "sf deploy" or "sfdx deploy" in any skill—should be ZERO hits. |

### Rollback Procedure
If skill produces bad output:
1. Remove output file: `rm outputs/{type}/{KEY}.md`
2. Remove any error log entries for that key
3. Re-run skill: `python run_pipeline.py --issue {KEY} --no-sync`
4. Operator reviews new output
5. If still bad: disable skill in orchestrator, investigate root cause

---

## IX. Success Criteria

**Phase 1 (Current - Complete):**
- ✓ 4 skills deployed and tested
- ✓ Orchestrator dumb and routing
- ✓ All idempotent and retryable
- ✓ Real issues processed successfully

**Phase 2 (Next - This Plan):**
- [ ] 3 new skills created + tested
- [ ] Full 7-skill pipeline operational
- [ ] 10+ real issues processed end-to-end
- [ ] Zero unplanned production changes
- [ ] Operator confidence in decisions (audit trail + evidence)
- [ ] <5% error rate per skill
- [ ] <5 min per issue average (all 7 skills)

**Long-term (Post-Phase 2):**
- [ ] Fully autonomous pipeline (operator only reviews + confirms)
- [ ] <1 min per issue average (all 7 skills, batch mode)
- [ ] Skill reuse for other workflows (e.g., cost estimation, forecasting)
- [ ] Community-contributed skills (Salesforce + Jira plugins)

---

## X. Architecture Patterns Applied

### From Anthropic's Framework
1. ✓ **Progressive disclosure** — skills load only needed context
2. ✓ **Single responsibility** — one skill = one decision
3. ✓ **Idempotence** — all skills replayable
4. ✓ **Clear contracts** — explicit I/O formats
5. ✓ **Dumb orchestration** — router has no logic
6. ✓ **Focused prompts** — narrow scope per skill
7. ✓ **Audit trail** — decisions are logged + traceable
8. ✓ **Constraint-driven** — designed around what NOT to do

### From High-Velocity Teams
1. ✓ **Atomic commits** — one complete unit per commit
2. ✓ **Staged testing** — unit → integration → batch
3. ✓ **Monitoring from day 1** — metrics logged everywhere
4. ✓ **Rollback-first** — every operation is reversible
5. ✓ **Error handling explicit** — not "try/catch", but "log + continue"
6. ✓ **Operator confirmation** — AI proposes, human decides (high-stakes)

---

## XI. Implementation Checkpoints

### Checkpoint: Solution Planning (Week 1)
- [ ] Agent created and tested locally
- [ ] Passes 3 unit test cases
- [ ] Passes integration test (HEAL-33066)
- [ ] Passes batch test (5 issues)
- [ ] Output file location: `outputs/solution-plans/{KEY}.md`
- [ ] Committed to main with test evidence

### Checkpoint: Escalation Gate (Week 2)
- [ ] Agent created and tested locally
- [ ] Passes 3 unit test cases
- [ ] Passes integration test (mix cases)
- [ ] Passes batch test (10 issues)
- [ ] Audit trail logging verified
- [ ] Committed to main with test evidence

### Checkpoint: Production Deployment (Week 3)
- [ ] Agent created and tested locally
- [ ] Passes 3 unit test cases
- [ ] Passes integration test (1 real prod deploy)
- [ ] Passes batch test (3 prod deploys)
- [ ] Rollback plan verified
- [ ] Committed to main with test evidence

### Checkpoint: Full Integration (Week 4)
- [ ] All 7 skills wired into orchestrator
- [ ] Full pipeline passes end-to-end test (1 complete issue)
- [ ] Full pipeline passes batch test (5 complete issues)
- [ ] Metrics collected and reviewed
- [ ] Operator sign-off
- [ ] Final commit: "Full 7-skill pipeline operational"

---

## XII. How This Plan Actually Works

**Why constraint-first?**  
It's easier to add a feature than remove complexity. Start with "what must NOT happen" → you naturally design better.

**Why staged testing?**  
Prevents disasters. Find bugs at unit stage (1 minute fix) not production stage (1 hour incident).

**Why idempotence mandatory?**  
Lets you re-run without fear. If Jira sync fails halfway, re-run it. No state corruption.

**Why dumb orchestrator?**  
Complex routers become bottlenecks. Keep orchestrator 20 lines. Logic belongs in skills.

**Why audit trail everything?**  
Operator needs to trust AI decisions. "Why did it escalate?" must be answerable by looking at logs.

**Why this timeline?**  
1 skill per week lets you catch problems early. By week 4, you're confident + fast.

---

**Next Action:** Review this plan with operator. If approved, start Week 1: Solution Planning skill.

