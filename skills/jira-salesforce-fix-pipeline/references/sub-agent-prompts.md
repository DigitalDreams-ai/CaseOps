# Sub-agent prompt templates

Copy the block for the active step into the Agent tool. Replace placeholders (`<KEY>`, pasted hypotheses, etc.) with real values. Each prompt must stay **fully self-contained** (the sub-agent has no orchestrator context).

## Step 3 — Analyze the issue

```
You are analyzing a Jira issue for Salesforce implementation work.

Issue key: <KEY>
Jira summary file: outputs/jira/summary/<KEY>.md

Instructions:
1. Use the jira-issue-analysis skill.
2. Read outputs/jira/summary/<KEY>.md as your primary input.
3. Write the Issue Understanding section of outputs/investigations/<KEY>.md
   using skills/jira-salesforce-fix-pipeline/assets/investigation-record-template.md.

Return a compact summary (max 400 tokens) containing:
- Observed behavior
- Expected behavior
- Acceptance criteria
- Affected Salesforce area (object, field, flow, permission, etc.)
- Top unknowns or missing information
- Path written: outputs/investigations/<KEY>.md
```

## Step 5 — Retrieve relevant Production metadata

```
You are retrieving Salesforce Production metadata for a Jira issue.

Issue key: <KEY>
Problem hypothesis: <paste the hypothesis from Step 4>
Investigation record: outputs/investigations/<KEY>.md

Instructions:
1. Use the salesforce-production-metadata-investigation skill.
2. Retrieve only metadata directly relevant to the hypothesis. Do not modify Production.
3. Append your findings to the Production Metadata Retrieved section of
   outputs/investigations/<KEY>.md.
4. If additional metadata is discovered to be needed (e.g., during drilling in Step 6), 
   Step 6 will loop back to you with a refined request.

Return a compact summary (max 400 tokens) containing:
- Metadata items retrieved and why
- Key findings per item
- Whether each item confirms or rejects the hypothesis
- Recommended implementation surface (what to change and where)
- Path written: outputs/investigations/<KEY>.md
```

## Step 6 — Identify problem location

```
You are drilling down to identify the exact problem location in Salesforce Production.

Issue key: <KEY>
Problem hypothesis: <paste hypothesis from Step 4>
Production metadata: <paste the Summary from Step 5>
Investigation record: outputs/investigations/<KEY>.md

Instructions:
1. Use the salesforce-production-metadata-investigation skill (drilling mode).
2. From the Step 5 metadata, drill down to identify:
   - **Problem type**: data / component / config / integration / access / setting / process
   - **Specific artifact**: exact name, API name, class name, field name (from Production)
   - **Location**: Production path (Setup > Object > Field, or code path, or org setting)
   - **Failure point**: where in the flow it breaks (at read, at mapping, at validation, at API call, etc.)
3. Add Problem Location section to outputs/investigations/<KEY>.md.
4. If additional metadata is needed to complete drilling (e.g., "Found Flow reference, need Flow definition"),
   return request for Step 5 with specific metadata needed. Include the label "REQUEST: Step 5 refinement".

Return a compact summary (max 400 tokens) containing:
- Problem type identified
- Specific artifact name + location in Production
- Failure point in the flow
- Root cause identified (why this artifact is broken)
- If more metadata needed: "REQUEST: Step 5 refinement — need [specific metadata]"
- Path written: outputs/investigations/<KEY>.md
```

## Step 9 — Deploy, test, and iterate

**Before spawning:** Read **`CASEOPS_SANDBOX_TARGET_ORG`** from `.env.jira`. If missing or empty, **STOP** and tell the operator to set it. Pass that exact string into the prompt below. Only that org may receive deploys or writes.

```
You are deploying and testing a Salesforce fix in Sandbox.

Issue key: <KEY>
Allowlisted Sandbox (from .env.jira CASEOPS_SANDBOX_TARGET_ORG): <paste exact value read from .env.jira>
Fix description: <paste the solution from Step 8>
Investigation record: outputs/investigations/<KEY>.md

Instructions:
1. Use the salesforce-sandbox-deploy-test skill (mandatory allowlist rules).
2. Confirm the CLI/UI org target matches the allowlisted value exactly before any deploy or write.
3. Deploy the fix, test against the Jira acceptance criteria.
4. Write results to outputs/test-reports/<KEY>.md using
   skills/jira-salesforce-fix-pipeline/assets/test-report-template.md.
   Fill **Production deployment state** (Sandbox vs Production; Gearset required Y/N/N/A).

Return a compact summary (max 400 tokens) containing:
- Pass or Fail
- Steps tested and actual results
- Whether the issue is confirmed fixed
- If failed: what broke, what hypothesis was wrong, what to try next
- Path written: outputs/test-reports/<KEY>.md
```

If the sub-agent returns **Fail:** update the hypothesis in Step 4, spawn a new Step 5 sub-agent if more metadata is needed (and Step 6 if drilling refinement needed), re-implement in Step 8, spawn a new Step 9 sub-agent. Record each failed iteration in `outputs/investigations/<KEY>.md`.

## Step 10 — Draft internal notes and Jira message

```
You are drafting internal notes and a Jira message for a completed Salesforce issue.

Issue key: <KEY>
Root cause: <from Step 4>
Fix or escalation: <Support fix description from Step 8, or "Escalated to Engineering">
Test result: <from Step 9 summary — mandatory for Support path; use "N/A - Engineering escalation" only when Step 7 escalated>
Investigation record: outputs/investigations/<KEY>.md
Test report: outputs/test-reports/<KEY>.md (if exists)
Engineering handoff: outputs/engineering-escalations/<KEY>.md (if escalated)

## Two-Audience Framework (MANDATORY)

Draft BOTH sections — don't combine them:

### ## Suggested reply (customer-facing message)
- Audience: The issue reporter
- Content: What you found → what it means for them → next step or question
- Must pass ALL voice rules (see below)

### ## [INTERNAL] (Sean's internal memo for Jira comment)
- Audience: Sean only (internal comment, not posted to customer)
- Content: What it's NOT → where the gap is → why symptom happens → action needed
- Keep short; full evidence stays in Investigation tab

## Voice Rules for Suggested Reply (all must pass)

- ✓ No em dash (—) or hyphen as clause punctuation
- ✓ Brief (summarize, don't replay investigation)
- ✓ Casual tone (short sentences, no corporate voice)
- ✓ Specific thanks (thank for *what* they provided: steps, screenshots, clear description)
- ✓ No bullets unless they asked for steps (prefer sentences)
- ✓ No internal IDs, file paths, or heavy jargon unless they asked
- ✓ No "we," "we've," "we're," "us," "let us" (use you/I/neutral facts)

If any fails: rewrite and re-check the entire draft.

## Instructions

1. Use the jira-response-drafting skill (read for two-audience framework details and examples).
2. Draft **Suggested reply** first — apply voice checklist, pass all rules.
3. Draft **[INTERNAL]** second — lean root-cause memo.
4. Fill **Production vs deployment** in both: never imply Production has Sandbox-only metadata; state **Gearset/deploy required** vs **already in Production** vs **N/A**.
5. Write internal notes to outputs/internal-notes/<KEY>.md.
6. Write Jira message draft to outputs/jira-messages/<KEY>.md.

Return a compact summary (max 300 tokens) containing:
- Outcome (fixed/escalated)
- Suggested reply summary (one sentence showing it passes voice rules)
- [INTERNAL] summary (one sentence showing structure: what NOT → gap → why → action)
- Production deploy? (Gearset / No / N/A)
- Paths written: outputs/internal-notes/<KEY>.md, outputs/jira-messages/<KEY>.md
```
