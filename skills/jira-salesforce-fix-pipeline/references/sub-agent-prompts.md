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
Problem hypothesis: <paste from outputs/step-4-hypothesis/<KEY>.md OR inline notes from Step 4>
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
Problem hypothesis: <paste from outputs/step-4-hypothesis/<KEY>.md OR inline notes from Step 4>
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

**CRITICAL: This is the bulletproof Step 10 rewrite (v2) with mandatory file separation and validation checkpoints.**

See also: `references/orchestration-loop-controller.md` for orchestrator-level Step 10 file validation that runs after this sub-agent completes.

```
CONTEXT:
Issue key: <KEY>
Root cause: <from Step 4>
Fix or escalation: <Support fix description from Step 8, or "Escalated to Engineering">
Test result: <from Step 9 summary>
Investigation record: outputs/investigations/<KEY>.md

═══════════════════════════════════════════════════════════════════════
TASK: Draft and save TWO completely separate documents for TWO audiences
═══════════════════════════════════════════════════════════════════════

⚠️  FATAL IF COMBINED: If both documents are in one file, customer sees internal diagnosis. This is a STOP rule.

════════════════════════════════════════════════════════════════════════
STEP A: DRAFT DOCUMENT 1 (Jira Message — Customer-Facing Only)
════════════════════════════════════════════════════════════════════════

AUDIENCE: Issue reporter + stakeholders (public Jira comment)
TEMPLATE: jira-message-template.md
OUTPUT FILE: outputs/jira-messages/<KEY>.md

CONTENT RULES:
- Greeting: "Hi [Reporter name],"
- Problem: What you found, in customer-friendly language (no internal jargon)
- Root cause: Why it's broken, explained for non-technical stakeholder
- Solution OR escalation: What happens next
- Production vs Sandbox (if resolved): What was tested, what's the deploy plan
- Closing: Thank them for what they provided (steps? screenshots? detail?)

FORBIDDEN IN THIS FILE (hard stop if present):
✗ [INTERNAL] section
✗ ## [INTERNAL] header
✗ Metadata names or change lists
✗ Engineering-specific terminology (thread ID, trigger, handler, etc.)
✗ Test case descriptions
✗ "Sean" or any internal name
✗ References to Gearset or Sandbox-only work
✗ Root cause analysis intended for diagnosis only
✗ Internal diagnosis details or investigation notes

VALIDATION BEFORE SAVING:
1. Read the draft you created
2. Search for EVERY keyword above and DELETE if found
3. If any [INTERNAL] section exists, DELETE it entirely
4. Confirm: would a customer-facing reader understand this without Salesforce admin knowledge?
5. Only after validation, save to outputs/jira-messages/<KEY>.md

════════════════════════════════════════════════════════════════════════
STEP B: SAVE DOCUMENT 1 TO DISK
════════════════════════════════════════════════════════════════════════

File: outputs/jira-messages/<KEY>.md
Content: ONLY the customer-facing draft from Step A
Do NOT save Document 2 content here
Do NOT include headers, separators, or sections from Document 2
Do NOT reuse any content when drafting Document 2 (start fresh)

CHECKPOINT: Is outputs/jira-messages/<KEY>.md now saved and contains ZERO internal keywords? YES or STOP.

════════════════════════════════════════════════════════════════════════
STEP C: DRAFT DOCUMENT 2 (Internal Notes — Internal Diagnosis Only)
════════════════════════════════════════════════════════════════════════

AUDIENCE: Sean only (internal reference, NOT posted to Jira)
TEMPLATE: internal-notes-template.md
OUTPUT FILE: outputs/internal-notes/<KEY>.md

CONTENT RULES:
- Root cause: Full technical diagnosis (internal detail OK here)
- Decision: Support-resolved OR Escalate to Engineering
- Actions: What was done, what needs doing
- Production vs Sandbox state: Explicit inventory of what exists where
- Risks: Technical or operational risks
- Escalation details: If Engineering, what's being handed off

FORBIDDEN IN THIS FILE (hard stop if present):
✗ Customer greeting (no "Hi [Name],")
✗ "Thanks" or "Thanks for" phrases
✗ Suggested reply or Jira comment tone
✗ "We will..." or "We recommend..." (customer voice)
✗ Any content that would go in a Jira comment

VALIDATION BEFORE SAVING:
1. Read the draft you created
2. Confirm it has root cause diagnosis, decision, actions, state, risks
3. Confirm ZERO customer-facing greeting or tone
4. Only after validation, save to outputs/internal-notes/<KEY>.md

════════════════════════════════════════════════════════════════════════
STEP D: SAVE DOCUMENT 2 TO DISK
════════════════════════════════════════════════════════════════════════

File: outputs/internal-notes/<KEY>.md
Content: ONLY the internal diagnosis draft from Step C
Do NOT save Document 1 content here
Do NOT reuse customer-facing greeting or tone

════════════════════════════════════════════════════════════════════════
FINAL CHECKPOINT (MANDATORY)
════════════════════════════════════════════════════════════════════════

After saving both files, verify:
1. outputs/jira-messages/<KEY>.md EXISTS and contains customer-facing message only
2. outputs/jira-messages/<KEY>.md contains ZERO [INTERNAL] sections
3. outputs/jira-messages/<KEY>.md contains ZERO internal diagnosis keywords
4. outputs/internal-notes/<KEY>.md EXISTS and contains root cause diagnosis
5. outputs/internal-notes/<KEY>.md does NOT contain "Hi [Name]," greeting

If any checkpoint fails, STOP and fix before returning.

════════════════════════════════════════════════════════════════════════

Return summary (max 300 tokens):
- Outcome (fixed/escalated)
- DOCUMENT 1 summary (jira-message file, customer-facing tone check)
- DOCUMENT 2 summary (internal-notes file, decision and action summary)
- Production deploy? (Gearset / No / N/A)
- Paths: outputs/jira-messages/<KEY>.md | outputs/internal-notes/<KEY>.md
```
