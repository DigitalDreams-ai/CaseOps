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
Selected org knowledge: <paste only the relevant bullets from the run's Org Knowledge Context; do not paste unrelated org-knowledge files>

CRITICAL: Metadata Workspace Contract
- Retrieve Production metadata to: ${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/ (read-only)
- All `sf project retrieve` commands MUST include an issue-scoped output dir, for example:
  --output-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
- Do not write to root-level temp/retrieve/deploy/metadata directories.
- Do not edit files under ${CASEOPS_METADATA_RAW_PROD_DIR}; copy only the needed files into a Sandbox attempt directory before changing them.

Instructions:
1. Use the salesforce-production-metadata-investigation skill.
2. Retrieve only metadata directly relevant to the hypothesis. Do not modify Production.
3. Pass the issue-scoped raw Production metadata directory to all retrieve commands (see CRITICAL section above).
4. Append your findings to the Production Metadata Retrieved section of
   outputs/investigations/<KEY>.md.
5. If additional metadata is discovered to be needed (e.g., during drilling in Step 6), 
   Step 6 will loop back to you with a refined request.
6. Use selected org knowledge first. If a known query/retrieve pattern fails twice, stop and replan instead of trying many variants.
7. Do not print raw access tokens or use `SF_TEMP_SHOW_SECRETS=true sf org display`.

Return a compact summary (max 400 tokens) containing:
- Metadata items retrieved and why
- Key findings per item
- Whether each item confirms or rejects the hypothesis
- Recommended implementation surface (what to change and where)
- Raw metadata directory used: ${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>
- Path written: outputs/investigations/<KEY>.md
```

## Step 6 — Identify problem location

```
You are drilling down to identify the exact problem location in Salesforce Production.

Issue key: <KEY>
Problem hypothesis: <paste from outputs/step-4-hypothesis/<KEY>.md OR inline notes from Step 4>
Production metadata: <paste the Summary from Step 5>
Investigation record: outputs/investigations/<KEY>.md
Selected org knowledge: <paste only relevant bullets from the run's Org Knowledge Context>

CRITICAL: Metadata Workspace Contract
- Read Step 5 Production metadata from: ${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/ (read-only)
- If additional metadata retrieval is needed, pass an issue-scoped output dir to Step 5, for example:
  --output-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"
- Do not edit raw Production metadata. Candidate changes belong under ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/candidate/.

Instructions:
1. Use the salesforce-production-metadata-investigation skill (drilling mode).
2. From the Step 5 metadata (stored in the issue-scoped raw metadata directory), drill down to identify:
   - **Problem type**: data / component / config / integration / access / setting / process
   - **Specific artifact**: exact name, API name, class name, field name (from Production)
   - **Location**: Production path (Setup > Object > Field, or code path, or org setting)
   - **Failure point**: where in the flow it breaks (at read, at mapping, at validation, at API call, etc.)
3. Add Problem Location section to outputs/investigations/<KEY>.md.
4. If additional metadata is needed to complete drilling (e.g., "Found Flow reference, need Flow definition"),
   return request for Step 5 with specific metadata needed. Include the label "REQUEST: Step 5 refinement".
5. Use selected org knowledge first and avoid re-running failed query patterns already known to be unreliable.

Return a compact summary (max 400 tokens) containing:
- Problem type identified
- Specific artifact name + location in Production
- Failure point in the flow
- Root cause identified (why this artifact is broken)
- If more metadata needed: "REQUEST: Step 5 refinement — need [specific metadata]"
- Raw metadata directory: ${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>
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
Selected org knowledge: <paste only relevant deploy/query bullets from the run's Org Knowledge Context>

CRITICAL: Sandbox Attempt Workspace and Revert Contract
- Use one directory per solution attempt: ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-001/, attempt-002/, etc.
- Before any Sandbox deploy, retrieve the current Sandbox baseline for every component you will change into:
  ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/baseline-sandbox/
- Put candidate metadata to deploy in:
  ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/candidate/
- Put rollback metadata or destructive changes in:
  ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/revert/
- If an attempt fails or is not viable, revert the Sandbox to the captured baseline before starting another attempt, then verify by retrieve/diff.
- When an attempt passes, copy the final package to:
  ${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/support-owned/ or ${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/engineering-proposal/
- Maintain ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/metadata-workspace.json with attempt number, components touched, baseline path, candidate path, revert status, and confirmed package path when applicable.
- Do not write to root-level temp/retrieve/deploy/metadata directories.

Instructions:
1. Use the salesforce-sandbox-deploy-test skill (mandatory allowlist rules).
2. Confirm the CLI/UI org target matches the allowlisted value exactly before any deploy or write.
3. Use the issue-scoped attempt directory (see CRITICAL section above).
4. Deploy the fix, test against the Jira acceptance criteria.
5. If the fix fails or is abandoned, revert Sandbox changes from the attempt baseline before returning Fail.
6. Write results to outputs/test-reports/<KEY>.md using
   skills/jira-salesforce-fix-pipeline/assets/test-report-template.md.
   Fill **Production deployment state** (Sandbox vs Production; Gearset required Y/N/N/A).
7. Use selected org knowledge first. Prefer deterministic MDAPI deploy patterns for metadata types where source tracking is known to cause `NothingToDeploy`.
8. Never print raw Salesforce access tokens. Do not use `SF_TEMP_SHOW_SECRETS=true sf org display`; use `sf` commands or JSON outputs that do not reveal secrets.

Return a compact summary (max 400 tokens) containing:
- Pass or Fail
- Steps tested and actual results
- Whether the issue is confirmed fixed
- If failed: what broke, what hypothesis was wrong, what was reverted, what to try next
- Attempt directory: ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N
- Confirmed package directory, if passed: ${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/<support-owned|engineering-proposal>
- Workspace manifest: ${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/metadata-workspace.json
- Path written: outputs/test-reports/<KEY>.md
```

If the sub-agent returns **Fail:** confirm the failed attempt was reverted in Sandbox, update the hypothesis in Step 4, spawn a new Step 5 sub-agent if more metadata is needed (and Step 6 if drilling refinement needed), re-implement in Step 8, spawn a new Step 9 sub-agent using the next attempt number. Record each failed iteration in `outputs/investigations/<KEY>.md`.

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

VOICE RULES (mandatory — all must pass validation):
✓ Human, direct tone. No corporate fluff or LLM patterns.
✓ Short sentences. Avoid em dashes (—) and hyphens as clause punctuation.
✓ NO "we," "we've," "we're," "us," "let us." Use you/I/neutral facts instead.
✓ Avoid bullets unless reporter asked for steps. Prefer short paragraphs.
✓ Specific, concrete thanks when reporter provided good repro, screenshots, or detail.
✓ No Salesforce IDs, file paths, or admin jargon unless they asked.

VOICE EXAMPLES:
✗ "We're excited to share the fix with you and we've tested it in Sandbox."
✓ "I found the issue and tested the fix in Sandbox."
✗ "Great news — everything is now working correctly — you should see this in Production."
✓ "I've confirmed the fix works. You'll see this in Production by end of week."

SALESFORCE ARTIFACT LINKING (mandatory):
When mentioning any Salesforce artifact (Permission Set, Flow, Field, Object, Profile, Class, etc.),
resolve the artifact to a Salesforce 15/18-character Id and linkify that Id. The GUI only converts
real Salesforce Ids, not API-name pseudo links.

FORMAT: [artifact_type: artifact_name](sf://salesforce_id)

EXAMPLES:
- [Flow: Case_Assign_RoundRobin](sf://300000000000000AAA)
- [Flow active version: Case_Assign_RoundRobin v8](sf://301000000000000AAA)
- [Permission Set: Lab_Providers_C_R_E](sf://0PS000000000000AAA)
- [User: Jane Example](sf://005000000000000AAA)
- [Field: Account.Industry__c](sf://00N000000000000AAA)
- [Email Template: Follow Up](sf://00X000000000000AAA)
- [Record: Example Opportunity](sf://006000000000000AAA)

Resolver rules:
✓ Linkify EVERY Salesforce artifact mentioned when an Id can be resolved
✓ Use the Production Id for Production findings; use the Sandbox Id for Sandbox-only changed metadata
✓ For Flows, query Tooling API `FlowDefinition` and link the FlowDefinition Id (`300...`) by default
✓ Also include the active Flow version Id (`301...`) when version specificity matters
✓ For Permission Sets, query `PermissionSet` and link the PermissionSet Id (`0PS...`)
✓ For Users, link the User Id (`005...`) when user records are part of the evidence
✓ For custom fields, use the field DurableId component Id (`00N...`) when available
✓ Do not linkify deployment/deploy request Ids (`0Af...`); those are transient deployment records
✓ Do not linkify Permission Set Assignment Ids (`0Pa...`); they are junction records and often fail for normal admins
✓ If no Id is available, write the artifact name as plain text and explicitly mark "Id not resolved"
✓ Do not emit typed pseudo links such as `sf://flow/Flow_API_Name` or `sf://field/Object/Field__c`

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
5. RUN VOICE VALIDATION CHECKLIST (all must be YES):
   - ✓ No em dashes (—)? YES or STOP and fix.
   - ✓ No hyphens used as clause punctuation? YES or STOP and fix.
   - ✓ No "we," "we've," "we're," "us," "let us"? YES or STOP and find/replace.
   - ✓ Tone is direct and human, not corporate? YES or STOP and rewrite.
   - ✓ Specific thanks for good repro/screenshots/detail? YES or N/A.
   - ✓ No unnecessary jargon or admin terms? YES or STOP and simplify.
6. Only after validation, save to outputs/jira-messages/<KEY>.md

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

CONTENT RULES (LEAN — NOT Investigation replay):
- Root cause: One-sentence diagnosis ONLY. Link to Investigation for full detail.
- Decision: Support-resolved OR Escalate to Engineering + confidence + evidence (terse).
- Actions: Concrete steps taken (if Support) or handoff summary (if Engineering).
- Production vs Sandbox: Explicit state (what changed where, what's next for operator).
- Risks: Brief list, one line per risk.
- DO NOT: Paste investigation sections, full metadata dumps, detailed evidence, narrative repros.
  → Investigation file is the source of truth. Internal Notes is the decision memo only.

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
4. LEAN CHECK (all must be YES):
   - ✓ Root Cause is ONE SENTENCE (not a paragraph)? YES or condense.
   - ✓ No investigation sections pasted (e.g., "## Issue Understanding", "## Production Metadata")? YES or DELETE.
   - ✓ No detailed metadata lists (Field X on Object Y configuration lists)? YES or DELETE and link to Investigation.
   - ✓ No narrative repro steps or evidence playback? YES or DELETE and link to Investigation.
   - ✓ Production vs Sandbox section is concrete (who does what next)? YES or rewrite for action.
   - ✓ Total length under 500 words? YES or trim.
5. Only after validation, save to outputs/internal-notes/<KEY>.md

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
