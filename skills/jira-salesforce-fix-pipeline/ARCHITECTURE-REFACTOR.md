# Pipeline Architecture Refactor

## Problem

Current design: monolithic skill doing everything (sync, analysis, implementation, testing, messaging, summarization). Violates separation of concerns. Hard to test, debug, iterate independently.

## Solution

**Orchestrator pattern:** Pipeline Orchestrator skill coordinates flow between specialized sub-skills. Orchestrator handles routing and decisions only. Sub-skills handle domain work.

## Refactored Architecture

```
UI Button Invocation
  ↓
Pipeline Orchestrator Skill (COORDINATOR ONLY)
  ├─ Step 1-2: Setup (sync via jira_sync.py, triage routing)
  ├─ Step 3: Delegate to jira-issue-analysis skill → get summary
  ├─ Step 4: Synthesize hypothesis from Step 3 summary
  ├─ Step 5-6: Delegate to salesforce-metadata-investigation skill → get summary
  ├─ Step 7: Make escalation gate decision from Step 6 summary
  ├─ Step 8-9: Delegate to salesforce-implementation skill (combined) → get summary
  ├─ Step 10: Delegate to jira-response-drafting skill → get summary
  ├─ Step 11-12: Generate dated summary + return results
  └─ State tracked in outputs/ (manifest, investigations, engineering-escalations, etc.)
```

## Skill Responsibilities

### Pipeline Orchestrator (NEW)
- **Owns:** Flow control, routing, decision gates, state tracking
- **Does:** 
  - Steps 1-2 (setup via jira_sync.py + run_pipeline.py)
  - Steps 4, 7, 11, 12 (orchestrator decisions only)
  - Delegates Steps 3, 5, 6, 9, 10 to sub-skills
  - Reads file state to decide routing
  - Saves summaries + decision logs
- **Does NOT:**
  - Analyze issues (delegate to Step 3 skill)
  - Implement fixes (delegate to Step 8-9 skill)
  - Test in Sandbox (delegate to Step 8-9 skill)
  - Draft messages (delegate to Step 10 skill)

### jira-issue-analysis (existing)
- **Owns:** Issue understanding, root cause analysis
- **Step 3 only**

### salesforce-metadata-investigation (existing)
- **Owns:** Production metadata retrieval + problem location identification
- **Steps 5-6 only**

### salesforce-implementation (NEW - COMBINED)
- **Owns:** Fix implementation + Sandbox deployment + testing
- **Combines current Steps 8-9**
- **Why:** Tightly coupled (implement → test), should be one skill

### jira-response-drafting (existing)
- **Owns:** Customer message + internal note drafting
- **Step 10 only**

## Context Management

### Orchestrator Context
- Minimal: Issue key + status + routing decision
- Retains only ~300-500 token summaries from sub-skills
- Avoids context explosion across 12 steps

### Sub-Skill Context
- Full context when invoked
- Analysis file from Step 3
- Metadata file from Step 5-6
- Implementation summary from Step 8-9
- Each skill gets enough context to do its job

## State Tracking (File-Based)

Orchestrator checks file existence to determine routing:

```
outputs/
├── jira/manifest.csv                          # All issues
├── closed-resolved/{key}.md                   # Step 2: Closed/resolved
├── engineering-escalations/{key}.md           # Step 7: Escalation decision
├── investigations/{key}.md                    # Step 3: Analysis
├── step-4-hypothesis/{key}.md                 # Step 4: Hypothesis
├── internal-notes/{key}.md                    # Step 10: Draft (internal)
├── jira-messages/{key}.md                     # Step 10: Draft (customer)
├── test-reports/{key}.md                      # Step 9: Test results
└── issue-summary-YYYY-MM-DD.md                # Step 11: Summary
```

### Decision Logic
- If `closed-resolved/{key}` exists → skip this issue (already archived)
- If `engineering-escalations/{key}` exists → skip Steps 8-9, go to Step 10 (escalated)
- If `test-reports/{key}` exists → issue tested, proceed to Step 10
- If `investigations/{key}` exists but empty → awaiting Step 3 analysis

## Error Handling & Checkpoints

### Explicit Gates
1. **After Step 2 (Triage):** Validate issue routing
2. **After Step 6 (Problem Location):** Validate escalation decision
3. **After Step 9 (Test):** Validate test results or escalation path
4. **After Step 10 (Messaging):** Validate message format separation

### Resumability
- Orchestrator can resume from any step
- Sub-skills can be re-run if they fail
- No duplicate work if step already completed

## Implementation Roadmap

### Phase 1: Orchestrator Refactor
- [ ] Write new Pipeline Orchestrator skill (coordinator-only)
- [ ] Extract decision logic from current skill
- [ ] Test routing with existing sub-skills

### Phase 2: Sub-Skill Isolation
- [ ] Verify jira-issue-analysis works standalone (Step 3)
- [ ] Verify salesforce-metadata-investigation works standalone (Steps 5-6)
- [ ] Create salesforce-implementation skill (combine 8-9)
- [ ] Verify jira-response-drafting works standalone (Step 10)

### Phase 3: Integration Testing
- [ ] End-to-end flow testing
- [ ] Error path testing
- [ ] State recovery testing

### Phase 4: Cleanup
- [ ] Remove deprecated code from run_pipeline.py
- [ ] Simplify UI button routing (all invoke orchestrator)
- [ ] Archive old monolithic skill

## Benefits

1. **Testability:** Each skill tested independently
2. **Debuggability:** Clear boundaries, easy to trace issues
3. **Maintainability:** Focused skill responsibilities
4. **Reusability:** Sub-skills usable in other contexts
5. **Scalability:** Easy to add new steps or variations
6. **Observability:** File-based state = transparent progress
7. **Resumability:** Can retry failed steps without full re-run
