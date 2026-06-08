# Orchestration Loop Controller (Steps 3–11)

This document describes the loop logic for processing active issues through Steps 3–11 of the CaseOps pipeline. The orchestrator (Claude Code skill) executes this loop sequentially for each active issue.

---

## Loop Overview

**Input:** Active issue list from `outputs/jira/manifest.csv` (post-triage from Step 2)

**Processing:**
1. For each active issue (ISSUE-XXXXX):
   - Steps 3–7: Diagnosis loop (analysis → hypothesis → metadata → location → escalation gate)
   - Step 7 decision: Branch to Support or Engineering path
   - Support path: Steps 8–10 (implement → deploy/test → draft messages)
   - Engineering path: Skip 8–9, go directly to Step 10 (draft escalation message)
   - Step 10: Message drafting (customer-facing + internal)
   - After Step 10: Log outcome in dated summary

**Output:** Dated summary file `outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md` with all issues rolled up

---

## Progress Tracking

### Log File Per Run

Create a progress log file at start: `outputs/pipeline-logs/YYYYMMDD-HHMMSS.log`

**Log entries:**
- `START <KEY>` — Begin processing issue
- `STEP_3 <KEY> ✓ summary` — Step 3 complete, returned summary
- `STEP_4 <KEY> ✓ file` — Hypothesis documented
- `STEP_5 <KEY> ✓ summary` — Step 5 metadata retrieved
- `STEP_6 <KEY> ✓ summary` — Step 6 problem location identified
- `STEP_6_LOOP <KEY> iteration=1 REQUEST: Step 5 refinement — [specific metadata]` — Metadata loop detected
- `STEP_7 <KEY> DECISION: Support-resolvable` or `STEP_7 <KEY> DECISION: Engineering-escalated`
- `STEP_8 <KEY> ✓ implemented` — Sandbox changes documented (Support path only)
- `STEP_9 <KEY> ✓ passed` or `STEP_9 <KEY> ✗ failed` — Deploy/test result
- `STEP_9_LOOP <KEY> iteration=1 — Revised hypothesis, looping back to Step 5` — Retry iteration
- `STEP_10 <KEY> ✓ messages drafted` — Internal notes + Jira message created
- `END <KEY> disposition=<fixed|escalated|on-hold>` — Complete and log outcome

### Issue-Specific Progress File (Optional)

For long runs (15+ issues), create per-issue progress file: `outputs/pipeline-logs/<KEY>.progress`

Example content:
```
Issue: ISSUE-33618
Received: 2026-05-20T14:30:00Z
Current step: 9
Last update: 2026-05-20T15:15:00Z (testing in Sandbox)
Iterations: 1 (Step 9 failed, retrying)
Estimated completion: 2026-05-20T16:00:00Z
```

---

## Loop Control Logic (Pseudocode)

