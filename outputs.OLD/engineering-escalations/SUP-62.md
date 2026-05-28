# Engineering Handoff — SUP-62

## Engineering Message

**Issue:** SUP-62 — Consolidate Login Authentication  
**Problem:** Analytics team requires manual support intervention for each 2FA login because MFA codes are not being routed to analytics@hennessey.com. The routing is controlled at the external Identity Provider level (Okta/Azure AD), not within Salesforce.  
**Potential Fix:** Configure the organization's external Identity Provider (IdP) to route MFA authentication codes to analytics@hennessey.com instead of the current support mailbox. Coordinate with SecOps or IdP Admin to update the MFA delivery policy.

---

## Steps to Reproduce

**Affected users:** Analytics team members (email domain @hennessey.com)

**Steps:**
1. Log in to Salesforce as an analytics team member (currently no active users exist)
2. Enter credentials; system prompts for 2FA
3. Expected: MFA code delivered to analytics@hennessey.com
4. Observed: MFA codes not delivered to analytics@hennessey.com; team must contact support for code

**Expected behavior:** Analytics team receives 2FA codes automatically at analytics@hennessey.com and can complete login independently.

---

## Issue

- **Key:** SUP-62
- **Summary:** Consolidate Login Authentication
- **Reporter:** Sean Bingham (analytics team)
- **Jira status:** Waiting for support

## Root Cause

Organization uses SAML-delegated authentication with an external Identity Provider (Okta, Azure AD, or similar). MFA code delivery routing is configured at the IdP level, not within Salesforce. The IdP is currently routing codes to a support team mailbox instead of analytics@hennessey.com. This is a cross-system integration configuration issue, not a Salesforce-only problem.

## Problem Location (from Step 6 investigation)

### Problem Type
Setting + Integration

### Specific Artifact
- **Name:** SAML MFA Delivery Routing Policy
- **Type:** Identity Provider configuration (external to Salesforce)
- **Scope:** Affects analytics team user login flow

### Location in Production
- **Salesforce side:** Setup > Security > Identity Providers (SAML configuration is visible in Salesforce)
- **External:** Organization's Identity Provider control panel (Okta Admin Console, Azure AD, etc.) — OUTSIDE Salesforce

### Failure Point
MFA code delivery routing policy at IdP level routes authentication codes to support team mailbox instead of target analytics@hennessey.com address. This occurs during the IdP-initiated SAML login flow, before Salesforce processes the authentication.

## Affected Component

- **Metadata/code component:** External SAML Identity Provider MFA delivery policy
- **In Salesforce:** SAML Identity Provider configuration (read-only visibility in Setup > Security > Identity Providers)
- **Engineering scope:** Cross-system integration; IdP coordination required

## Potential Fix

1. **Engineering + SecOps coordination:** Identify the organization's external Identity Provider (IdP administrator/console details already verified as SAML/Okta or Azure AD based on login logs)
2. **IdP Policy Update:** Modify the MFA delivery routing policy to route authentication codes to analytics@hennessey.com instead of support team mailbox
3. **Salesforce side (Support scope):** Create analytics user records in Salesforce with email analytics@hennessey.com and assign appropriate permission sets (AnalyticsViewOnlyUser, B2BMarketingAnalytics, etc.)
4. **Validation:** Test end-to-end login flow with MFA code delivery to analytics@hennessey.com

## Production / deploy context (required)

- **Production modified by Support pipeline?:** No. This escalation documents Engineering work only. Support may create user records and assign permission sets (if that is Support-owned), but MFA routing reconfiguration is Engineering/SecOps responsibility.
- **Does Production already have the proposed metadata?** Unknown — SAML Identity Provider configuration is external to Salesforce. Requires IdP Admin review.
- **Recommended path to Production (if fix is accepted):** Engineering + SecOps coordination; no Gearset deployment needed (IdP-level change, not Salesforce metadata change).

## Evidence

- **Jira evidence:** SUP-62 issue details from analytics team request
- **Salesforce record evidence:** No analytics users exist in Production (User query returned 0 results); Permission Sets exist (AnalyticsViewOnlyUser, B2BMarketingAnalytics) but have no assignments
- **Metadata/log evidence:** SAML authentication confirmed in Production login logs (SAML Sfdc Initiated); no custom Apex or Flow handling MFA routing in Salesforce codebase
- **Investigation record:** outputs/investigations/SUP-62.md (full Issue Understanding, Production Metadata Retrieved, Problem Location analysis)

## References

- **Investigation:** outputs/investigations/SUP-62.md
- **Step 4 Hypothesis:** outputs/step-4-hypothesis/SUP-62.md
- **Jira issue:** SUP-62

## Open Questions

1. **Which IdP?** Okta, Azure AD, or other? (Suspected based on SAML logs, needs confirmation)
2. **Current MFA routing destination?** What support mailbox or process is currently receiving codes?
3. **analytics@hennessey.com:** Is this a group email (DL) or individual user mailbox? Must support direct email delivery.
4. **Support scope for user creation:** Does Support own creating analytics user records, or should Engineering do this as part of the fix?
5. **Compliance/security constraints:** Are there org-wide 2FA policies or compliance requirements that restrict who can receive MFA codes?

---

**Escalated to Engineering:** 2026-05-28  
**Status:** Awaiting Engineering + SecOps review and IdP configuration update
