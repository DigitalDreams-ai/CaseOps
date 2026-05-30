# CaseOps Pipeline Enhancement Plan

## Overview

Phase 1: Gather baseline data. Phase 2+ based on what Phase 1 learns.

**Decisions deferred to Phase 2 (based on Phase 1 metrics):**
1. **Scope Validator** — Do we need it? Phase 1 will measure Step 7 escalation accuracy.
2. **Related Issues** — Does it help? Phase 1 will measure Step 3 analysis speed baseline.
3. **Salesforce MCP integration** — Research + planning
4. **Jira authentication** — Audit team review

---

## Phase 1: Immediate (1 week) — Logging & Baselines Only

**NO renumbering. NO scope validator. NO new sub-agents.**

Pipeline stays exactly as-is (Steps 1-12). Just add instrumentation.

### 1.1 JSON Logging & Baseline Metrics

**Implementation:**

Add JSON logging to existing Steps 1-12:
- `app.py` progress tracking (STEP_N emissions include metrics)
- `ORCHESTRATOR-PROMPT.md` documentation of baseline requirements
- Sub-agent response time capture (already partially done)

**Metrics to capture per issue:**

```json
{
  "key": "HEAL-33753",
  "step": 3,
  "duration_seconds": 5.2,
  "sub_agent": "jira-issue-analysis",
  "response_tokens": 450,
  "confidence": 0.85
}
```

**Baseline measurements (across first 10 issues):**

- Step 3 analysis speed: T seconds (median, p95)
- Step 3 sub-agent response tokens: N (median)
- Step 7 escalation accuracy: X% (count correct vs. wrong decisions on sample)
- Escalation rate: Y% (issues escalated vs. support-fixed)
- Sub-agent response times: Step 3, 5, 6, 8, 10 (median, p95)

**Why this matters:** Phase 2 decisions depend on baseline data. "Do we need scope validator?" "Is Step 3 analysis slow?" Measure first, decide later.

### 1.2 Jira Authentication (DEFERRED TO PHASE 2)

**Status:** Move to Phase 2 for audit team review before implementation.

**Reasoning:** Using personal API token affects audit trail integrity. Requires compliance sign-off.

**Phase 2 plan:**
- Coordinate with audit/compliance team
- Document business justification (transparency, accountability)
- Implement after Phase 1 ships


---

## Phase 1.5: Conditional (1-2 weeks) — Related Issues

**Decision gate:** Implement ONLY if Phase 1 baseline shows opportunity.

**Baseline requirement:** Phase 1 must measure Step 3 analysis speed WITHOUT related issues. If improvement opportunity is marginal, skip Phase 1.5 entirely.

**IF proceeding with Phase 1.5:**

### 1.5.1 Related Issues Identification

**Files to modify:**
- `jira_sync.py` (add Step 1.5: fetch related issues)
- `app.py` (update progress tracking for Step 1.5)
- `ORCHESTRATOR-PROMPT.md` (document Step 1.5)

**Implementation:**

Step 1.5 (after manifest fetch):
```
For each active issue KEY:
  JQL query: component ~ <component> AND (status = Closed OR key = KEY) LIMIT 5
  Fetch related issues, save to outputs/investigations/{KEY}-related.md
  Format: issue key, summary, status, resolution reason (if closed)
```

**Constraint:** Component-based matching only (more precise than keyword). Reduces false positives.

Step 3 input: Sub-agent receives `{KEY}-related.md` alongside issue context
- Analysis can reference: "Similar issue HEAL-33752 (closed, same component), caused by X"
- Hypothesis gains confidence from pattern match

Step 6 validation: Problem location confirms or refutes pattern
- "Production has same problem as HEAL-33752 — specifically, missing record type. Likely same root cause."

### 1.5.2 Success Criteria for Phase 1.5

- [ ] Related issues identified for 80%+ of issues (component match)
- [ ] Step 3 analysis speed improves 2-3x vs. Phase 1 baseline (measured in metrics)
- [ ] Related issues accuracy >= 80% (human review of 10 issues)
- [ ] JQL performance acceptable (< 1s/issue, no API rate limits)
- [ ] If any metric misses: remove feature, keep Phase 1 core

---

## Phase 2: Future (4-8 weeks)

### 2.1 Salesforce MCP

**Research task:**
- Search for existing Salesforce MCPs (anthropic-ai/mcp-servers, community repos)
- Evaluate: maturity, API coverage, authentication support

**If none exist, build wrapper:**

**MCP endpoints needed:**
```
salesforce_mcp.retrieve_metadata(
  component_type: "Flow|ValidationRule|CustomObject|Apex",
  name: str,
  org: "Production|Sandbox"
) → metadata JSON

salesforce_mcp.deploy(
  metadata: list[str],
  target_org: str,
  test_level: "NoTestRun|RunLocalTests|RunAllTests"
) → deployment result

salesforce_mcp.test(
  test_class: str,
  org: str
) → test results

salesforce_mcp.query_metadata(
  component_type: str,
  filter: dict
) → matching components
```

**Integration into pipeline:**

Step 1: **No change** — jira_sync.py stays. Fetches Jira issues, creates manifest.

Steps 5-6: Replace manual metadata investigation with MCP calls:

Current (manual):
```
Sub-agent reads cached metadata files or runs sf CLI commands
Returns findings based on file inspection
```

Future (with MCP):
```
metadata = salesforce_mcp.retrieve_metadata(
  component_type="Flow",
  name="Order Sync",
  org="Production"
)

details = salesforce_mcp.query_metadata(
  component_type="Flow",
  filter={"name__contains": "Order Sync"}
)

# Returns direct API responses, not files
```

