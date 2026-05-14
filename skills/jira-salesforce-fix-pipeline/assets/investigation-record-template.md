# Investigation Record

## Jira Issue

- Key:
- Summary:
- Status:
- Priority:
- Reporter:
- Assignee:
- Link:

## Reproduction Steps (top-level — used for escalations and validation)

1. [Step 1 — include login type, Salesforce UI navigation or API call]
2. [Step 2]
3. [Observe: actual behavior — what is broken]

**Expected behavior:**

**Affected record IDs or characteristics:**

---

## Issue Understanding

### Observed Behavior

### Expected Behavior

### Acceptance Criteria

### Attachments Or Evidence

### Unknowns

## Salesforce Problem

### Confirmed Facts

### Hypotheses

### Likely Affected Metadata

## Escalation Decision (early flag)

**Is this Support-resolvable or Engineering escalation?**
- Support-resolvable (data, config, access, report, list-view, permission changes)
- Engineering escalation (Apex/code, flows, approval processes, validation rules, automation)

**If escalating:** What specific capability does Engineering need? (e.g., "create a flow to trigger on record update")

## Solution Plan

### Classification

- Support-resolvable or Engineering escalation:
- Escalation reason, if any:

### Proposed Change

### Production vs sandbox deployment state (required)

State clearly for the operator. **Do not** imply Production was updated unless it was (this pipeline does not deploy to Production unless explicitly requested).

| Question | Answer |
| --- | --- |
| **What exists in Production today?** | (Summarize read-only verification: component present / absent / partial — cite Step 5 or SOQL.) |
| **What exists only in Sandbox after this fix?** | (List metadata or config changed/deployed **only** in the allowlisted Sandbox.) |
| **Production metadata deploy required?** | **Yes — promote via Gearset** (or team standard) / **No — fix relies on metadata already in Production** / **N/A — no metadata change** (data, assignment, user education only). |
| **Operator next step** | (e.g. “Create Gearset deployment from Sandbox → Production for Permission Set X” or “None — assign existing Permission Set Y in Production”.) |

### Why This Should Fix It

### Risks

### Rollback Plan

## If Escalating to Engineering

**Steps to Reproduce (for Engineering handoff — must be clear and testable)**
1. [Step 1 — login type, UI/API path]
2. [Step 2]
3. [Observe: actual behavior]

**Expected behavior:**

**Affected record IDs or data characteristics:**

**Root cause clarity for handoff:**
(Brief: what it's NOT, where the gap is, why symptom shows up — Engineering will refine, but be clear enough to avoid back-and-forth)

**Metadata/components involved:**
(What Engineering owns or needs to change)

## Production Metadata Retrieved

| Metadata | Reason Retrieved | Relevant Finding |
| --- | --- | --- |

## Implementation

### Engineering Handoff

- Required?:
- Handoff file: `outputs/engineering-escalations/<KEY>.md`

### Files Or Metadata Changed

### Notes

## Sandbox Deployment

- Sandbox:
- Command:
- Result:

## Testing

### Test Cases

### Results

### Fixed?

## Iterations

| Attempt | Hypothesis | Change | Test Result | Next Step |
| --- | --- | --- | --- | --- |
