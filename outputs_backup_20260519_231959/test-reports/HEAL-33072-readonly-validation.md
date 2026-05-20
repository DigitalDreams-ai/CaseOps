# HEAL-33072 Read-Only Validation

## Scope

Production was reviewed read-only. No metadata or data changes were deployed.

## Validated

- Jira issue was retrieved and summarized locally.
- Production Opportunity metadata was retrieved for relevant fields and stage configuration.
- `StageName` is field-history tracked.
- Existing date fields found:
  - `Approved_Date__c`
  - `Transaction_Approval_Date__c`
- No existing submitted-date or rejected-date Opportunity field was found.
- Stage values include:
  - `Waiting For Approval`
  - `Approved`
  - `Rejected`

## Outcome

Recommended solution is a small Salesforce metadata enhancement:

- Add `Submitted_Date__c`.
- Add `Rejected_Date__c`.
- Add before-save Opportunity flow logic to populate those fields from stage changes.

Implementation and sandbox testing were intentionally deferred until the report owner confirms date behavior and whether the existing `Approved_Date__c` field satisfies the approval-date requirement.
