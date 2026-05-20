# HEAL-33458 Read-Only Validation

Production validation only. No production data was changed.

Validated:

- Example Opportunity exists and is currently owned by Magdalena Toporkiewicz.
- Opportunity was created by Wendy Ellis.
- Opportunity field history shows owner changed from Wendy Ellis to Magdalena Toporkiewicz at creation time.
- `Referred_By__c` was populated with Magdalena Toporkiewicz's Account at creation time.
- Magdalena's Account maps to Magdalena's Salesforce User through `Employee__c`.
- Wendy has Opportunity create/edit access through Nursing Staff.
- Wendy does not have transfer-any-record permission.
- Existing `Transfer_Owners` permission set grants transfer-any-record.
- Existing owner override screen uses `User.Manage_Opportunity_Owner__c`; Wendy's value is currently false.

Result:

- Recommended fix is operational user access, not a metadata deployment.