Steps 9-10: Deploy + test via MCP (was via sf CLI):
```
result = salesforce_mcp.deploy(
  metadata=[problem_artifact],
  target_org="CASEOPS_SANDBOX_TARGET_ORG",
  test_level="RunAllTests"
)

test_result = salesforce_mcp.test(
  test_class="OrderSyncTests",
  org="CASEOPS_SANDBOX_TARGET_ORG"
)
```

**What MCP replaces:**
- Manual sf CLI invocations in sub-agents
- Cached metadata files in outputs/salesforce-metadata/
- Investigation file parsing for metadata details

**What stays:**
- jira_sync.py (fetches Jira, unaffected)
- File-based state tracking (investigation.md, test-reports.md, etc.)

**Timeline:** Build after Phase 1 complete. Or use as reference for future work.

---

## Phase 3: Nice-to-have (8+ weeks)

### 3.1 Sandbox Pooling

When scaling to 10+ instances.

### 3.2 Event-driven Orchestrator

When sequential bottleneck reached.

### 3.3 Human-in-the-loop Interactive Mode

Different product. Separate roadmap.

---

## Implementation Sequence

### Phase 1 (Week 1)

1. Add JSON logging to `app.py` (STEP_N emissions)
2. Update `ORCHESTRATOR-PROMPT.md` with baseline metrics requirements
3. Test: run 10 issues end-to-end, collect baseline data
4. Ship Phase 1 (no changes to pipeline, just logging)

### Analysis (Week 2)

5. **Analyze baseline metrics:**
   - Step 3 analysis speed (seconds)
   - Step 7 escalation accuracy (% correct on sample)
   - Escalation rate (% escalated vs. support-fixed)
   - Sub-agent response times

6. **Decisions for Phase 2:**
   - Is Step 3 slow? → Maybe need related issues?
   - Is Step 7 accuracy low? → Maybe need scope validator?
   - Which problem is bigger? Start there.

### Phase 2 (Weeks 3-5+, based on Phase 1 data)

7. Implement one feature at a time based on Phase 1 findings
8. (Scope validator? Related issues? MCP integration? Prioritize by data)

### Phase 3 (Future, based on Phase 1-2 learnings)

---

## Files to Create/Modify

### Phase 1

**Modify (small changes):**
- `app.py` (add JSON logging to STEP_N emissions)
- `ORCHESTRATOR-PROMPT.md` (document baseline metrics requirement)

**No other files.**

---

## Capacity & Team

### Phase 1 (1 week)

- **1 engineer, 1 week:** Add JSON logging, run baseline, collect metrics
- **Can be done in parallel with other work**

### Phase 2+ (based on Phase 1 findings)

- **Depends on which improvement Phase 1 data suggests**

---

## Phase 1 Testing & Validation

**Before shipping, validate:**

1. **Logging works**
   - [ ] JSON logging added to app.py
   - [ ] STEP_N lines emit with metrics (duration, tokens, confidence)
   - [ ] No errors in logging code

2. **End-to-end baseline run**
   - [ ] Run 10 issues through Steps 1-12 (no changes to pipeline)
   - [ ] Collect baseline metrics for all steps
   - [ ] Verify data quality (no NaNs, no missing fields)

3. **Baseline metrics collected**
   - [ ] Step 3 analysis speed: T seconds (median, p95)
   - [ ] Step 7 escalation accuracy: X% (count correct decisions on sample)
   - [ ] Escalation rate: Y% (issues escalated vs. support-fixed)
   - [ ] Sub-agent response tokens captured

**Abort condition:** If logging fails or metrics incomplete, fix before shipping.

---

## Success Criteria — Phase 1

- [ ] JSON logging added to app.py
- [ ] 10-issue baseline run complete
- [ ] Metrics collected: Step 3 speed, Step 7 accuracy, escalation rate, sub-agent tokens
- [ ] Phase 1 shipped (no pipeline changes, just logging)
- [ ] Baseline data analyzed: what's fast, what's slow, what's broken?

## Next Steps — Phase 2 (based on Phase 1 data)

- [ ] Review Phase 1 metrics
- [ ] Prioritize: scope validator? related issues? something else?
- [ ] Implement ONE improvement, measure impact
- [ ] Iterate

---

## Abort Conditions

### Phase 1 Abort Conditions

**Do NOT ship Phase 1 if:**

| Condition | Action |
|-----------|--------|
| JSON logging fails or has errors | Fix logging code before shipping |
| Baseline run incomplete (< 10 issues) | Run more issues until metrics stable |
| Metrics missing or malformed | Verify data integrity before shipping |

**Decision rule:** Ship Phase 1 ONLY when logging works + baseline metrics complete + no errors.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| JSON logging adds overhead | Test on 10 issues. If performance impact > 10%, optimize before shipping. |
| Baseline metrics incomplete or wrong | Don't skip this step. Run 10 issues, validate data quality. |
| Phase 1 takes longer than 1 week | Just logging. If > 1 week, something is wrong. Debug immediately. |
| Phase 2 decisions unclear from Phase 1 data | Define clear metrics thresholds upfront. "Slow" = what? "Accurate" = what? Lock thresholds before Phase 1. |

---

## Notes

- **Phase 1 (1 week):** Just logging + baselines. NO pipeline changes. Ship ASAP.
- **Phase 2 (based on Phase 1 data):** Decide what to build based on metrics.
  - Slow analysis? → Add scope validator? Or related issues?
  - Low escalation accuracy? → Need better decision logic?
  - Something else?
- **Phase 3+:** Future improvements based on Phase 2 learnings.

**Philosophy:** Gather data first. Make decisions later. Ship something measurable every week.
