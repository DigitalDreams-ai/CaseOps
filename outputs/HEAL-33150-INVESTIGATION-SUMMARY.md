# HEAL-33150 Investigation Summary

**Issue:** Cx Case Record Response - replies missing from Case activity  
**Status:** Root cause refined after file review and read-only Production validation  
**Date:** 2026-05-20

## Executive Summary

The strongest supported root cause is that the affected internal approval replies are bypassing Salesforce. The outbound Case email includes a Salesforce thread token, but the Outlook reply path sends the response back to the agent and/or shared Outlook recipients rather than to a Salesforce Email-to-Case routing address. Salesforce cannot attach an inbound reply it never receives.

This corrects the earlier investigation language. The evidence does not support a broad "Customer Experience record type has no Email-to-Case threading" conclusion. Production has Customer Experience cases where inbound replies attach correctly when the reply is delivered to routed addresses such as `support@10xhealthsystem.com` or `info@10xhealthsystem.com`.

## Production Findings

- Cx Case record type exists: `Customer_Experience`.
- Affected sample Case: `500Ql00000ujeSTIAY` / `00565984`.
- Salesforce logged the outbound internal approval email from the Case.
- Salesforce did not log an inbound approval reply for that Case.
- Later outbound customer email exists on the same Case with the same thread identifier.
- Nearby Cx refund cases show successful `Incoming = true` replies when addressed to Salesforce-routed mailboxes.
- The prior "38 Email-to-Case addresses" statement was inaccurate. The 38 active `EmailServicesAddress` records include many per-user Email-to-Salesforce addresses; the Case routing service has only the relevant routed local parts such as `patientdocs`, `support`, and `tech-dataopps`.

## Root Cause

The internal approval email workflow does not force replies back through Salesforce. Thread token matching is available, but the reply must first be delivered to a Salesforce-routed Email-to-Case address. In the affected screenshots, the reply appears to stay in Outlook because the visible recipients are human/shared mailboxes.

## Smoking Gun

The exact action is `Case.SendEmail` on the `Case-Customer Experience` layout. Its metadata exposes editable `ValidatedFromAddress` and has no predefined sender/Reply-To override. The affected email was sent with:

- `FromAddress = ntorres@10xhealthsystem.com`
- `ValidatedFromAddress = ntorres@10xhealthsystem.com`
- `EmailTemplateId = null`
- `EmailRoutingAddressId = null`
- `ToAddress = tjones@10xhealthsystem.com`
- `BccAddress = ntorres@10xhealthsystem.com`

That is the source of the problem. The internal approval email is being sent as the agent, not as a Salesforce-routed case mailbox.

## Corrective Direction

Engineering/Admin should audit the Cx internal approval email workflow:

1. Change or replace `Case.SendEmail` for internal approvals so the sender/reply path is Salesforce-routed.
2. Configure replies to route to Salesforce, either by using a Salesforce-routed Reply-To/From address or forwarding the shared approval/refund mailbox to Email-to-Case.
3. Validate in Sandbox that an Outlook reply creates an incoming `EmailMessage` on the original Cx Case.

## Production vs Sandbox

- Production read-only validation: Completed.
- Production writes/deploys by this investigation: None.
- Sandbox validation: Not yet performed.
- Production deploy/config required: Likely, after Sandbox validation. The exact path depends on whether the fix is email action/template metadata, Setup configuration, or mailbox forwarding.

## Files Updated

- `outputs/investigations/HEAL-33150.md`
- `outputs/engineering-escalations/HEAL-33150.md`
- `outputs/internal-notes/HEAL-33150.md`
- `outputs/jira-messages/HEAL-33150.md`
