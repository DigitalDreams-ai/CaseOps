---
name: jira-response-drafting
description: Drafts concise issue briefs, internal implementation notes, Engineering handoff notes when routed, and Jira responses after a Salesforce solution has been validated or escalated. Use when the user needs final notes, status details, handoff text, or text to paste into Jira.
---

# Jira Response Drafting

## Use This Skill When

- The Salesforce solution has been validated in Sandbox.
- The issue has been diagnosed and needs Engineering escalation.
- The user needs internal notes.
- The user needs a concise issue brief.
- The user needs a Jira-ready message.
- The `caseops-pipeline` delegates notes and message drafting as Step 10.

## Three-File Messaging Framework

CaseOps drafts three separate files, each with distinct purpose and voice. Do not combine them.

### Issue brief (neutral summary)
- **Audience:** Operator/reviewer, and Engineering if the issue is routed there
- **Content:** Problem → Reproduce → Expected behavior → Affected record IDs → Proposed Solution
- **Tone:** Concise, Jira-ready, factual
- **Routing:** Informational only. Do not treat this as an Engineering escalation.
- **Formatting:** Plain text only. No Markdown links, `sf://` links, `SB` suffixes, deploy IDs, package paths, repeated facts, or test-result narration.

### Jira message (customer-facing, for portal)
- **Audience:** Issue reporter (for example, a product or support stakeholder)
- **Content:** What you found → what it means for them → next step or question
- **Tone:** Human, direct, no corporate fluff
- **Example:** "The validation rule was blocking that update. I fixed it in our test environment and confirmed it works."

### Internal notes (operator memo)
- **Audience:** Operator/internal reviewer
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

## Writing Style Rules (customer-facing Jira messages)

The message should sound like a thoughtful admin talking to a busy colleague: clear, direct, warm but not chatty, confident but not over-certain. Not a corporate ticket template, not a meeting recap, not a transcript summary.

### Write from the current position, not the investigation history

State what is true now. Do not narrate how you got there or rehash earlier back-and-forth.

Bad:
> After first suspecting a record type issue and then checking the permission sets, it turned out the real cause was the validation rule.

Better:
> The validation rule was blocking that update.

### Sentence rhythm — avoid repetitive LLM patterns

Watch for these sentence starts. One is fine; several in one message is a rewrite:

- "This is not..."
- "That is why..."
- "That does not mean..."
- "It is important to..."
- "The key is..."
- "In practical terms..."

Prefer natural variation: short statement → specific fact → next step or boundary.

Bad:
> This is not a missing feature. It is a permission gap that prevents the button from rendering.

Better:
> The Edit button is hidden because your account doesn't have report editing permissions.

### First person — sparingly

Use "I" when reporting an action or a judgment call ("I fixed it in our test environment"). Drop it when the sentence stands on its own.

Too much:
> I would say the field should now appear on the layout.

Better:
> The field now appears on the layout.

### Names and direct address

Use the reporter's name once at most (greeting). Do not repeat it through the body.

### Words to avoid

Unless the reporter used them first: seamless, robust, leverage, optimize, utilize, stakeholder, unlock, game-changing, transformation, scalable solution, end-to-end, strategic alignment, operational excellence.

> Machine-enforced copy of this list lives in `message_rules.py` (used by the output-quality evals). When editing this list, update that module in the same change.

### Boundary language — firm, not defensive

Bad:
> That doesn't mean your idea for an Opportunity-level field is bad.

Better:
> The Account checkbox covers that automatically, so no Opportunity-level field is needed.

### Revision checklist (before saving the Jira message)

- Does it answer what the reporter actually needs to decide or do next?
- Does it avoid replaying the investigation?
- Are there several "This/That/It is..." sentence starts? Rewrite.
- Is anything oversold or over-certain?
- Could a human admin imagine sending this exact text?

---

## Workflow

1. Read the investigation record and test report.
2. Summarize the root cause.
3. Summarize the fix or Engineering escalation reason.
4. List changed metadata/code, or affected metadata/code for Engineering.
5. Summarize Sandbox testing or read-only validation evidence.
6. Draft `outputs/issue-briefs/<KEY>.md` for every processed issue using the canonical structure in `../caseops-pipeline/assets/issue-brief-template.md`:
   - **Problem**
   - **Reproduce**
   - **Expected behavior**
   - **Affected record IDs**
   - **Proposed Solution**
7. **For Engineering escalations only:** read or create the handoff file at `outputs/engineering-escalations/<KEY>.md` created by the pipeline's escalation gate. Use the canonical structure in `../caseops-pipeline/assets/engineering-handoff-template.md`:
   - **Problem**
   - **Reproduce**
   - **Expected behavior**
   - **Affected record IDs**
   - **Proposed Solution**
8. Draft internal notes and append additional details that emerged, but do not recreate the handoff.
9. **Draft all required files:**
   - `outputs/issue-briefs/<KEY>.md` (neutral issue brief) — every processed issue
   - `outputs/jira-messages/<KEY>.md` (customer message) — apply voice rules checklist
   - `outputs/internal-notes/<KEY>.md` (operator memo) — lean root-cause memo
10. Follow `../caseops-pipeline/references/markdown-output-rules.md` for generated Markdown.

## Production vs Sandbox (mandatory in drafts)

In **internal notes** and the **Jira message**, always separate:

- What was **verified in Production** (read-only).
- What exists **only in Sandbox** after the fix.
- Whether **Production metadata deployment** is required: **Yes — promote via Gearset** (or org standard) / **No — already in Production** / **N/A**.

Never imply Production includes new metadata just because Sandbox validation passed. The operator owns Production promotion unless they explicitly directed otherwise.

## Assets

- `../caseops-pipeline/assets/internal-notes-template.md`: canonical internal notes format.
- `../caseops-pipeline/assets/issue-brief-template.md`: canonical issue brief format.
- `../caseops-pipeline/assets/engineering-handoff-template.md`: canonical Engineering handoff format.
- `../caseops-pipeline/assets/jira-message-template.md`: canonical Jira response format.

## Quality Checks

- Keep the Jira message concise and factual.
- Follow the canonical Markdown output rules.
- Apply the stricter no-link/no-deploy-artifact formatting only to `outputs/issue-briefs/<KEY>.md` and `outputs/engineering-escalations/<KEY>.md`.
- Do not apply the Issue Brief / Engineering Handoff formatting rules to Jira messages or internal notes.
- Do not claim Production deployment unless the operator **explicitly** performed or confirmed it.
- Always separate **Sandbox-validated** work from **Production state**: say **Gearset (or deploy) required** vs **no Production metadata deploy** vs **N/A**.
- Avoid phrasing that sounds like a component “is in Production” when it was only created/deployed in Sandbox.
- Include Sandbox validation details.

### Engineering Handoff Checklist (if escalating)

- ✓ **Problem is specific** — identifies exact component/location and failure point.
- ✓ **Reproduce is numbered and runnable** — includes user role, navigation/action, and observed result.
- ✓ **Expected behavior is clear** — states the behavior Engineering should restore.
- ✓ **Affected record IDs are concrete** — includes examples, report/list-view references, or "None confirmed".
- ✓ **Proposed Solution is actionable** — names the component/element and the change Engineering should make.
- ✓ **No verbose internal sections** — no metadata dumps, confidence scoring, full investigation replay, or pipeline-only notes.
- ✓ **No rendered links or transient artifacts** — no Markdown links, `sf://` links, deploy IDs, confirmed package paths, `SB` suffixes, or local/NAS paths.
- ✓ **Grouped details** — related component names and record IDs use sub-bullets instead of long link-heavy sentences.

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

### Internal Notes Example

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
