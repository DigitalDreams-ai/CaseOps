# CaseOps 2026 Application-Layer Optimization Plan

**Owner:** Sean  
**Scope:** Application-layer optimization (batch, cache, pre-compute, confidence flags)  
**Constraint:** Dev/test only. No Jira writes. No production deployment.  
**Timeline:** Single session  
**Success:** All 4 phases implemented + smoke tested

---

## Phase 1: Batch Size Tuning (5 → 12)

**File:** `run_pipeline.py`  
**Current:** `batch_size=5`  
**Target:** `batch_size=12`

### Implementation
1. Locate line: `batch_size=5` in run_pipeline.py
2. Change to: `batch_size=12`
3. No other changes to subprocess logic or timeout

### Success Criteria
- Code change is 1-line only
- Subprocess timeout remains 600s (10 min)
- run_pipeline.py still runs without syntax error

### Test
- Run: `python run_pipeline.py --no-sync` on 30 active issues
- Measure: completion time (should be faster than 5-batch baseline)
- Verify: all 30 issues complete successfully (30 succeeded, 0 failed)
- If any failures: revert batch_size to 5, ask architect

---

## Phase 2: Caching Strategy (Jira Summary + Investigations)

**Files:** `app.py`, `templates/index.html`

### Investigation: Current Caching State
1. Read `app.py` lines 1-50 (imports, global state)
2. Check: is there already a caching layer? (likely yes from recent work)
3. Document: what's cached, what isn't

### Implementation: Jira Summary Cache
**File:** `app.py`, endpoint `/api/jira-summary/<key>`

- Add global dict: `jira_summary_cache = {}`
- Modify endpoint to check cache before reading disk
- Cache key format: `{key}` (issue key)
- TTL: none (cache for session lifetime)
- Size limit: keep only last 100 keys (LRU evict oldest)

### Implementation: Investigation Cache
**File:** `app.py`, endpoint `/api/issues` (returns issues with investigation status)

- Add global dict: `investigation_cache = {}`
- When returning issue flags, check if investigation file exists
- Store in cache: `{key: {"has_investigation": bool, "has_solution": bool}}`
- Invalidate cache when pipeline completes (clear on `/api/pipeline-complete` or similar)

### Success Criteria
- Caching dicts defined at module scope
- No database/Redis (memory only, session-local)
- Cache lookup happens before disk I/O
- Size limit prevents unbounded growth
- Code compiles without error

### Test
1. Load GUI
2. Select issue HEAL-33618
3. Switch to HEAL-33619, then back to HEAL-33618
4. Verify second load of HEAL-33618 is instant (served from cache)
5. Browser DevTools → Network tab: second request should be < 50ms

---

## Phase 3: Nightly Pre-Computation (Investigation Record Generation)

**File:** `run_pipeline.py` (extend with new function)

### Implementation: Batch Pre-Compute Function
Add function `run_nightly_precompute()`:

```python
def run_nightly_precompute():
    """Generate investigation records for all active issues (Steps 1-7 only, no Step 8 agent)."""
    # Load active issues from outputs/active-issues.txt (or scan jira/summary/)
    # For each issue:
    #   - Run Steps 1-5 (sync, triage, scaffold, soql, verification)
    #   - Skip Step 8 (agent) — investigations created as empty template
    #   - Write investigation record to outputs/investigations/<KEY>.md
    # Log: "Nightly pre-compute: generated N investigations in T seconds"
    return completed_count, failed_count
```

### Success Criteria
- Function can be called standalone (not part of --no-sync pipeline)
- Generates investigations for all active issues without running Step 8
- Writes to outputs/investigations/ (same as normal pipeline)
- Logs completion time and count

### Test
1. Call function directly: `python -c "from run_pipeline import run_nightly_precompute; run_nightly_precompute()"`
2. Verify: all 30 issues have investigation files in `outputs/investigations/`
3. Verify: investigations are templates (no agent-filled content yet)
4. Measure: time taken (should be < 5 min for 30 issues)

---

## Phase 4: Confidence Flags (Detect Low-Effort Responses)

**File:** `step8_agent.py`

### Implementation: Token Count Check
After step8_agent writes investigation, internal notes, jira message:

1. Check investigation_text token count (rough: len(text) / 4)
2. If < 300 tokens: write flag file `outputs/confidence-flags/{KEY}.low`
3. If >= 300 tokens: write flag file `outputs/confidence-flags/{KEY}.high`

