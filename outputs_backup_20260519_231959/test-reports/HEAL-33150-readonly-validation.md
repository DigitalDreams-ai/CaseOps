# HEAL-33150 Read-Only Validation

## Scope

Read-only Production validation for Customer Experience Case email reply attachment behavior.

## Commands/Checks

- Synced Jira issue `HEAL-33150` with attachments.
- Reviewed screenshots to identify Opportunity `006Ql00000a2CpxIAE`.
- Queried related Account Cases.
- Identified Customer Experience Case `500Ql00000ujeSTIAY`.
- Queried `EmailMessage` records on that Case.
- Queried related refund-thread EmailMessages in Production for comparison.

## Results

- The example outbound Salesforce email includes the thread token.
- The example Case has no incoming EmailMessage for the Outlook/Teams reply shown in screenshots.
- Other refund threads do show inbound replies attached when the replies are sent to monitored routing addresses.

## Outcome

Pass for investigation. No sandbox deployment needed. Recommended fix is email routing/reply-to workflow or configuration, not code.
