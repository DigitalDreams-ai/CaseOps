# CaseOps Anthropic Framework Audit — 2026-05-19

## Summary

**Overall Assessment: Excellent.** CaseOps demonstrates strong alignment with Anthropic's context engineering and agent skills frameworks. Core architecture is sound. Identified gaps are non-blocking optimizations.

**Alignment Score:** 9/10

---

## Framework 1: Context Engineering

### ✓ System Prompts
- `step8_agent.py` uses well-structured prompts with clear sections
- Role definition, context, task breakdown, strict output format
- Templates embedded for format guidance
- Marker-based parsing enforces structure (`---INVESTIGATION---`, `---INTERNAL-NOTES---`, `---JIRA-MESSAGE---`)
- Clear guidance on what not to do (Response Format section)

### ✓ Tool Design
- 5 skills, each narrowly focused (zero overlap):
  1. `jira-salesforce-fix-pipeline` — main orchestrator
  2. `jira-issue-analysis` — Step 3 only
  3. `salesforce-production-metadata-investigation` — Step 5 only
  4. `salesforce-sandbox-deploy-test` — Step 8 (deployment guard)
  5. `jira-response-drafting` — Step 9 only
- Clear "Use When" / "Do Not Use When" boundaries
- Each tool serves single, well-defined purpose

### ✓ Sub-Agent Architecture
- **Orchestrator steps** (deterministic): 1, 2, 4, 6, 7, 10, 11 (run in main context)
- **Sub-agent steps** (AI reasoning): 3, 5, 8, 9 (delegated, return 300-500 token summaries)
- Orchestrator never loads full sub-agent output files; only reads summary returns
- One sub-agent per step per issue (no batching)
- Self-contained prompts in `sub-agent-prompts.md` template (SKILL.md line 15)

### ✓ Compaction / Context Management
- `nightly_run.py`: calls `jira_sync --incremental` (fresh data) then `run_nightly_precompute()` (scaffold from cache)
- `run_pipeline.py`: deterministic triage → external memory artifacts (outputs/)
- `step8_agent.py` per-issue: loads ONLY Jira summary + investigation (not all 32 issues)
- Confidence flags signal investigation depth (low = thin, high = thorough)
- Manifest cached in `outputs/jira/manifest.csv` (just-in-time refresh)

### ✓ Dynamic Context Retrieval
- Flask app loads manifests on-demand from disk
- Sidebar shows open issue count (fresh calculation, not pre-computed)
- Client-side filter/sort on issue list (no server-side pre-filtering)
- Templates stored separately; loaded when building prompts

---

## Framework 2: Agent Skills

### ✓ Skill Structure
- All skills have SKILL.md with YAML frontmatter (name, description)
- Progressive disclosure architecture:
  - Core guidance in SKILL.md
  - References (workflow.md, sub-agent-prompts.md, safety-policy.md) loaded when needed
  - Asset templates (investigation-record, internal-notes, jira-message) optional load
- Example: `jira-salesforce-fix-pipeline/SKILL.md` → reference `references/workflow.md` for steps 1-11

### ✓ Metadata Clarity
- `jira-salesforce-fix-pipeline` description is specific and actionable (line 3-4)
  - Names mandatory configs: `CASEOPS_SANDBOX_TARGET_ORG`, `.env.jira`
  - Explains when to use (Jira issues, Salesforce diagnosis) and when not (general explanations, non-Jira tasks)
- `salesforce-sandbox-deploy-test` leads with **hard requirements** (security-first)
  - Line 8-14: non-negotiable allowlist checks
  - Line 12-13: STOP conditions (missing env var, org mismatch)

### ✓ Security-First Design
- `salesforce-sandbox-deploy-test`:
  - Enforces read `CASEOPS_SANDBOX_TARGET_ORG` before any deploy
  - Requires exact CLI target match (no "pick the closest")
  - Production remains read-only (separate skill/prompt)
  - STOP condition: if env var missing or org doesn't match, refuse to proceed
- `step8_agent.py`:
  - Uses `os.environ.get()` with fallback
  - Clamps `max_tokens` to [256, 64000] range (line 200)
  - API key validation before calling Claude (line 193-196)

### ✓ Iterative Design Pattern
- Confidence flag system (token count → high/low) enables operator feedback loop
- Investigation scaffolding allows manual enhancement before AI step
- Test reports feed back to pipeline iteration (Step 8 failure → re-implement → re-test)

