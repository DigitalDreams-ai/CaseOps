# Step 4 — Problem Hypothesis and Solution

**Issue:** `<KEY>`  
**Date:** `<YYYY-MM-DD>`

---

## Problem Hypothesis

**Confirmed facts (from Step 3):**
- [Fact 1: What is known to be true from Jira issue + Issue Understanding]
- [Fact 2: Specific, verifiable behavior or state]
- [Fact 3: Evidence or context]

**Symptoms (what the user reported):**
- [Symptom: observable failure or misbehavior]
- [Impact: how this blocks the user]

**Root cause hypothesis:**
[One-sentence statement: what is broken and why, based on confirmed facts. Should reference a Salesforce component or configuration, not just "bug" or "error".]

**Example:** "Wellvi integration payload construction is missing Order address fields because the Apex callout class is reading from custom CMT mappings that point to nested JSON paths (shippingAddress.city) instead of flat root-level fields (City) that Wellvi's API expects."

---

## Smallest Viable Fix

**What to fix:**
- **Metadata/code artifact:** [Exact component: "Apex class WellviCallout", "Flow MyOrderFlow", "Permission Set XYZ", "Field LedgerAmount__c", etc.]
- **Change scope:** [What specifically changes in that artifact]
- **Why it solves the problem:** [Direct link between root cause and fix]

**Example:**
- **Artifact:** Apex class `PharmacySubmitPrescriptionCallout` (lines 45-67 payload construction)
- **Change:** Update JSON serialization to emit flat top-level fields (City, PostalCode, AddressLine1, StateProvince) instead of nested shippingAddress object
- **Why:** Wellvi API contract expects flat PascalCase fields; current nested structure causes validation failure

---

## Sandbox Validation Plan

**What to test in Sandbox:**
- [Test scenario 1: exact reproduction steps from Jira issue]
- [Test scenario 2: edge case or related functionality]

**Expected outcome:**
- [What should happen after fix is deployed in Sandbox]

**Success criteria:**
- [Boolean: issue is resolved or not]

**Example:**
- Test: Create Order with populated shipping fields, submit to Wellvi via eSubmit action
- Expected: Wellvi HTTP 200 success (not 400 missing-fields error)
- Criteria: Wellvi receives City, PostalCode, AddressLine1, StateProvince in request body

---

## Rollback Plan

**If Sandbox test fails:**
1. [Undo step 1]
2. [Undo step 2]
3. [Fallback action]

**If Production deployment fails:**
1. [Emergency rollback: revert to previous version via Gearset]
2. [Notification: inform team of rollback]
3. [Investigation: post-mortem on why test passed but Production failed]

**Example:**
1. Revert Apex class to previous version via Gearset
2. Notify engineering team and reporter that fix is rolled back pending investigation
3. Review: Compare Sandbox payload vs Production runtime (may have data difference)

---

## Risks and Constraints

**Implementation risks:**
- [Risk 1: potential side effect or breaking change]
- [Risk 2: dependency on other components]

**Constraints:**
- [Constraint 1: e.g., "Cannot modify Wellvi API contract; must match their endpoint spec"]
- [Constraint 2: e.g., "Must not impact other integrations using same CMT"]

**Mitigation:**
- [For each risk, how to reduce impact]

**Example:**
- Risk: Changing payload structure could break other Wellvi endpoints if they also use the same CMT mappings
- Constraint: Wellvi API is external; cannot be changed
- Mitigation: Audit all Wellvi CMT references before deploying; test both prescription and other order types in Sandbox

---

## Production Deploy Readiness

**Sandbox sign-off:** [Name, date: "Fix tested and validated in Sandbox <ORG>. Ready for Production."]

**Production deploy path:** [Gearset / Manual Apex deployment / Configuration-only (no deploy)]

**Rollout plan:** [Immediate / Phased by record type / Scheduled for maintenance window]

**Monitoring after deploy:** [What to watch for in Production; log queries, dashboard monitoring, etc.]
