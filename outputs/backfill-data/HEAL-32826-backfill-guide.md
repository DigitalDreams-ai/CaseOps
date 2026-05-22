# HEAL-32826 Backfill Execution Guide

**Issue:** PAM Informed Consent Cases for Shopify Orders  
**Scope:** 54 affected accounts (3/18–3/27 window)  
**Status:** Ready for Production backfill  
**Date Prepared:** 2026-05-22

---

## Summary

Shopify MGT/GHT orders created between 3/18–3/27/2026 did not receive "Informed Consent 2026" assignment due to a temporary integration failure in the Shopify→SF order sync automation. A fix was deployed on 3/27 that restored forward-looking assignment for post-3/27 orders.

**Action required:** Backfill missing "Informed Consent 2026" records to 41 affected accounts in the 3/18–3/27 window.

**Scope note:** Some accounts may have older Informed Consent records (pre-2026 versions) but lack the required current-year version. The flow checks "if Informed Consent 2026 already exists" before creating; it will skip accounts that already have the 2026 version.

---

## Affected Accounts

**Total:** 41 accounts  
**Date range:** Shopify orders created 3/18–3/27/2026  
**Filter:** Accounts with Shopify (Store) orders that do NOT have Patient_Agreement__c with Name LIKE '%2026%'  
**Data source:** Production SOQL query (read-only verified 2026-05-22)  
**File:** `HEAL-32826-affected-accounts.csv`

**Note:** 54 total Shopify orders exist in window; 41 lack the 2026 Informed Consent version. Some of the 41 may have older Informed Consent versions but still need 2026 added.

---

## Backfill Method

### Option 1: Batch via "Assign patient agreements" (Recommended)

If a bulk action or custom flow wrapper exists in Production:

1. Use "Assign patient agreements" quick action or custom button on Account list
2. Select all 54 accounts from `HEAL-32826-affected-accounts.csv`
3. Invoke action → Patient_Agreement__c records created with:
   - Consent_Type__c = "Explicit Consent"
   - Status__c = "Sent"
   - Creation_Source__c = "Salesforce"
   - Dispatch_Platform__c = auto-set by flow logic

### Option 2: Salesforce Flow (if bulk action unavailable)

Invoke `Autolaunch_Send_Patient_Agreements_to_Patient` for each account:

**Flow Details:**
- **API Name:** Autolaunch_Send_Patient_Agreements_to_Patient
- **Type:** Auto-launched flow (requires manual invocation)
- **Input parameters:**
  - `rec_Account` (required): Account ID
  - `col_PatientAgreementConfigurtion` (required): Collection with one item: `a5URh000000FDY1MAO` (Informed Consent configuration)

**Execution (pseudocode):**
```
FOR EACH accountId IN HEAL-32826-affected-accounts.csv:
  INVOKE Autolaunch_Send_Patient_Agreements_to_Patient
    rec_Account = accountId
    col_PatientAgreementConfigurtion = [{ Id: a5URh000000FDY1MAO }]
  VERIFY Patient_Agreement__c created with Status__c = "Sent"
END
```

### Option 3: Direct DML (Not recommended)

If Options 1–2 unavailable, create Patient_Agreement__c records directly (loses duplicate prevention logic):

**Template:**
```
FOR EACH accountId IN affected accounts:
  INSERT new Patient_Agreement__c(
    Patient__c = accountId,
    Consent_Type__c = 'Explicit Consent',
    Status__c = 'Sent',
    Creation_Source__c = 'Salesforce',
    Dispatch_Platform__c = 'Salesforce' (or from Account.Biocanic_External_Id__c logic)
  )
END
```

---

## Configuration Reference

**Patient_Agreement_Configuration__c (Informed Consent):**
- **Record ID:** a5URh000000FDY1MAO
- **Name:** "Informed Consent"
- **Consent_Type__c:** "Explicit Consent"
- **Status:** ACTIVE in Production

---

## Verification Checklist

After backfill execution:

- [ ] All 41 accounts have Patient_Agreement__c records with 2026 version created
- [ ] Each record Name contains "2026" (e.g., "Informed Consent_2026")
- [ ] Each record has Consent_Type__c = "Explicit Consent"
- [ ] Each record has Status__c = "Sent"
- [ ] Creation_Source__c = "Salesforce"
- [ ] No duplicate records created (flow has duplicate-prevention logic; safe to skip if 2026 already exists)
- [ ] Dispatch_Platform__c set correctly for Chrono downstream sync
- [ ] No errors in flow execution logs

**Verification query:**
```soql
SELECT COUNT() FROM Patient_Agreement__c 
WHERE Patient__c IN (
  SELECT Id FROM Account 
  WHERE Id IN (<41 account IDs from HEAL-32826-affected-accounts.csv>)
)
AND Name LIKE '%2026%'
AND Status__c = 'Sent'
AND CreatedDate >= 2026-05-22T00:00:00Z
```

**Expected result:** 41 records (minimum; may be more if duplicates created)

---

## Risks & Mitigation

| Risk | Mitigation |
| --- | --- |
| Duplicate records if re-run on same account | Flow has duplicate prevention; safe to re-invoke |
| Chrono sync does not process backfilled consents | Monitor Dispatch_Platform__c field; Chrono sync is listener-based |
| Missing accounts not captured in query | Query is definitive from Production; process all 54 listed |
| Consent status mismatch with forward-looking records | All new records set to Status__c = "Sent" to match post-3/27 behavior |

---

## Production vs Sandbox

| Environment | Role | Deploy Required? |
| --- | --- | --- |
| Production | Backfill execution (data remediation only) | N/A |
| Sandbox | Optional: test on cloned account before bulk | No (validation only) |
| Metadata | No changes needed (Informed Consent config already exists) | No |

---

## Next Steps

1. **Execute backfill** using Option 1, 2, or 3 above
2. **Verify** with checklist above
3. **Monitor** Chrono sync for 24 hours post-backfill
4. **Close Jira issue** with backfill completion comment
5. **Archive** backfill execution logs and this guide in CaseOps outputs

---

## Contacts & Approvals

- **Issue Owner:** Sean Bingham (CaseOps)
- **Backfill Approval:** Sean Bingham (confirmed safe 2026-05-22)
- **Downstream (Chrono):** Monitor via Dispatch_Platform__c field for sync confirmation