```pseudocode
FUNCTION process_active_issues(active_issue_list, manifest_metadata):
    """
    Main loop: for each active issue, execute Steps 3–11 with branching.
    Handles iteration/loop-back for Step 5/6 metadata discovery and Step 9 failure.
    """
    
    log_file = create_log("outputs/pipeline-logs/{YYYYMMDD-HHMMSS}.log")
    summary_data = initialize_summary_template()
    
    FOR EACH issue IN active_issue_list:
        
        issue_key = issue["Key"]
        jira_summary = load_file(f"outputs/jira/summary/{issue_key}.md")
        
        log(f"START {issue_key}")
        
        # ====== DIAGNOSIS LOOP (Steps 3–7) ======
        
        # Step 3: Analyze issue
        step_3_summary = spawn_sub_agent(
            tool="jira-issue-analysis",
            prompt_template="Step 3 — Analyze the issue",
            inputs={
                "issue_key": issue_key,
                "jira_summary": jira_summary
            }
        )
        log(f"STEP_3 {issue_key} ✓ {step_3_summary[:50]}...")
        
        # Step 4: Synthesize hypothesis
        hypothesis = synthesize_hypothesis(
            issue_key=issue_key,
            step_3_summary=step_3_summary
        )
        write_file(f"outputs/hypothesis/{issue_key}.md", hypothesis)
        log(f"STEP_4 {issue_key} ✓ outputs/hypothesis/{issue_key}.md")
        
        # Step 5 → 6 Metadata Loop
        step_6_metadata_loop = True
        loop_iteration = 0
        WHILE step_6_metadata_loop AND loop_iteration < 3:
            loop_iteration += 1
            
            # Step 5: Retrieve metadata
            step_5_summary = spawn_sub_agent(
                tool="salesforce-production-metadata-investigation",
                prompt_template="Step 5 — Retrieve relevant Production metadata",
                inputs={
                    "issue_key": issue_key,
                    "hypothesis": hypothesis
                }
            )
            log(f"STEP_5 {issue_key} ✓ {step_5_summary[:50]}...")
            
            # Step 6: Identify problem location
            step_6_result = spawn_sub_agent(
                tool="salesforce-production-metadata-investigation",
                prompt_template="Step 6 — Identify problem location",
                inputs={
                    "issue_key": issue_key,
                    "hypothesis": hypothesis,
                    "production_metadata": step_5_summary
                }
            )
            
            # Check for Step 5/6 loop-back request
            IF step_6_result CONTAINS "REQUEST: Step 5 refinement":
                refined_request = extract_request(step_6_result)
                log(f"STEP_6_LOOP {issue_key} iteration={loop_iteration} REQUEST: {refined_request}")
                # Continue loop; next iteration will fetch refined metadata
            ELSE:
                step_6_metadata_loop = False
                log(f"STEP_6 {issue_key} ✓ {step_6_result[:50]}...")
        
        IF loop_iteration >= 3:
            log(f"STEP_6 {issue_key} ✗ BLOCKER: Metadata loop exceeded 3 iterations")
            log(f"END {issue_key} disposition=on-hold (requires manual investigation)")
            ADD_TO_SUMMARY(issue_key, disposition="on-hold", reason="Metadata loop blocker")
            CONTINUE
        
        # Step 7: Escalation gate
        escalation_decision = determine_escalation(
            issue_key=issue_key,
            problem_location=step_6_result
        )
        log(f"STEP_7 {issue_key} DECISION: {escalation_decision}")
        
        # ====== BRANCHING PATH ======
        
        IF escalation_decision == "Engineering-escalated":
            
            # Engineering path: Skip Steps 8–9
            log(f"STEP_8 {issue_key} — SKIPPED (Engineering escalation)")
            log(f"STEP_9 {issue_key} — SKIPPED (Engineering escalation)")
            
            # Create engineering handoff
            engineering_handoff = create_file(
                f"outputs/engineering-escalations/{issue_key}.md",
                template="assets/engineering-handoff-template.md",
                data={
                    "problem_location": step_6_result,
                    "hypothesis": hypothesis,
                    "affected_metadata": step_5_summary
                }
            )
            log(f"ESCALATION {issue_key} ✓ outputs/engineering-escalations/{issue_key}.md")
            
            # Step 10 with escalation flag
            test_result = "N/A - Engineering escalation"
            
        ELSE:
            # Support path: Execute Steps 8–9
            
            # Step 8: Implement
            implementation_changes = implement_fix(
                issue_key=issue_key,
                hypothesis=hypothesis
            )
            write_file(f"outputs/investigations/{issue_key}.md", implementation_changes)
            log(f"STEP_8 {issue_key} ✓ implemented")
            
            # Step 9 Deploy/Test Loop
            deploy_test_iteration = 0
            test_passed = False
            WHILE NOT test_passed AND deploy_test_iteration < 3:
                deploy_test_iteration += 1
                
                # Before spawning Step 9: Verify Sandbox org
                sandbox_org = read_env_variable(active_env_file(), "CASEOPS_SANDBOX_TARGET_ORG")
                IF sandbox_org IS EMPTY OR NOT REACHABLE:
                    log(f"STEP_9 {issue_key} ✗ BLOCKER: CASEOPS_SANDBOX_TARGET_ORG missing or unreachable")
                    log(f"END {issue_key} disposition=on-hold (Sandbox org blocker)")
                    ADD_TO_SUMMARY(issue_key, disposition="on-hold", reason="Sandbox org unreachable")
                    CONTINUE OUTER LOOP
                
                step_9_result = spawn_sub_agent(
                    tool="salesforce-sandbox-deploy-test",
                    prompt_template="Step 9 — Deploy, test, and iterate",
                    inputs={
                        "issue_key": issue_key,
                        "sandbox_org": sandbox_org,
                        "fix_description": implementation_changes,
                        "jira_acceptance_criteria": extract_criteria(jira_summary)
                    }
                )
                
                IF step_9_result CONTAINS "Pass":
                    test_passed = True
                    log(f"STEP_9 {issue_key} ✓ passed")
                    log(f"TEST_REPORT {issue_key} ✓ outputs/test-reports/{issue_key}.md")
                ELSE:
                    deploy_test_iteration += 1
                    log(f"STEP_9 {issue_key} ✗ failed (iteration={deploy_test_iteration})")
                    
                    IF deploy_test_iteration < 3:
                        # Loop back to Step 4 for hypothesis revision
                        log(f"STEP_9_LOOP {issue_key} iteration={deploy_test_iteration} — Revised hypothesis, looping back to Step 5")
                        hypothesis = revise_hypothesis(
                            original_hypothesis=hypothesis,
                            test_failure_details=step_9_result
                        )
                        write_file(f"outputs/hypothesis/{issue_key}.md", hypothesis)
                        # Continue loop to Step 5
                    ELSE:
                        log(f"STEP_9 {issue_key} ✗ BLOCKER: Deploy/test exceeded 3 iterations")
                        log(f"END {issue_key} disposition=on-hold (requires manual revision)")
                        ADD_TO_SUMMARY(issue_key, disposition="on-hold", reason="Sandbox test blocker")
                        BREAK
            
            test_result = "Pass" IF test_passed ELSE "N/A - Blocker"
        
        # ====== MESSAGE DRAFTING (Step 10) ======
        
        step_10_result = spawn_sub_agent(
            tool="jira-response-drafting",
            prompt_template="Step 10 — Draft internal notes and Jira message",
            inputs={
                "issue_key": issue_key,
                "root_cause": hypothesis,
                "fix_or_escalation": escalation_decision,
                "test_result": test_result,
                "investigation_record": read_file(f"outputs/investigations/{issue_key}.md")
            }
        )
        
        # Validate file separation
        jira_msg_file = f"outputs/jira-messages/{issue_key}.md"
        internal_file = f"outputs/internal-notes/{issue_key}.md"
        IF NOT file_exists(jira_msg_file) OR NOT file_exists(internal_file):
            log(f"STEP_10 {issue_key} ✗ VALIDATION FAILED: Missing output files")
            log(f"END {issue_key} disposition=on-hold (Step 10 validation failure)")
            ADD_TO_SUMMARY(issue_key, disposition="on-hold", reason="Message drafting failed")
            CONTINUE
        
        jira_msg_content = read_file(jira_msg_file)
        internal_content = read_file(internal_file)
        
        IF jira_msg_content CONTAINS "[INTERNAL]" OR internal_content CONTAINS "Hi [":
            log(f"STEP_10 {issue_key} ✗ VALIDATION FAILED: Files are mixed (customer/internal)")
            log(f"END {issue_key} disposition=on-hold (Step 10 file separation failure)")
            ADD_TO_SUMMARY(issue_key, disposition="on-hold", reason="Step 10 file mixing")
            CONTINUE
        
        log(f"STEP_10 {issue_key} ✓ messages drafted (validated)")
        
        # ====== SUMMARY & CLOSE-OUT ======
        
        disposition = determine_disposition(escalation_decision, test_result)
        log(f"END {issue_key} disposition={disposition}")
        
        ADD_TO_SUMMARY(
            issue_key=issue_key,
            jira_status=issue["Status"],
            summary=issue["Summary"],
            disposition=disposition,
            prod_deploy_needed=determine_prod_deploy(escalation_decision, test_result),
            sandbox_org=CASEOPS_SANDBOX_TARGET_ORG,
            test_report_path=f"outputs/test-reports/{issue_key}.md" IF disposition == "fixed" ELSE "N/A",
            internal_notes_path=f"outputs/internal-notes/{issue_key}.md",
            jira_message_path=f"outputs/jira-messages/{issue_key}.md"
        )
    
    # ====== POST-PROCESSING (Steps 11–12) ======
    
    # Step 11: Generate dated summary
    summary_output_path = generate_summary(
        summary_data=summary_data,
        template="assets/issue-summary-template.md",
        date=TODAY,
        output_file=f"outputs/summaries/{TODAY}/issue-summary-{TODAY}.md"
    )
    log(f"STEP_11 ✓ Summary generated: {summary_output_path}")
    
    # Step 12: Report to user
    report_summary = generate_user_report(
        summary_data=summary_data,
        dated_summary_path=summary_output_path,
        issues_processed=len(active_issue_list),
        log_file_path=log_file
    )
    log(f"STEP_12 ✓ User report ready")
    
    PRINT(report_summary)
    RETURN success=True, summary_path=summary_output_path
```

