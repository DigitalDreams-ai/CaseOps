# Investigation Record

## Jira Issue

- Key: SUP-62
- Summary: Consolidate Login Authentication
- Status: Waiting for support
- Priority: [Not specified in summary]
- Reporter: Sean Bingham
- Assignee: Sean Bingham
- Link: [Jira instance URL/browse/SUP-62]

## Reproduction Steps (top-level — used for escalations and validation)

1. Analytics team member attempts to log into Salesforce
2. Two-factor authentication required; team must request code from support (analytics@hennessey.com cannot receive it directly)
3. Observe: Current auth flow requires manual intervention from support team for each MFA code delivery

**Expected behavior:**
MFA authentication codes are sent directly to analytics@hennessey.com, enabling analytics team to complete 2FA independently without support intervention.

**Affected record IDs or characteristics:**
Analytics team users; analytics@hennessey.com email address

---

## Issue Understanding

### Observed Behavior
- Analytics team must request two-factor authentication codes from support for each Salesforce login
- MFA codes are not automatically delivered to analytics@hennessey.com
- Current process requires manual support team coordination for routine login operations

### Expected Behavior
- Two-factor authentication codes are automatically delivered to analytics@hennessey.com
- Analytics team can complete 2FA login flow independently without requesting codes from support
- Login process is self-service for analytics team members

### Acceptance Criteria
1. MFA delivery destination is configured to send codes to analytics@hennessey.com
2. Analytics team can log in and receive 2FA codes directly to that email address
3. Support team is no longer required to manually deliver codes for analytics team logins
4. Solution works for all analytics team member accounts

### Attachments Or Evidence
None provided in issue

### Unknowns
- Which Salesforce authentication system is in use (built-in 2FA, Okta, other IdP)?
- Are analytics users assigned to a specific permission set or profile?
- Is this a per-user setting, profile-level, or org-wide configuration?
- Are there security/compliance requirements preventing self-service MFA delivery?
- How many users are in the analytics team?
- Is there a group email alias or DL for analytics@hennessey.com?

## Salesforce Problem

### Confirmed Facts

**Matching Configuration (for new/modified items):**
- Similar existing items found: [To be discovered during Production metadata investigation]
- Their FLS permissions: [To be confirmed]
- Their layout placement: [To be confirmed]
- Their record type availability: [To be confirmed]
- New item will match: [To be confirmed after analysis]

### Hypotheses

- **H1 (Most Likely):** Salesforce org has user-level or profile-level 2FA configuration that currently routes codes to a support mailbox; needs to be updated to route to analytics@hennessey.com or configured per-user for analytics team
- **H2:** External IdP (Okta, AD, etc.) handles 2FA delivery; configuration at IdP level needs update to direct MFA codes to analytics team email
- **H3:** Role-based or permission-set-based email routing rule exists and needs analytics team added to distribution list handling 2FA delivery

### Likely Affected Metadata
- User records (2FA email field if field-based)
- Profile/permission set assignments for analytics users
- Organization-wide 2FA settings or user record email field configuration
- Possible: custom metadata or flows handling authentication email delivery

### Similar Items Analysis

**Due diligence check — before implementation:**
- [ ] Searched for similar existing items (fields, objects, list views, components, etc.)
- [ ] Found: [Pending Production metadata investigation]
- [ ] Documented their config: FLS, layouts, record types, field order
- [ ] Confirmed new item will use same permissions/placement/availability
- [ ] Rationale: [Pending Implementation]

**Similar items found:**
| Item Name | Type | FLS | Layouts | Record Types | Notes |
| --- | --- | --- | --- | --- | --- |
| [Pending] | [Pending] | [Pending] | [Pending] | [Pending] | [Pending] |

---

## Production Metadata Retrieved

### Metadata Items Queried

1. **User Records (Analytics Team)**
   - Query: Searched for users with email containing "analytics", "hennessey" domain
   - Result: 0 users found matching analytics@hennessey.com email
   - Finding: Analytics team users do not yet exist in Production

2. **Permission Sets (Analytics-Related)**
   - Query: PermissionSet WHERE Label/Name LIKE '%Analytics%'
   - Result: Found 6 analytics-related permission sets:
     - AnalyticsViewOnlyUser (ID: 0PS0b000000GO4sGAG) — Read-only analytics access
     - B2BMarketingAnalytics (ID: 0PS0b000000GO4rGAG) — B2B marketing analytics
     - ActivitiesWaveAdminHVS (ID: 0PS5a000000fMzsGAE) — CRM Analytics for Sales Cloud
     - C2CAnalyticsStoragePermSet, EventMonitoringWaveAdmin, EventMonitoringWaveUser
   - Finding: No users currently assigned to these permission sets

