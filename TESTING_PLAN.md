# CaseOps End-to-End Testing Plan

**Validate full Steps 1–12 pipeline with a low-risk Jira issue.**

## Test Case: HEAL-33150

**Issue:** Cx Case Record Response  
**Status:** In Progress  
**Risk:** Low (existing investigation already present; can be re-run)  
**Key artifacts:** `outputs/investigations/HEAL-33150.md`, `outputs/jira/summary/HEAL-33150.md`

## Pre-Flight Checklist

- [ ] `.env.jira` exists with valid credentials
- [ ] `CASEOPS_LLM_AUTH=claude_code` is set
- [ ] `CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean` (or your Sandbox org)
- [ ] `claude --version` runs (Claude Code CLI installed)
- [ ] `claude login` succeeded (subscription active)
- [ ] `CASEOPS_PRODUCTION_MAGIC_LINK` and `CASEOPS_SANDBOX_MAGIC_LINK` are set (optional; needed for UI investigation)

## Test Procedure

### Option A: Via GUI Button (Recommended)

1. Start Flask: `python app.py`
2. Open `http://localhost:5000`
3. Find HEAL-33150 in the sidebar
4. Click the issue
5. Click **"Run Pipeline For This Issue"** button
6. Watch live logs in the right panel
7. Verify stages:
   - ✓ Step 1: Sync from Jira (already done; skipped if manifest exists)
   - ✓ Step 2: Triage (route to active list)
   - ✓ Step 3: Sub-agent `jira-issue-analysis` spawned
   - ✓ Step 4: Hypothesis drafted
   - ✓ Step 5: Sub-agent `salesforce-production-metadata-investigation` spawned
   - ✓ Step 6: Sub-agent `salesforce-production-metadata-investigation` (drilling)
   - ✓ Step 7: Escalation gate decision logged
   - ✓ Step 8: Implementation (if Support-resolvable)
   - ✓ Step 9: Sub-agent `salesforce-sandbox-deploy-test` spawned (if Support path)
   - ✓ Step 10: Sub-agent `jira-response-drafting` spawned
   - ✓ Step 11: Dated summary created
   - ✓ Step 12: Report generated

### Option B: Via Claude Code CLI (Direct)

```bash
cd CaseOps
claude -p "Process HEAL-33150 through the full jira-salesforce-fix-pipeline Skill."
```

## Expected Outputs

After full execution, verify files exist:

```
outputs/
├── investigations/HEAL-33150.md                    ← Updated with Steps 3–10 findings
├── step-4-hypothesis/HEAL-33150.md                ← Hypothesis (Support vs Engineering decision)
├── test-reports/HEAL-33150.md                     ← Sandbox test results (if Support path)
├── jira-messages/HEAL-33150.md                    ← Customer-facing message draft
├── internal-notes/HEAL-33150.md                   ← Internal diagnosis + decision
├── engineering-escalations/HEAL-33150.md          ← (if escalated) Engineering handoff
└── issue-summary-YYYY-MM-DD.md                    ← Dated rollup (if Step 11 ran)
```

## Validation Checkpoints

### Step 3 Completion
- File: `outputs/investigations/HEAL-33150.md`
- Expected: "Issue Understanding" section populated with observed/expected behavior
- Command: `grep -A 5 "## Issue Understanding" outputs/investigations/HEAL-33150.md`

### Step 5 Completion
- File: `outputs/investigations/HEAL-33150.md`
- Expected: "Production Metadata Retrieved" section with metadata details
- Command: `grep -A 10 "## Production Metadata" outputs/investigations/HEAL-33150.md`

### Step 6 Completion
- File: `outputs/investigations/HEAL-33150.md`
- Expected: "Problem Location" section with artifact type, name, location, failure point
- Command: `grep -A 10 "## Problem Location" outputs/investigations/HEAL-33150.md`

### Step 7 Decision
- File: `outputs/investigations/HEAL-33150.md` OR `outputs/engineering-escalations/HEAL-33150.md`
- Expected: Escalation decision (Support-resolvable vs Engineering)
- Check: Which file exists determines the path

### Step 10 File Separation
- Files: `outputs/jira-messages/HEAL-33150.md` AND `outputs/internal-notes/HEAL-33150.md`
- Validation:
  - Jira message must NOT contain "[INTERNAL]" section
  - Internal notes must NOT contain customer greeting ("Hi [Name]")
- Commands:
  ```bash
  grep "[INTERNAL]" outputs/jira-messages/HEAL-33150.md && echo "FAIL: Jira message contains [INTERNAL]" || echo "PASS"
  grep -i "hi " outputs/internal-notes/HEAL-33150.md && echo "FAIL: Internal notes have greeting" || echo "PASS"
  ```

### Step 11 Dated Summary
- File: `outputs/issue-summary-YYYY-MM-DD.md`
- Expected: Table with issue, status, disposition, Production deploy status
- Command: `grep "HEAL-33150" outputs/issue-summary-*.md`

## Troubleshooting

### "CASEOPS_SANDBOX_TARGET_ORG not set"
→ Edit `.env.jira`, add: `CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean`

### "claude CLI not found"
→ Install Claude Code: `npm install -g @anthropic-ai/claude-code`  
→ OR: Set `CASEOPS_LLM_AUTH=api_key` + `ANTHROPIC_API_KEY` (but sub-agents will not work)

### "Sub-agent timeout"
→ Issue is too large or context overflowed  
→ Reduce other background tasks, try again  
→ Check Jira summary file size (`outputs/jira/summary/HEAL-33150.md`)

### "Jira message and internal notes are in the same file"
→ **CRITICAL BUG** — Step 10 file separation failed  
→ Re-run Step 10 sub-agent with fresh context  
→ Report issue: Step 10 bulletproof validation (lines 115–199 in sub-agent-prompts.md) is not enforced

### "Test report shows FAIL but Sub-Support path was expected"
→ Sandbox deployment failed  
→ Check Step 9 sub-agent error in logs  
→ Verify Sandbox org is reachable: `sf org display --target-org 10xhealth-sean`  
→ Consider Step 5/6 loop (if more metadata needed) or Step 8 re-implementation

## Success Criteria

✅ All 12 steps execute without error  
✅ No files missing after Step 10  
✅ Jira message and internal notes are in separate files  
✅ Investigation record has all sections (Understanding, Metadata, Problem Location)  
✅ Escalation decision is documented  
✅ Test report exists (if Support-resolvable)  
✅ Dated summary includes HEAL-33150 with correct disposition  

## Notes

- This is a **validation test**, not a **functional test**. It checks that the pipeline architecture works, not that the fix itself is correct.
- If testing with a different issue, pick one with "In Progress" status (active, not closed/escalated).
- The test will post SSE logs in real-time. Check browser console for any JavaScript errors.
- Full execution typically takes 3–8 minutes depending on Jira/Salesforce API latency.

---

**After testing:** If all checkpoints pass, the pipeline is ready for production use.