### Implementation: GUI Display
**File:** `app.py`, `templates/index.html`

1. New endpoint: `/api/issue/<key>/confidence-flag`
   - Returns: `{"confidence": "high"|"low", "investigation_tokens": N}`
2. GUI: Show badge next to issue name if `confidence == "low"`
   - Badge: "⚠ Low Confidence" (yellow)
   - On click: show investigation quality warning

### Success Criteria
- Flag files written to `outputs/confidence-flags/` after Step 8
- Flag format: {key}.low or {key}.high
- Endpoint returns confidence status
- GUI displays badge for low-confidence issues
- No auto-correction or re-runs (just flagging)

### Test
1. Run step8 on a few issues
2. Check: confidence-flags files created
3. Load GUI, select low-confidence issue → verify badge shows
4. Click badge → verify warning message displays

---

## Smoke Test (Final Validation)

**Goal:** Verify all 4 phases work together without breaking existing functionality

### Test Sequence
1. **Batch size:** Run `python run_pipeline.py --no-sync`
   - All 30 issues complete
   - No increase in errors vs baseline
   - Completion time is faster

2. **Caching:** Load GUI, switch between issues 5 times
   - No errors in browser console
   - Second+ loads are visibly faster
   - Cache dicts not growing indefinitely

3. **Pre-compute:** Call nightly function
   - Generates investigations for all issues
   - No errors, completes in < 5 min

4. **Confidence:** Run step8 on HEAL-33618
   - Confidence flag file created
   - GUI shows badge if low confidence
   - No crashes

### Acceptance Criteria
- **Batch size:** 30/30 issues complete, < 20 min elapsed
- **Caching:** no errors, second page load < 100ms
- **Pre-compute:** all 30 investigations exist, generated in < 5 min
- **Confidence:** flag file exists, GUI displays badge correctly
- **Overall:** no regressions in existing features (issue list, detail view, pipeline log)

### Rollback Plan
If any phase fails:
1. Revert the file changes (git checkout <file>)
2. Restart app server
3. Document failure reason
4. Ask architect: "Should we skip this phase or fix it?"

---

## Architect Decision Points

If uncertain, ask: **"What would Sean prioritize—speed or simplicity here?"**

### Known Decisions
- Batch size: prioritize throughput over latency (12 chosen for safety)
- Caching: session-local memory only (no Redis complexity)
- Pre-compute: Skip Step 8 (keep agent out of nightly job)
- Confidence: flagging only (no auto-correction, no re-runs)

### If You Encounter
- **"Should we cache API responses?"** → No. Cache disk I/O only (jira summary, investigation files).
- **"What if cache grows too large?"** → LRU evict (keep last 100 keys).
- **"Should pre-compute run Step 8?"** → No. Step 8 runs on-demand only (in GUI).
- **"Should low-confidence trigger a re-run?"** → No. Just flag. Human reviews.

---

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| `run_pipeline.py` | Batch size 5→12 | ~line with `batch_size=` |
| `run_pipeline.py` | Add `run_nightly_precompute()` function | New function |
| `app.py` | Add jira_summary_cache dict | Top of file, module scope |
| `app.py` | Add investigation_cache dict | Top of file, module scope |
| `app.py` | Modify `/api/jira-summary/<key>` to use cache | ~line 1000+ |
| `app.py` | Add `/api/issue/<key>/confidence-flag` endpoint | New endpoint |
| `step8_agent.py` | Add confidence flag writing after line 255 | After file writes |
| `templates/index.html` | Load confidence flag, display badge | In issue detail section |

---

## Success Looks Like

After completion:
- [ ] Batch size changed (1 line)
- [ ] Caching layer working (instant second page load)
- [ ] Nightly function callable and generates investigations
- [ ] Confidence flags visible in GUI
- [ ] All 30 issues process in single pipeline run
- [ ] No regressions in existing features
- [ ] Git diff shows 4 focused changes (no scope creep)

---

## Notes for Subagent

- Read this plan before each phase
- Reference plan section number when reporting progress
- Test after each phase (don't batch all phases then test)
- If anything is unclear, ask the architect
- This is dev/test only—do not deploy to production
- No Jira writes, no live data changes
- Commit each phase (4 commits total)
