# Problem Hypothesis and Solution

<!-- Follow Markdown formatting rules in ../references/markdown-output-rules.md. -->

**Issue:** `<KEY>`
**Date:** `<YYYY-MM-DD>`

---

## Problem Hypothesis

**Confirmed facts:**
- [Fact 1: What is known to be true from Jira issue + Issue Understanding]
- [Fact 2: Specific, verifiable behavior or state]
- [Fact 3: Evidence or context]

**Symptoms:**
- [Observable failure or misbehavior]
- [User or business impact]

**Root cause hypothesis:**
[One-sentence statement: what is broken and why, based on confirmed facts. Reference a Salesforce component, configuration, data condition, permission, or integration behavior.]

---

## Smallest Viable Fix

**What to fix:**
- **Artifact:** [Exact component, record/config item, field, flow, Apex class, permission set, integration mapping, etc.]
- **Change scope:** [What specifically changes]
- **Why it solves the problem:** [Direct link between root cause and fix]

---

## Sandbox Validation Plan

**What to test in Sandbox:**
- [Test scenario 1: exact reproduction path from the issue]
- [Test scenario 2: edge case or related behavior]

**Expected outcome:**
- [What should happen after the fix is deployed or applied in Sandbox]

**Success criteria:**
- [Boolean criteria that proves the issue is resolved]

---

## Rollback Plan

**If Sandbox test fails:**
1. [Undo step 1]
2. [Undo step 2]
3. [Fallback action]

**If Production deployment fails:**
1. [Rollback path through Gearset or the org standard process]
2. [Notification or operator follow-up]
3. [Investigation needed]

---

## Risks and Constraints

**Implementation risks:**
- [Risk 1]
- [Risk 2]

**Constraints:**
- [Constraint 1]
- [Constraint 2]

**Mitigation:**
- [How to reduce impact]

---

## Production Deploy Readiness

**Sandbox sign-off:** [Name/date or "not complete"]

**Production deploy path:** [Gearset / standard deploy / manual admin action / no deploy / Engineering]

**Rollout plan:** [Immediate / scheduled / phased / operator decision needed]

**Monitoring after deploy:** [What to watch in Production]
