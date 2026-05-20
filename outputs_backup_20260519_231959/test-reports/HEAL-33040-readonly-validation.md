# HEAL-33040 Read-Only Validation

## Scope

Read-only Production validation for Account-to-Shopify sync failure.

## Commands/Checks

- Synced Jira issue `HEAL-33040`.
- Queried Account `001Ql00000x8VCkIAM`.
- Queried Opportunity records for the Account.
- Queried Admin Flags for the Account.
- Queried Nebula log entries for the Account.
- Retrieved relevant Production flow metadata:
  - `Record_Trigger_Account_Account_Sync_To_External_Systems`
  - `Autolaunch_Account_Sync_To_External_Systems`

## Results

- Account has no Shopify customer ID, sync message, or shop URL.
- `TRIG_SHOPIFY_SYNC__c` is true.
- Admin Flags identify missing address data.
- Nebula logs confirm the Account sync flow ran and invoked the external sync path.
- No sandbox deployment was performed because no local metadata change is recommended.

## Outcome

Pass for investigation. Recommended remediation is data correction plus manual sync retrigger. If the retrigger still fails, escalate to downstream external sync service ownership.
