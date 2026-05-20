# Engineering Handoff

## Engineering Message

**Issue:** [KEY] — [one-line summary]
**Problem:** [Simple description of what is broken in Salesforce — written for an Engineer with no prior context]
**Potential Fix:** [Plain description of what likely needs to change — e.g., "Update validation rule X to allow Y when Z condition is met"]

---

## Steps to Reproduce

**Affected record IDs:** [List specific record IDs if applicable]

**Steps:**
1. [Step 1 — include login / user type / Salesforce UI navigation or API call]
2. [Step 2]
3. [Step 3]
4. [Observe: actual behavior — what is broken]

**Expected behavior:** [What should happen instead]

---

## Issue

- Key:
- Summary:
- Reporter:
- Jira status:

## Root Cause

[From investigation: why is this artifact broken? What is wrong with it?]

## Problem Location (from Step 6 investigation)

**Required — Support must identify before escalating.**

### Problem Type
[data / component / config / integration / access / setting / process]

### Specific Artifact
- **Name:** [exact name from Production]
- **API Name (if applicable):** [API name]
- **Type:** [Apex class / Flow / Validation Rule / Permission Set / Field / Org Setting / etc.]

### Location in Production
[Setup path or code path: e.g., "Setup > Object Manager > Order > Fields > ShipToCity", or "Apex class: Namespace.ClassName", or "Flow: Wellvi_eSubmit_Flow"]

### Failure Point
[Where in the flow it breaks. Example: "SOQL SELECT clause at line 45 does not include ShipToCity field."]

## Affected Component

- Metadata/code component: [Same as artifact identified above]
- Element/rule/process, if applicable: [Specific element within the component]

## Potential Fix

[Plain description of what likely needs to change. Do NOT ask Engineering to discover the component. Be specific: 
- "Update Email-to-Case routing address for Cx record type to enable Thread ID matching" 
- NOT "Identify and audit Email-to-Case routing addresses"]

## Production / deploy context (required)

- **Production modified by Support pipeline?:** No (default). This pipeline must not change Production unless the operator explicitly requests it.
- **Does Production already have the proposed metadata?** Yes / No / Unknown — (how verified.)
- **Recommended path to Production (if fix is accepted):** Engineering deploy / Gearset / Not applicable.

## Evidence

- Jira evidence:
- Salesforce record evidence:
- Metadata/log evidence:
- Sandbox evidence, if any:

## References

- Investigation:
- Test report:
- Jira message draft:

## Open Questions

