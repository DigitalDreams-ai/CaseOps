# HEAL-33369 Sandbox Validation

Sandbox: `10xhealth-sean`

Deployment:

- Status: Succeeded
- Deploy ID: `0AfEa00000ZnLyQKAV`

Validated metadata:

- `Opportunity.Account_Billing_State__c`
- `Opportunity.Account_Main_Practitioner__c`
- `Opportunity_TTS_Report_Field_Access`
- `Mya_s_Reports/Avg_Days_to_Scheduled_NEW`
- `Mya_s_Reports/Avg_Days_to_Scheduled_Clarity_Calls`
- `Mya_s_Reports/Avg_Days_to_Scheduled_PepEx`

Read-back checks:

- FieldDefinition confirmed both formula fields exist.
- Sandbox Opportunity query confirmed `Account_Main_Practitioner__c` returns the Account main practitioner name.
- Report metadata retrieved from sandbox confirmed all three reports include:
  - `Opportunity.Account_Billing_State__c`
  - `Opportunity.Account_Main_Practitioner__c`

Notes:

- A temporary sandbox-only assignment of `Opportunity_TTS_Report_Field_Access` was made to Sean Bingham for SOQL validation.
- No production deployment or production data changes were performed.