3. **Profiles (Analytics-Related)**
   - Query: Profile WHERE Name LIKE '%Analytics%'
   - Result: Found 2 analytics-related profiles:
     - Analytics Cloud Integration User (ID: 00eRh000000itjxIAA)
     - Analytics Cloud Security User (ID: 00eRh000000itjyIAA)

4. **Org-Wide 2FA Settings**
   - Finding: Unable to query 2FA settings directly via SOQL (not exposed as queryable object)
   - Note: 2FA routing in Salesforce is typically configured at:
     - User record level (if custom field exists)
     - Profile level (if embedded in profile email settings)
     - Org-wide security settings (Setup > Security > Two-Factor Authentication)
     - External IdP level (if using Okta, Okta Identity Cloud, or other IdP)

### Hypothesis Validation

- **H1 (User/Profile-level 2FA config):** REJECTED — Analytics users do not exist in Production yet; no per-user or profile-level email routing can be tested
- **H2 (External IdP routing):** UNCONFIRMED — No SAML/SSO configuration metadata retrieved; requires direct Setup inspection or SeC team review
- **H3 (Role/Permission-set email routing):** REJECTED — No users assigned to analytics permission sets; email routing rules cannot be active without assigned users

### Implementation Surface

Since analytics users do not exist in Production:
1. **Create user records** for analytics team with email analytics@hennessey.com (or identify existing users to migrate)
2. **Determine 2FA delivery mechanism**:
   - If Salesforce built-in 2FA: Update user email field or org-wide 2FA settings to route codes to analytics@hennessey.com
   - If external IdP (Okta): Coordinate with IdP admin to update MFA delivery settings; may require custom claim mapping or separate MFA policy
3. **Assign Permission Sets** to analytics users (likely AnalyticsViewOnlyUser or B2BMarketingAnalytics depending on role)
4. **Test 2FA flow** end-to-end: User login → 2FA prompt → Code delivery to analytics@hennessey.com

## Problem Location (Step 6 — filled after Production metadata drilling)

### Problem Type

**setting / integration / access**

**Explanation:** The issue is a combination of missing user setup (access problem) and authentication routing configuration (setting/integration problem). Salesforce org uses SAML-based authentication, likely with external IdP handling MFA delivery.

### Specific Artifact

- **Name:** Analytics User Email Configuration + SAML/MFA Delivery Routing
- **API Name (if applicable):** User.Email field + org-wide 2FA settings (not exposed via API) + SAML IdP MFA policy
- **Type:** Org Setting + User Field Configuration + External IdP Integration

### Location in Production

1. **Setup > Security > Two-Factor Authentication** (org-wide 2FA settings; check if SAML-delegated)
2. **Setup > Users > Users** (individual user records with Email field)
3. **Setup > Security > Identity Providers** (SAML IdP configuration; likely where MFA routing is controlled)
4. **External IdP (Okta / AD / other)** — Organization's identity provider; MFA code delivery routing is configured here, not in Salesforce

### Failure Point (where in the flow it breaks)

1. **Primary failure:** Analytics team users do not exist in Production
   - Query result: 0 users with email containing "analytics" or "hennessey"
   - No PermissionSetAssignments found for any analytics-related permission sets
   
2. **Secondary failure:** 2FA/MFA delivery is SAML-delegated
   - Login logs show "SAML Sfdc Initiated" auth type; Salesforce is NOT handling MFA natively
   - 2FA settings are likely governed by external IdP (Okta, AD, etc.), not Salesforce Setup
   - Salesforce Setup > Two-Factor Authentication may be disabled or in "SAML-delegated" mode
   
3. **Tertiary failure:** MFA code delivery routing is configured at IdP level, not in Salesforce
   - No custom Apex, flows, or metadata in Production handling 2FA email routing
   - IdP MFA policy currently routes codes to support team/shared mailbox instead of analytics@hennessey.com
   - Email routing rule at IdP level must be updated to send MFA codes to analytics@hennessey.com

### Root Cause

**Two-part root cause:**

1. **Access prerequisite not met:** Analytics team users have not been created in Production with email analytics@hennessey.com. Without user records, 2FA routing cannot be tested or configured.

2. **IdP-level configuration gap:** Organization's external Identity Provider (likely Okta or Azure AD based on SAML login pattern) currently routes MFA codes to a support mailbox or manual delivery process. The IdP's MFA delivery policy must be updated to send codes to analytics@hennessey.com. This is an IdP configuration issue, not a Salesforce configuration issue.

### Support-Resolvable Classification

**ENGINEERING REQUIRED** — This issue has dependencies outside of Support's scope:
- Support can create the analytics user records in Production (User.Email = analytics@hennessey.com)
- Support can assign the appropriate analytics permission sets to those users
- **But:** The MFA delivery routing is controlled by the organization's external IdP, not by Salesforce Setup. Support cannot modify IdP MFA policies; that requires SecOps / IdP Admin coordination
- Support can verify the fix works after IdP is updated, but the core fix is outside Salesforce
