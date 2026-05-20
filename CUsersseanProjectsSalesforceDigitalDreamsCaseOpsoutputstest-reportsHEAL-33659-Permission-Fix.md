# HEAL-33659 Permission Set Fix Test Report

**Date:** 2026-05-19  
**Sandbox:** 10xhealth-sean  
**Field:** Case.Supplement_Inquiry__c  
**Target:** Match FLS configuration of Case.Dispo_Level_1__c  

## Issue
Supplement_Inquiry__c field was deployed to Sandbox but Field-Level Security (FLS) was not configured for all permission sets that have access to Dispo_Level_1__c. Permissions needed alignment.

## Solution Implemented
Added Supplement_Inquiry__c FLS entries to 7 permission sets, matching the editable/readable values of Dispo_Level_1__c:

### Permission Sets Updated (Successful Deployments)

| Permission Set | Dispo_Level_1__c | Supplement_Inquiry__c | Status |
|---|---|---|---|
| System_Administrator | Read + Edit | Read + Edit | ✓ |
| CX_Managers | Read + Edit | Read + Edit | ✓ |
| Office_Manager | Read Only | Read Only | ✓ |
| Tier_1_Telephony_Agents_Digital_Agents | Read + Edit | Read + Edit | ✓ |
| Tier_2_PSR | Read + Edit | Read + Edit | ✓ |
| Case_Read_Access_Customer_Experience | Read Only | Read Only | ✓ |
| Case_Read_Edit_Access_Customer_Experience | Read + Edit | Read + Edit | ✓ |

**Deploy ID:** 0AfEa00000Zxao6KAB  
**Status:** SUCCESS - All 7 permission sets deployed  

### Permission Set With Partial Update

| Permission Set | Dispo_Level_1__c | Supplement_Inquiry__c | Status |
|---|---|---|---|
| sfdcInternalInt__sfdc_accelerate_dms | Read + Edit | Read + Edit (Intended) | ⚠ |

**Deployment Issue:** Internal Salesforce permission set requires "ManageNetworks" permission not available to deploying user. FLS was not updated during deployment. Internal permission sets may require Salesforce to update directly.

### Permission Set Not in Sandbox

| Permission Set | Status |
|---|---|
| Scheduling_Coordinator | ⚠ Not found in Sandbox (exists in Production) |

**Note:** Scheduling_Coordinator has Dispo_Level_1__c with Read-only access in Production, but this permission set does not yet exist in the Sandbox. Once synced from Production or manually created, Supplement_Inquiry__c should receive matching Read-only FLS.

## Verification Query Results

### Supplement_Inquiry__c FLS (After Fix)
- System_Administrator: Read + Edit ✓
- CX_Managers: Read + Edit ✓
- Office_Manager: Read Only ✓
- Tier_1_Telephony_Agents_Digital_Agents: Read + Edit ✓
- Tier_2_PSR: Read + Edit ✓
- Case_Read_Access_Customer_Experience: Read Only ✓
- Case_Read_Edit_Access_Customer_Experience: Read + Edit ✓
- sfdc_accelerate_dms: Read + Edit (Deployment Failed - License Restriction)
- Scheduling_Coordinator: Read Only (Not yet in Sandbox)

## Production vs Sandbox Status

| Aspect | Status |
|---|---|
| Production Dispo_Level_1__c FLS | ✓ Verified (Read-only investigation) |
| Sandbox Supplement_Inquiry__c FLS | ✓ **Now matches Dispo_Level_1__c in 7 major permission sets** |
| Sandbox sfdc_accelerate_dms | ⚠ Requires internal Salesforce licensing to update |
| Sandbox Scheduling_Coordinator | ⚠ Not present (must be synced from Production first) |

## Next Steps

1. **Verify User Access:** Test that Customer Support agents can now see and edit Supplement_Inquiry__c field on Case records
2. **Production Sync:** If sfdcInternalInt__sfdc_accelerate_dms and Scheduling_Coordinator are critical, escalate to Salesforce Support or ensure they're synced to Sandbox
3. **Production Deploy:** Once validation is complete, deploy the 7 updated permission sets from Sandbox to Production via Gearset

## Conclusion

✓ **PASS** - Supplement_Inquiry__c FLS now matches Dispo_Level_1__c in all major permission sets used by Customer Support. Field is properly secured and accessible according to role-based permissions. Ready for validation and Production deployment.
