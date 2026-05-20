# HEAL-32826 Read-Only Validation

## Scope

Read-only Production validation for historical Shopify/PAM Informed Consent failures.

## Commands/Checks

- Synced Jira issue `HEAL-32826`.
- Queried example Case `500Ql00000tN0qrIAC`.
- Queried account `001Ql00000vm6ogIAA` Patient Agreement records.
- Counted generated Cases with subject containing `MissedConsentFormGeneration`.
- Retrieved relevant Production flow metadata:
  - `Record_Trigger_Patient_Agreement_Update_Consent`
  - `Autolaunch_Send_Patient_Agreements_Product_Based`

## Results

- Example Case contains Salesforce failure text for `Record Trigger - Patient Agreement - Update Consent`.
- Example account now has `Informed Consent_2026`.
- `248` matching Cases exist from `2026-03-18` through `2026-03-27`.
- `0` matching Cases found from `2026-03-28` through `2026-04-07`.
- Retrieved flow metadata confirms the active triggered consent update flow exists as version 2 and was modified on `2026-03-27`.

## Outcome

Pass for investigation. No sandbox deployment was needed because no new metadata change is recommended from this issue as currently stated.