---

## Identified Gaps (Non-Blocking)

### 1. Skill Directory Duplication
**Issue:** Two copies of SKILL.md exist:
- `/skills/jira-salesforce-fix-pipeline/SKILL.md` (canonical)
- `.claude/skills/jira-salesforce-fix-pipeline/SKILL.md` (copy/pointer)

**Risk:** Drift. Updates to one copy may not reflect in the other.

**Fix:** Remove `.claude/skills/` copy; ensure Claude Code discovers `/skills/` at repo root as authoritative source.

**Priority:** Medium. Current state works but violates single-source-of-truth principle.

---

### 2. Incomplete Skill Registration in `.claude/`
**Issue:** Only `jira-salesforce-fix-pipeline` has `.claude/skills/` entry.
- Other 4 skills (`jira-issue-analysis`, `salesforce-production-metadata-investigation`, `salesforce-sandbox-deploy-test`, `jira-response-drafting`) exist in `/skills/` but not discoverable as independent skills in `.claude/`
- They're referenced **inside** jira-salesforce-fix-pipeline SKILL.md (lines 15, 21), but Claude Code may not discover them without `.claude/` entry

**Fix:** Create `.claude/skills/jira-issue-analysis/`, `.claude/skills/salesforce-production-metadata-investigation/`, etc. Each should point to canonical file in `/skills/`.

**Priority:** Medium. Affects Claude Code skill discoverability UI, but functionality still works via orchestrator.

---

### 3. Marker-Based Response Parsing: Fragile
**Issue:** `step8_agent.py` line 215-240 uses regex marker parsing (`---INVESTIGATION---`, `---INTERNAL-NOTES---`, `---JIRA-MESSAGE---`).
- If Claude outputs text before first marker or forgets markers, parsing fails with generic "response missing required markers"
- No fallback/recovery; hard error

**Better Approach:** Use Claude's native structured outputs (e.g., JSON schema constraint) instead of marker-based string splits.

**Priority:** Low. Current approach works reliably in practice; only matters if Claude format drifts.

---

### 4. Confidence Flag: Incomplete Signal
**Issue:** Confidence flag measures investigation effort only:
- High = 300+ tokens (thorough investigation)
- Low = < 300 tokens (thin investigation)

**Gap:** Does NOT measure solution correctness. High-confidence investigation can still recommend wrong fix.

**Better Signal:** Add post-deployment validation flag:
- "Deployed to Production & customer confirmed fixed"
- "Sandbox tested, awaiting Production promotion"
- "Failed testing; marked for re-investigation"

**Priority:** Low. Current flag serves its purpose (flagging thin investigations). Post-deployment validation is separate concern.

---

### 5. Context in App.py: Minor Optimization Opportunity
**Issue:** `app.py` line 870-872 calculates `open_count` fresh on every page load by filtering manifest.
- Could be cached or pre-computed during manifest sync
- Minor: acceptable performance for small datasets

**Priority:** Very Low. No user-facing impact.

---

## Recommendations

### Ship As-Is
All identified gaps are optimizations, not architectural flaws. Core system is production-ready.

### Priority Fixes (Do Next)

1. **Consolidate skill sources** (Gap 1-2)
   - Make `/skills/` authoritative
   - Remove/simplify `.claude/` duplicates
   - Effort: 1-2 hours
   - Benefit: Eliminates drift risk, improves maintainability

2. **Implement structured outputs** (Gap 3, optional)
   - Replace marker-based parsing with Claude JSON schema constraint
   - Effort: 2-3 hours
   - Benefit: Eliminates parsing brittleness, improves error messages

3. **Add post-deployment validation flag** (Gap 4, future)
   - Supplement confidence flag with real-world fix confirmation
   - Effort: 1-2 hours (for flag structure; validation workflow is operator responsibility)
   - Benefit: Closes loop between investigation and production outcome

---

## Conclusion

**CaseOps is well-architected and production-ready.** It successfully implements:
- ✓ Anthropic's context engineering best practices (compaction, sub-agents, dynamic retrieval)
- ✓ Anthropic's agent skills framework (progressive disclosure, security-first, clear boundaries)
- ✓ Deterministic pipeline + AI reasoning separation
- ✓ Idempotent, per-issue processing
- ✓ Security guards (sandbox allowlist, read-only Production)

No critical flaws. Ship with confidence. Fix identified gaps on next sprint.
