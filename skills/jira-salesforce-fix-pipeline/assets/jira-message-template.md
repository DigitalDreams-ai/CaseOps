# Jira Message Draft — [ISSUE KEY]

**CUSTOMER-FACING — POSTED TO JIRA**

This message will be posted as a public comment on the Jira issue. The reporter and stakeholders will see it. For internal-only memo, use `outputs/internal-notes/<KEY>.md` instead.

<!-- Choose the block that matches the outcome. Delete the other. -->

<!-- ── CONFIRMED FIX ─────────────────────────────────────────── -->
Hi [Name],

I investigated and resolved this issue in Sandbox.

**Root cause:**

**What was changed:**

**Production vs Sandbox (required — pick one wording and delete the rest):**

- **Deploy required:** The fix was **validated in Sandbox only**. **Production has not been updated** by this work. **[Operator: promote these changes to Production via Gearset (or your standard path) — e.g. metadata: …]**
- **No deploy:** **No Production metadata deployment is required** for this fix because … **(e.g. the permission set already exists in Production; issue was assignment/access/data.)**
- **N/A:** **No metadata change** — …

Do **not** say “add a permission set” without clarifying whether that component **already exists in Production** or **only exists in Sandbox until deploy**.

**Sandbox validation:**
- Sandbox:
- Steps tested:
- Result:

**Next steps:**

Thanks.

---

<!-- ── ENGINEERING ESCALATION ────────────────────────────────── -->
Hi [Name],

I investigated this issue. It requires an Engineering change and has been escalated.

**Problem:**

**What needs to change:**

**Evidence:**

**Escalation notes:**

Thanks.
