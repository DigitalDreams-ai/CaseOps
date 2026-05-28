# SUP-62 Internal Notes

## Root Cause
Organization uses SAML-delegated authentication with external IdP (Okta/Azure AD). MFA code routing is governed at the IdP level, not within Salesforce; IdP currently routes codes to support team instead of analytics@hennessey.com.

See investigation: `outputs/investigations/SUP-62.md`

## Escalation Decision
**ESCALATED TO ENGINEERING** — High confidence.

**Evidence:**
- Production metadata investigation confirmed SAML-delegated 2FA (Login audit shows "SAML Sfdc Initiated" auth type)
- Analytics users do not exist in Production; no per-user 2FA config discoverable
- Salesforce Setup does not expose 2FA routing controls (setting is at org-security level or disabled for SAML)
- MFA code delivery routing is controlled at IdP level; Support cannot modify IdP policies

## Actions for Operator
1. Coordinate with Engineering team on IdP configuration timeline
2. Provide investigation file (`SUP-62.md`) to Engineering and customer's identity team
3. Offer to create analytics user records in Production once IdP routing is updated (prerequisite step Support can handle)
4. After IdP fix is deployed and verified, Support can run end-to-end login test with analytics@hennessey.com email

## Production vs Sandbox
Escalation only; no Sandbox testing. IdP reconfiguration is cross-system integration work.

## Open Questions for Engineering
- Which IdP is in use (Okta, Azure AD, other)?
- Are analytics users already defined in IdP, waiting to be synced to Salesforce?
- Does MFA delivery policy require custom claim mapping or separate MFA rule for analytics team?
- Timeline for IdP admin to apply routing change?