---

## Escalation Gate Decision (Step 7)

**Input:** Problem location from Step 6 (problem type, specific artifact, location, failure point)

**Decision criteria:**

| Problem Type | Example Artifact | Decision | Path |
|---|---|---|---|
| **Data** | Order.ShipToCity null | Support-resolvable | Steps 8–10 |
| **Config** (no automation) | Permission Set field-level access | Support-resolvable | Steps 8–10 |
| **Validation Rule** update | Existing rule needs exception | Engineering-required | Skip 8–9, go to 10 |
| **Flow** modification | SOAP trigger, new flow branch | Engineering-required | Skip 8–9, go to 10 |
| **Apex code** change | Custom class, trigger, extension | Engineering-required | Skip 8–9, go to 10 |
| **Approval Process** change | New step, routing rule | Engineering-required | Skip 8–9, go to 10 |
| **Integration API** | Wellvi payload mapping | Engineering-required | Skip 8–9, go to 10 |
| **Access / Role** | User role permission missing | Support-resolvable | Steps 8–10 |

**Note:** If uncertain, escalate to Engineering. Support team can resolve data/access/read-only config issues; code/automation changes belong to Engineering.

---

## Loop-Back Conditions

### Step 5 ↔ Step 6 Metadata Loop

**Trigger:** Step 6 sub-agent returns `"REQUEST: Step 5 refinement — [specific metadata]"`

