# CaseOps 4-Skill Separation Implementation Guide

**Status:** Phase 2 Complete (Investigation Finalization Skill)
**Next:** Phases 3-4 (Notes-and-Escalation Skill + Test Report Skill)

## Pattern Overview

Investigation Finalization Skill demonstrates the pattern for the remaining 2 skills.

### Pattern Applied (Step 5B - Investigation Finalization)

```
Source: step8_agent.py (monolithic)
Extracted → investigation_finalization_agent.py (focused)
│
├─ Directory: skills/investigation-finalization/
│   └─ SKILL.md (canonical)
│   └─ Assets (templates, references)
│
└─ Directory: .claude/skills/investigation-finalization/
    └─ SKILL.md (stub pointer to canonical)
```

**Key features:**
1. Single-purpose prompt (investigation diagnosis only)
2. Focused agent script (~150 LOC)
3. JSON structured output (1 field)
4. Clear input/output (Jira summary → investigation record)
5. Idempotent (skip if already exists)
6. Registered in Claude Code skill selector

## Phase 3: Notes-and-Escalation Skill (Step 8B)

**Purpose:** Diagnose root cause, decide solution path, escalate if needed

**Input:** outputs/investigations/{KEY}.md (from Phase 2)
**Output:** 
- outputs/internal-notes/{KEY}.md
- outputs/engineering-escalations/{KEY}.md (if escalating)

**Create:**
```
notes_and_escalation_agent.py
├─ Reads investigation file
├─ Calls Claude with Notes & Escalation prompt
├─ Writes internal-notes/{KEY}.md
├─ Writes engineering-escalations/{KEY}.md (conditional)
├─ JSON output: { "internal_notes": "...", "eng_handoff": "..." }

skills/notes-and-escalation/SKILL.md
.claude/skills/notes-and-escalation/SKILL.md
```

**Prompt focus:**
- Root cause analysis (from investigation)
- Solution OR escalation decision
- Production vs Sandbox deployment plan
- Engineering handoff (if escalating)

## Phase 4: Test-Report Skill (Step 8D)

**Purpose:** Document test execution, results, validation after Sandbox deployment

**Input:** outputs/internal-notes/{KEY}.md (from Phase 3) + Sandbox deployment output
**Output:** outputs/test-reports/{KEY}.md

**Create:**
```
test_report_agent.py
├─ Reads internal notes file
├─ Reads Sandbox deployment details
├─ Calls Claude with Test Report prompt
├─ Writes test-reports/{KEY}.md
├─ JSON output: { "test_report": "..." }

skills/test-report-drafting/SKILL.md
.claude/skills/test-report-drafting/SKILL.md
```

**Prompt focus:**
- Test cases executed
- Results (pass/fail)
- Validation against acceptance criteria
- Sign-off and readiness for Production

## Orchestration Update (Future)

When all 3 skills are implemented, update `step8_agent.py` or create new orchestrator:

```python
# Orchestration sequence:
1. investigation_finalization_agent.py --key {KEY}  # Step 5B
2. notes_and_escalation_agent.py --key {KEY}        # Step 8B
3. jira_response_agent.py --key {KEY}               # Step 9 (already exists)
4. test_report_agent.py --key {KEY}                 # Step 8D (after Sandbox deploy)
```

## Testing Strategy

**Unit test: Investigation Finalization**
```bash
# 1. Run against sample issue with cached Jira summary
python investigation_finalization_agent.py --key HEAL-33659

# 2. Verify output
cat outputs/investigations/HEAL-33659.md

# 3. Check:
- [ ] Has Issue Understanding section (observed, expected, criteria, unknowns)
- [ ] Has Salesforce Problem section (facts, hypotheses, metadata)
- [ ] Has Similar Items Analysis section (due diligence checklist complete)
- [ ] No solution/deployment/escalation sections (correctly excluded)
```

**Integration test: Full 4-skill flow (when Phases 3-4 complete)**
```bash
# Run against real issue with full pipeline
python run_pipeline.py --issue HEAL-33659
# Then invoke all 4 skills in sequence and verify outputs
```

## Reuse Opportunities

Investigation Finalization pattern can be applied to:
- Notes-and-Escalation (read investigation, produce notes)
- Test-Report (read notes, produce report)
- Any future single-purpose skill

**Template:**
1. Copy investigation_finalization_agent.py → {new_skill}_agent.py
2. Modify prompt (different task, same structure)
3. Change JSON schema (different output field)
4. Update idempotence check (different output file)
5. Create skills/{new_skill}/ with SKILL.md
6. Create .claude/skills/{new_skill}/ with stub

## Architecture Benefits

✓ Single responsibility per skill
✓ Reusable (can run investigation alone)
✓ Testable (each skill independently)
✓ Debuggable (clear input/output)
✓ Maintainable (focused prompts)
✓ Extensible (same pattern for new skills)
✓ Monolithic step8_agent.py → modular skill suite

## Notes

- Investigation Finalization is fully working and registered
- Notes-and-Escalation + Test Report follow identical pattern
- Total effort: ~2-3 hours to complete Phases 3-4
- Can be done in parallel by different engineers (independent skills)
