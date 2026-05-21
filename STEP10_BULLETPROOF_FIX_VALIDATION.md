# Step 10 Bulletproof Fix — Validation Status

**Date:** 2026-05-20  
**Fix:** Step 10 sub-agent prompt completely rewritten for mandatory file separation with validation checkpoints  
**File:** `skills/jira-salesforce-fix-pipeline/references/sub-agent-prompts.md`

## The Problem (Pre-Fix)

Two issues generated jira-messages with mixed content:
- **HEAL-33150**: jira-messages contains "## Suggested Reply" + "## [INTERNAL]" sections
- **HEAL-33633**: jira-messages contains "## Suggested reply" + "## [INTERNAL]" sections

24 other issues have internal-notes but NO jira-messages files (Step 10 not yet applied or failed silently).

## The Fix Applied

**Rewrote Step 10 prompt to enforce physical file separation:**

1. **Step A**: Draft customer-facing message only
   - Validation checkpoint: Search for forbidden keywords, DELETE if found
   - Explicit list: [INTERNAL], metadata names, engineering terminology, test cases, etc.

2. **Step B**: Save DOCUMENT 1 to disk
   - Checkpoint: "Is file saved and contains ZERO internal keywords? YES or STOP."

3. **Step C**: Draft internal notes (start completely fresh, no reference to Document 1)
   - Validation checkpoint: Zero customer-facing tone

4. **Step D**: Save DOCUMENT 2 to disk

5. **Final Checkpoint**: Verify both files exist and are properly separated

## Validation Plan

### Before Batch Processing
1. Run `/jira-salesforce-fix-pipeline` on ONE issue (HEAL-33098 or HEAL-33316)
2. Check outputs/jira-messages/<KEY>.md:
   - ZERO [INTERNAL] sections
   - ZERO internal diagnosis keywords
   - Customer-facing tone only
3. Check outputs/internal-notes/<KEY>.md:
   - Root cause diagnosis present
   - ZERO customer greeting "Hi [Name],"
4. If both pass → clear to batch process remaining issues
5. If either fails → investigate why sub-agent still mixing and adjust prompt

### Expected Outcome
- jira-messages files contain customer-facing message only
- internal-notes files contain internal diagnosis only
- No mixing between files

## Status

✓ **Prompt Updated**: Step 10 now has mandatory validation checkpoints and forbidden keyword enforcement  
⏳ **Pending Validation**: One issue must be processed through full pipeline to confirm file separation works  
⚠️ **Known Issues to Fix Post-Validation**:
- 24 issues have internal-notes but missing jira-messages (need Step 10 applied)
- Incomplete investigations on HEAL-33098, HEAL-33399, HEAL-33616, etc. (need investigation completion before Step 10)

## Next Steps

1. **Immediate**: Run `/jira-salesforce-fix-pipeline` on a fresh issue (HEAL-33316 or similar)
2. **Validate**: Check that new bulletproof prompt produces separated files
3. **Batch Process**: If validation passes, process all active issues
4. **Cleanup**: Re-run Step 10 on HEAL-33150 and HEAL-33633 to fix their mixed files
