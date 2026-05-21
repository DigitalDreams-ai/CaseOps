# HEAL-33753 — Pipeline Status: Diagnostic Complete, Implementation Blocked

**Date:** 2026-05-21  
**Issue:** HEAL-33753 — Create workflow for email to send scheduling link for AHB consults  
**Status:** Waiting for customer input

---

## Completed Steps

- **Step 1–2:** Jira sync and triage ✓
- **Step 3:** Issue analysis ✓
- **Step 4:** Problem hypothesis ✓
- **Step 5:** Production metadata retrieval ✓
- **Step 6:** Problem location identification ✓
- **Step 7:** Escalation gate decision ✓

**Decision:** Support-resolvable (no Engineering escalation required)

---

## Current Blocker

**Step 8 (Implementation) is blocked:** Requires customer-provided Calendly event URL before Sandbox implementation can proceed.

**What we need:** 
- Calendly event booking URL for AHB Hormone Consults (format: `https://calendly.com/d/xxx-xxx-xxx`)
- Confirmation that the event exists in Calendly admin account

**Customer message:** Jira draft at `outputs/jira-messages/HEAL-33753.md` requests this URL explicitly.

---

## Resumption Plan

Once Calendly URL is provided by customer (Ashlee Edwards or Sarah Phonthaphanh):

1. **Step 8** (Orchestrator): Update email template `00XQl000005kQavMAE` with the provided URL. Populate Product2 field.
2. **Step 9** (Sub-agent `salesforce-sandbox-deploy-test`): Deploy to allowlisted Sandbox, test new opportunity creation triggers email with correct Calendly link.
3. **Step 10** (Sub-agent `jira-response-drafting`): Finalize Jira message with test results. Finalize internal notes with Production deployment decision.
4. **Step 11:** Generate dated summary.
5. **Step 12:** Report completion status to user.

---

## Files Ready for Implementation

- **Investigation:** `outputs/investigations/HEAL-33753.md` — complete with Problem Location (Step 6)
- **Jira draft:** `outputs/jira-messages/HEAL-33753.md` — ready to post (awaiting customer response)
- **Internal notes:** `outputs/internal-notes/HEAL-33753.md` — ready (will be refined after Step 9)

---

## Production vs Sandbox

**In Production (read-only verified):**
- Email template `00XQl000005kQavMAE` exists (placeholder body, no Calendly URL)
- Product2 "At-Home Blood Test: Hormone Panel Consultation" exists with Calendly link populated
- `Calendly_Email_Template_Id__c` field is NULL (missing linkage)
- Dispatcher flow `Record_Trigger_After_Save_Send_Genetic_Breakthrough_Schedule_Link` active and waiting for template ID

**Sandbox deployment:** Two fixes needed (see investigation for exact field paths):
1. Email template body: Insert Calendly URL with prefill params
2. Product2 field: Set `Calendly_Email_Template_Id__c = 00XQl000005kQavMAE`

**Production deploy required:** **Yes** — both email template and Product2 changes must reach Production (via Gearset or equivalent)

---

## Next Action

Await customer reply in Jira with Calendly URL. Once received, reply to this status file and resume Step 8.
