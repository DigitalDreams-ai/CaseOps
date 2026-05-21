# Internal Notes — [ISSUE KEY]

**INTERNAL ONLY — DO NOT POST TO JIRA**

This file is Sean's internal memo. It is NOT posted to the Jira issue or customer. For customer-facing message, use `outputs/jira-messages/<KEY>.md` instead.

**Reference:** See `outputs/investigations/<KEY>.md` for full problem diagnosis, Salesforce configuration, and similar items analysis.

---

## Status

[One-line summary: what is the current state of this issue?]

## Root Cause

[Why is this happening (if defect) or why is it resolved (if completed)? Diagnosis only — not a replay of what happened in Investigation. Be terse.]

## Decision

**Support-Resolvable** OR **Escalate to Engineering**

[Confidence level + key evidence for this decision.]

---

## If Support-Resolvable: Actions Taken

[What was done to resolve. Include:]
- [Action 1 with ID/date if applicable]
- [Action 2]
- [Approvals/sign-offs if applicable]

## If Escalating: Engineering Handoff

- Reason for escalation:
- Affected metadata/component:
- Reproduction steps (terse, as reference to Investigation):
- Proposed approach:
- Evidence:

---

## Production vs Sandbox (required)

**Rule:** Never state or imply Production was changed unless the operator explicitly deployed. Sandbox validation ≠ Production has the change.

- **Verified in Production (read-only):** [What exists or doesn't exist in Prod]
- **Changed/created in Sandbox only:** [What was tested in Sandbox]
- **Production deployment required?** [Yes — exact steps / No — uses existing Prod config / N/A]
- **Operator action:** [Concrete next step for operator]

---

## Risks

[Brief list of operational or technical risks, if any. One line per risk.]

## Next Action

[What operator does immediately.]