**Action:**
1. Log: `STEP_6_LOOP {KEY} iteration=1 REQUEST: [metadata needed]`
2. Re-spawn Step 5 sub-agent with refined request
3. Re-spawn Step 6 with updated metadata
4. Repeat until Step 6 returns problem location (no further refinement request)
5. Cap at 3 iterations; if exceeded, escalate to Engineering with note: "Metadata discovery incomplete"

### Step 8 ↔ Step 9 Hypothesis/Test Loop

**Trigger:** Step 9 sub-agent returns `"Fail"`

**Action:**
1. Log: `STEP_9_LOOP {KEY} iteration=1 — Revised hypothesis, looping back to Step 5`
2. Revise Hypothesis based on test failure details
3. Re-spawn Step 5 (if more metadata is needed)
4. Re-spawn Step 6 if Step 5 discovered new artifacts
5. Re-implement Step 8 with revised hypothesis
6. Re-run Step 9 test
7. Cap at 3 iterations; if exceeded, escalate to Engineering with test failure details

---

## Blocker Handling

### Hard Stops (Escalate to Engineering or On-Hold)

| Condition | Action | Disposition |
|---|---|---|
| Step 3 returns no Issue Understanding | Spawn Step 3 again, or ask user for manual issue clarification | on-hold |
| Step 5/6 metadata loop > 3 iterations | Escalate with "Metadata discovery incomplete" | on-hold |
| Active env file missing CASEOPS_SANDBOX_TARGET_ORG | Stop run, report error | system-error |
| Sandbox org unreachable or credentials invalid | Stop run, report error | system-error |
| Step 9 failure loop > 3 iterations | Escalate to Engineering with test details | on-hold |
| Step 10 file validation fails (mixed customer/internal) | Re-prompt Step 10 sub-agent, or escalate | on-hold |

