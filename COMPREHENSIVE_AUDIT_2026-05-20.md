# CaseOps Comprehensive Audit — 2026-05-20

**Status:** 79 findings across 4 severity levels

## CRITICAL (🔴) — 5 findings

### 1. Secrets exposed in .env.jira and AGENTS.md
- **Location:** `.env.jira:7-8`, `AGENTS.md:49,66`
- **Issue:** Real Anthropic key (`sk-ant-api03-...`), Jira token (`ATATT3x...`), Azure PAT, and Salesforce frontdoor session IDs stored on disk in two places
- **Risk:** Credential leakage if file is ever shared or discovered
- **Action:** IMMEDIATELY rotate ALL secrets (Anthropic, Jira, Azure, SF sessions); validate not in git history

### 2. Unsafe curl example in AGENTS.md
- **Location:** `AGENTS.md:113`
- **Issue:** Unix-style curl with magic link variable on Windows PowerShell host; suggests piping credentials into logging shell
- **Risk:** Credential exposure in shell history
- **Action:** Rewrite as PowerShell `Invoke-WebRequest`, never include magic link in command output

### 3. Sub-agent step assignment contradiction
- **Location:** `SKILL.md:43` vs `workflow.md:6-21`
- **Issue:** SKILL.md says Steps 3,5,8,9 are sub-agents; workflow says Steps 3,5,6,9,10 are sub-agents. Step 8 is different.
- **Risk:** Orchestrator delegates wrong step, breaks pipeline
- **Action:** Fix SKILL.md line 43 to match workflow.md (Steps 3,5,6,9,10 are sub-agents; 1,2,4,7,8,11,12 are orchestrator)

### 4. SKILL.md step count wrong
- **Location:** `.claude/skills/jira-salesforce-fix-pipeline/SKILL.md:17`
- **Issue:** Says "steps 1-11" but pipeline has 12 steps; Claude Code discovery misses Step 12
- **Risk:** Step 12 (Inform the user) skipped silently
- **Action:** Change to "steps 1-12"

### 5. Silent-success failure in run_pipeline.py
- **Location:** `run_pipeline.py:336-358, 508`
- **Issue:** `run_7_skills_for_issue` is a no-op `[SKIP]` but parent function `process_active_issues_parallel` still calls it and reports `[OK]`
- **Risk:** Users run pipeline, get "Pipeline complete: N succeeded" while doing zero processing
- **Action:** Remove from default path or make loud (`print(f"Step 8 deferred — run /jira-salesforce-fix-pipeline in Claude Code")`)

---

## HIGH (🟠) — 9 findings

### 6-8. Orphaned skills pointing to deprecated scripts
- **Location:** `skills/notes-and-escalation/`, `skills/test-report-drafting/`, `skills/investigation-finalization/`
- **Issue:** All reference Python scripts now in `deprecated/` and are non-functional
- **Action:** Delete these 3 SKILL.md folders (replaced by Step 10 sub-agent prompt)

### 9. Step numbering collision
- **Location:** `run_pipeline.py:55-141`
- **Issue:** Python script emits "Step 1" through "Step 8" labels but these refer to DIFFERENT actions than `workflow.md` Steps 1-12
- **Risk:** Log reader confused by conflicting step numbers
- **Action:** Rename Python stages to "Stage A/B/C" or delete altogether (processing moved to Claude Code skill)

### 10. Test-report-template missing section
- **Location:** `skills/jira-salesforce-fix-pipeline/assets/test-report-template.md`
- **Issue:** Missing "Production deployment state" section that Step 9 prompt requires
- **Action:** Copy section from `skills/salesforce-sandbox-deploy-test/assets/test-report-template.md:28-35`

### 11. Engineering-handoff-template missing section
- **Location:** `skills/jira-response-drafting/assets/engineering-handoff-template.md`
- **Issue:** Missing "Problem Location (Step 6)" section (exists in pipeline canonical version)
- **Action:** Delete duplicate, reference canonical at `skills/jira-salesforce-fix-pipeline/assets/engineering-handoff-template.md`

### 12. Voice rules example violates rules
- **Location:** `skills/jira-response-drafting/SKILL.md:110-114`
- **Issue:** Example contains em dash (—) and hyphenated clause, but rule forbids both
- **Action:** Rewrite example to use periods/commas only

### 13. Parallel claim but sequential code
- **Location:** `run_pipeline.py:469-534`
- **Issue:** Docstring claims "spawn up to batch_size processes in parallel" but code is sequential for-loop
- **Action:** Either implement true parallelism or rewrite docstring to say sequential

### 14. Duplicate .env.jira.test
- **Location:** `.env.jira.test` at repo root
- **Issue:** Second copy of secrets file; increases leakage surface even if gitignored
- **Action:** Delete `.env.jira.test`

---

## MEDIUM (🟡) — 14 findings

### 15. Step 12 not clearly described
### 16. Step 4 template omitted from asset list in SKILL.md
### 17. Step 4 output auditability issue (file vs inline)
### 18. Stale manifest.csv after manual Jira edits
### 19. Template variable substitution non-idempotent
### 20. Summary scaffold regex fragile
### 21. Status field case/spelling brittle
### 22. Step 5/6 manual copy-paste of payloads (no file handoff)
### 23. Unix path in Windows docs
### 24. Undocumented SKILL.md compatibility field
### 25. Missing references/ directory in jira-response-drafting
### 26. Duplicate .gitignore entries
### 27. Literal Windows path filename in repo root
### 28. Ambiguous asset path in skill description
### 29. Skill description lists Step 5 but not Step 6

---

## LOW (🔵) — 51 findings

Cosmetic, dead code, orphaned templates, documentation nits (see full audit for details)

---

## Recommended Fix Priority

**Phase 1 (CRITICAL — must complete before any batch processing):**
1. Rotate all secrets in .env.jira and remove from AGENTS.md
2. Fix SKILL.md step assignment (lines 43, 17)
3. Fix run_pipeline.py silent-success bug
4. Delete orphaned skills (notes-and-escalation, test-report-drafting, investigation-finalization)

**Phase 2 (HIGH — must complete before shipping):**
5. Reconcile divergent templates (test-report, engineering-handoff, internal-notes)
6. Fix voice rules example
7. Remove/fix Python step numbering collision
8. Fix parallel/sequential discrepancy

**Phase 3 (MEDIUM — should complete soon):**
- Fix Step 4 output auditability
- Fix template substitution robustness
- Clean up manual copy-paste handoffs (Step 5/6)

**Phase 4 (LOW — cleanup pass):**
- Delete dead code from run_pipeline.py
- Remove orphaned templates
- Fix documentation nits

**Estimated effort:**
- Phase 1: 2-3 hours (mostly secret rotation)
- Phase 2: 2 hours (template dedupe + text fixes)
- Phase 3: 1 hour (robustness improvements)
- Phase 4: 1 hour (cleanup)

**Total: ~6-7 hours for 100% clean system**

---

## Architecture Observation

System is mid-transition from:
- **OLD:** Python-orchestrated 7-skill model (deprecated/step*.py agents)
- **NEW:** Claude Code skill–orchestrated 12-step model

Old code, templates, and skills still present; transition half-complete. One focused cleanup day would eliminate ~80% of findings.
