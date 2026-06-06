---
name: jira-response-drafting
description: Drafts internal implementation notes, Engineering handoff notes, and concise Jira responses after a Salesforce fix has been validated or escalated. Use when the user needs final notes, status details, handoff text, or text to paste into Jira.
---

# Jira Response Drafting

## Use This Skill When

- The Salesforce fix has been validated in Sandbox.
- The issue has been diagnosed and needs Engineering escalation.
- The user needs internal notes.
- The user needs a Jira-ready message.
- The `jira-salesforce-fix-pipeline` delegates notes and message drafting as Step 9.

## Two-Audience Messaging Framework

Jira drafts contain **two separate sections**, each with distinct purpose and voice:

### Suggested reply (customer-facing, for portal)
- **Audience:** Issue reporter (for example, a product or support stakeholder)
- **Content:** What you found → what it means for them → next step or question
- **Tone:** Human, direct, no corporate fluff
- **Example:** "The validation rule was blocking that update. I fixed it in our test environment and confirmed it works."

### [INTERNAL] (operator internal memo, Jira comment only)
- **Audience:** Operator/internal reviewer (internal Jira memo, not posted to customer)
- **Content:** What it's NOT → where the gap is → why the symptom happens → action needed
- **Length:** Keep short; full investigation evidence stays in Investigation tab
- **Example:** "NOT a missing field. The validation rule conditions were outdated — didn't account for the new status value. Fixed by adding the new status to the rule condition. Engineering will review."

---

## Voice Rules for Suggested Reply (mandatory)

Every customer-facing draft must pass **all** of these:

- ✓ **No em dash** (—) or hyphen as clause punctuation
- ✓ **Brief** (summarize, don't replay the investigation)
- ✓ **Casual tone** (short sentences, no corporate voice)
- ✓ **Specific thanks** (if reporter gave good repro steps, screenshots, or clear description — thank them for *what* they provided, not generic "appreciate you")
- ✓ **No bullets** unless they asked for steps (prefer sentences)
- ✓ **No internal IDs, file paths, or heavy jargon** unless reporter asked for details
- ✓ **No "we," "we've," "we're," "us," "let us"** — use you/I/neutral facts

**If any fails:** rewrite and re-check the entire draft.

---

## Workflow

1. Read the investigation record and test report.
2. Summarize the root cause.
3. Summarize the fix or Engineering escalation reason.
4. List changed metadata/code, or affected metadata/code for Engineering.
5. Summarize Sandbox testing or read-only validation evidence.
6. **For Engineering escalations:** read the handoff file at `outputs/engineering-escalations/<KEY>.md` created by the pipeline's escalation gate. Use the structure in `assets/engineering-handoff-template.md`:
   - **Summary & Description** (with root cause)
   - **Reproduction Steps** (with examples)
   - **Expected vs. Actual Results** (with evidence)
   - **Proposed Fix**
   - **Environment/Version Details**
   - **Attachments** (logs, screenshots, debug output)
   - **Open Questions** (clarifications needed for Engineering)
   - **Investigation Summary** (recap of findings and validation)
7. Draft internal notes and append additional details that emerged, but do not recreate the handoff.
8. **Draft both sections:**
   - **Suggested reply** (customer message) — apply voice rules checklist
   - **[INTERNAL]** (operator memo) — lean root-cause memo

## Production vs Sandbox (mandatory in drafts)

In **internal notes** and the **Jira message**, always separate:

- What was **verified in Production** (read-only).
- What exists **only in Sandbox** after the fix.
- Whether **Production metadata deployment** is required: **Yes — promote via Gearset** (or org standard) / **No — already in Production** / **N/A**.

Never imply Production includes new metadata just because Sandbox validation passed. The operator owns Production promotion unless they explicitly directed otherwise.

## Assets

- `assets/internal-notes-template.md`: Internal notes format.
- `assets/engineering-handoff-template.md`: Engineering handoff format.
- `assets/jira-message-template.md`: Jira response format.

## Quality Checks

- Keep the Jira message concise and factual.
- Do not claim Production deployment unless the operator **explicitly** performed or confirmed it.
- Always separate **Sandbox-validated** work from **Production state**: say **Gearset (or deploy) required** vs **no Production metadata deploy** vs **N/A**.
- Avoid phrasing that sounds like a component “is in Production” when it was only created/deployed in Sandbox.
- Include Sandbox validation details.

### Engineering Handoff Checklist (if escalating)

- ✓ **Summary includes clear root cause** — avoid vague language; be specific about the underlying problem
- ✓ **Reproduction steps are numbered and complete** — include examples that reliably reproduce the issue
- ✓ **Expected vs. Actual clearly separated** — with supporting evidence (logs, screenshots, error messages)
- ✓ **Proposed Fix includes implementation details** — specific components/files affected, estimated effort
- ✓ **Environment details filled in** — version, relevant objects, production vs sandbox state
- ✓ **Attachments documented** — logs, screenshots, configuration files noted or attached
- ✓ **Open Questions listed** — clarifications needed from Engineering or product
- ✓ **Investigation Summary provided** — recap of findings and any Sandbox validation done

- The handoff file is created by the pipeline escalation gate, not this skill. Append details if new information emerged during drafting, but do not recreate it.
- Include any remaining risks or follow-up.

## Examples: Good vs Bad Voice

### ❌ BAD (violates voice rules)

```
We investigated the issue and found that the validation rule was blocking the update. 
We've made changes in Sandbox — we recommend deploying via Gearset to Production.
Thanks for reporting.
```

**Violations:**
- "we investigated" ✗ (uses "we")
- "we've made" ✗ (uses "we've")
- "we recommend" ✗ (uses "we")
- No specific thanks (generic "thanks for reporting")
- No next step or question for reporter

---

### ✓ GOOD (passes all checks)

```
The validation rule was blocking that update. I fixed it in our test environment and confirmed it works.

Production doesn't have the fix yet. Your team will need to promote it via Gearset. I can send deployment details if you need them.

The steps you provided made it easy to spot. Thanks for that clarity.
```

**Passes all checks:**
- ✓ No em dashes, no hyphens as punctuation
- ✓ Brief (four sentences, one action)
- ✓ Casual tone ("made it easy to spot")
- ✓ Specific thanks ("The steps you provided made it easy to spot")
- ✓ No bullets, no internal IDs, no jargon
- ✓ No "we"; uses passive voice + you/I
- ✓ Clear next step (Gearset, I can help)

---

### [INTERNAL] Example

```
NOT a missing field. The validation rule conditions were outdated — didn't account for the new status value. Fixed by adding the new status to the rule condition.

Why: Status field has 3 new values as of Q2 but the validation rule hardcoded only the old 2 values, so any record with the new status triggered the block.

Action: Monitor Sandbox fix for 24h in pre-prod. Then Gearset promotion to Production (no code, just rule update).
```

**Structure:**
- Negation (what it's NOT)
- Root cause (why it happened)
- Fix (what changed)
- Action (what the operator does next)