### Soft Failures (Retry or Escalate)

| Condition | Action | Retry Budget |
|---|---|---|
| Step 9 test fails | Revise hypothesis, re-run Step 5–9 | 3 attempts |
| Step 5/6 needs more metadata | Loop back to Step 5 with refined request | 3 iterations |
| Sub-agent timeout | Retry sub-agent call | 1 retry per step |

---

## Summary Generation (Step 11)

After all issues are processed, generate `outputs/summaries/YYYY-MM-DD/issue-summary-YYYY-MM-DD.md` using `assets/issue-summary-template.md`.

**Sections to populate:**

1. **Executive Summary**
   - Total issues in scope
   - Count of Closed/Resolved (skipped)
   - Count of active issues processed
   - Count of Engineering escalations (pre-escalated + escalated during processing)
   - Count of Sandbox deployments
   - Count of on-hold or blockers

2. **Closed / Resolved (Skipped)**
   - Table: Issue, Jira Status, Summary

3. **Issue Rollup**
   - Table: Issue, Jira Status, Summary, Disposition (fixed/escalated/on-hold), Prod deploy? (Gearset/No/N/A), Next Step
   - **Exclude** pre-escalated or escalated issues (they go in separate section)

4. **Sandbox Deployments / Validations**
   - Table: Issue, Sandbox, Deploy/Validation, Prod deploy needed?
   - Support-resolvable fixes only

5. **Escalated to Engineering**
   - Table: Issue, Jira Status, Component, Handoff File, Problem, Proposed Solution
   - Unified table (pre-escalated + escalated during processing)

6. **Artifact Index**
   - Links to output directories and per-issue files

---

## User Report (Step 12)

After Step 11, generate a clear, actionable report for the user:

```
═══════════════════════════════════════════════════════════════════
CaseOps Pipeline Run Complete
═══════════════════════════════════════════════════════════════════

Date: 2026-05-20
Issues processed: 5 active
Closed/Resolved (skipped): 2
Engineering escalations: 2
Support-fixed: 1

✓ Dated summary: outputs/summaries/2026-05-20/issue-summary-2026-05-20.md
✓ Jira message drafts: outputs/jira-messages/ISSUE-*.md
✓ Internal notes: outputs/internal-notes/ISSUE-*.md
✓ Run log: outputs/pipeline-logs/20260520-143000.log

NEXT STEPS FOR USER (Step 12):
1. Review dated summary: outputs/summaries/2026-05-20/issue-summary-2026-05-20.md
2. Post Jira messages:
   - ISSUE-33618: outputs/jira-messages/ISSUE-33618.md
3. Promote confirmed Support packages via Gearset or standard change control (if needed):
   - ISSUE-33618 (Gearset deployment required)
4. Coordinate with Engineering:
   - ISSUE-33633: outputs/engineering-escalations/ISSUE-33633.md
   - ISSUE-33369: outputs/engineering-escalations/ISSUE-33369.md

Total runtime: 2 hours 15 minutes
```

---

## Recommendations

1. **Process issues sequentially** (one at a time) to isolate failures and ensure clear progress tracking.
2. **Log every step transition** to enable debugging and auditing.
3. **Cap loop iterations** at 3 to prevent infinite loops and force escalation decisions.
4. **Validate file outputs** before proceeding (Step 10 file separation, Step 9 test reports exist).
5. **Report progress to user** after every issue completes (especially for long runs > 5 issues).
