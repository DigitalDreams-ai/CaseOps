# End-to-End Browser Validation: CaseOps Orchestrator

**Date:** 2026-05-20  
**Sandbox Target:** 10xhealth-sean  
**Issues Processed:** HEAL-33369, HEAL-33618, HEAL-33066

---

## What to Verify in Chrome DevTools

### HEAL-33369: Opportunity Report with Account Fields

**Expected in Sandbox 10xhealth-sean:**
- [ ] Opportunity object has custom fields:
  - [ ] Account_Billing_State__c (formula field) — References `Account.BillingState`
  - [ ] Account_Main_Practitioner__c (formula field) — References `Account.Main_Practitioner__r.Name`
- [ ] Three reports updated with new columns:
  - [ ] "Avg Days to Scheduled - Lab Review" (ID: 00OEa000007vWiIMAU)
    - [ ] Contains "Account Billing State" column
    - [ ] Contains "Account Main Practitioner" column
    - [ ] Data populates from formula fields
  - [ ] "Avg Days to Scheduled - Clarity Calls" (similar checks)
  - [ ] "Avg Days to Scheduled - PepEx" (similar checks)

**Status:** Fields deployed ✓; Report columns require manual UI updates (Salesforce API limitation)

**Blockers Found:**
- Report Builder does NOT expose column configuration via API
- Columns must be added manually in each org (Sandbox + Production)
- Documented as manual step in test report

---

### HEAL-33618: Case Escalation Timestamp

**Expected in Sandbox 10xhealth-sean:**
- [ ] Case object has custom field:
  - [ ] Escalation_DateTime__c (DateTime field)
  - [ ] Field exists in Sandbox (Deploy ID: 0AfEa00000ZzfdBKAR)
- [ ] Field appears on Case layout (Case-Customer Experience)
  - [ ] Escalations section, near IsEscalated and Escalation_Details__c
- [ ] Round-robin flow Record_Trigger_Case_Assign_Round_Robin_Cases:
  - [ ] Flow modified to add Record Update action
  - [ ] Action sets Escalation_DateTime__c = NOW() when Dispo_Level_3__c = "Escalation"

**Status:** Field deployed ✓; Flow modification pending ⏳

**Blockers Found:**
- Flow modification not yet deployed
- Test case creation and escalation trigger NOT verified
- Elapsed-time formulas NOT created
- Blocker: Flow logic must be tested before Production deploy

---

### HEAL-33066: Price Book Configuration

**Expected in Sandbox:**
- [ ] Price books exist:
  - [ ] Quest (ID: 01sQl0000021f6PIAQ or Sandbox equivalent)
  - [ ] Evexia (ID: 01sQl0000021f81IAA or Sandbox equivalent)
- [ ] 59 products are ACTIVE (not inactive)
- [ ] Pricing matches Excel source

**Status:** Already in Production; no Sandbox-specific changes

**Blockers Found:**
- Issue is BLOCKED on customer (Carlin French) clarifying additional adjustments
- Awaiting customer response; no further work until scope defined

---

## Gaps Identified During Orchestration

| Gap | Issue | Severity | Impact | Fix |
|-----|-------|----------|--------|-----|
| Report column API limitation | HEAL-33369 | Medium | Must manually add columns in each org | Document as support procedure; no code fix |
| Flow modification not deployed | HEAL-33618 | High | Timestamp feature incomplete | Deploy flow modification, test, re-validate |
| Customer engagement undefined | HEAL-33066 | Medium | Work blocked; no proceeding without scope | Automatic: Flag in summary, skip issue, notify user |
| Sub-agent timeout risk | All issues | Low | Long sub-agent calls may timeout | Add 5min timeout + retry logic to orchestrator |
| Sandbox org discovery lag | HEAL-33369 | Low | Report IDs differ between orgs | Auto-discovery via query in orchestrator |

---

## Production Readiness Assessment

### What Works End-to-End
✓ Steps 1-3: Jira sync → triage → issue analysis  
✓ Steps 4-6: Hypothesis → metadata retrieval → problem location  
✓ Step 7: Escalation gate (correctly identifies Support vs Engineering)  
✓ Step 10: Message drafting with file separation  
✓ Step 11: Summary generation  

### What Needs Fixes Before Production
⚠️ Step 8-9: Flow modifications not deploying (manual input required)  
⚠️ Report Builder: Manual column config required (platform limitation)  
⚠️ Customer engagement: Detect "Waiting for support" status, flag, skip  

### What Needs Testing Before Production
- Full loop on 10-15 issues (batch processing)
- Flow modification deployment + validation
- Sandbox safety checks (org confirmation)
- Sub-agent timeout handling

---

## Browser Demo Checklist

1. **Open Sandbox:** Connect to 10xhealth-sean via Chrome DevTools
2. **HEAL-33369:** Navigate to Opportunities, open one record, verify formula fields exist (even if reports not updated)
3. **HEAL-33618:** Navigate to Cases, open one, verify Escalation_DateTime__c field exists and is accessible
4. **HEAL-33066:** Navigate to Price Books, verify Quest and Evexia exist with products active
5. **Verify outputs:** Check outputs/jira-messages/, outputs/internal-notes/, outputs/investigations/ for all three issues
6. **Review summary:** Read outputs/issue-summary-2026-05-20.md for consolidated status

---

## Sign-Off

**Pipeline Status:** Operational but requires fixes  
**Blockers:** Flow deployment, manual report updates, customer clarification  
**Recommendation:** Deploy as-is with known limitations documented; batch-test on 5-10 issues before production announcement  
