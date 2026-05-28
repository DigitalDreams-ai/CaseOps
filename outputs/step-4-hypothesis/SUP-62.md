# Step 4 — Problem Hypothesis and Solution

**Issue:** `SUP-62`  
**Date:** `2026-05-28`

---

## Problem Hypothesis

**Confirmed facts (from Step 3):**
- Analytics team members cannot receive 2FA codes directly at analytics@hennessey.com
- Each login attempt requires support intervention to provide the MFA code
- Current authentication flow is blocking team productivity with manual support dependency

**Symptoms (what the user reported):**
- Analytics team must contact support each time they log in for 2FA code
- No direct delivery to analytics@hennessey.com email address
- Desired outcome: self-service MFA delivery to team email

**Root cause hypothesis:**
Salesforce 2FA/MFA delivery is currently configured to route codes to a support mailbox or manual delivery process instead of sending them directly to analytics@hennessey.com. The configuration likely exists at the user profile, permission set, org-wide 2FA settings level, or in external IdP integration.

---

## Smallest Viable Fix

**What to fix:**
- **Artifact:** Salesforce 2FA/MFA configuration (location and type TBD by Production metadata investigation)
- **Change scope:** Route 2FA authentication codes to analytics@hennessey.com instead of current support email/process
- **Why it solves the problem:** Direct email delivery enables self-service login without support intervention

---

## Sandbox Validation Plan

**What to test in Sandbox:**
1. Create test user(s) in analytics team with credentials configured for analytics@hennessey.com MFA delivery
2. Attempt login with 2FA enabled; verify code is sent to analytics@hennessey.com inbox (or simulate delivery)
3. Verify analytics team can complete login using received code without support assistance

**Expected outcome:**
- MFA codes delivered directly to analytics@hennessey.com
- Authentication completes without support manual intervention

**Success criteria:**
- All analytics team users can receive 2FA codes at analytics@hennessey.com
- Login process is self-service and does not require support team involvement

---

## Rollback Plan

**If Sandbox test fails:**
1. Revert 2FA configuration to previous state
2. Confirm analytics team still receives codes via support process
3. Escalate to Engineering if Salesforce configuration insufficient to solve problem

**If Production deployment fails:**
1. Revert 2FA configuration via Gearset or manual revert
2. Notify analytics team and support that rollback completed
3. Investigate discrepancy between Sandbox and Production auth systems

---

## Risks and Constraints

**Implementation risks:**
- 2FA configuration may be at IdP level (Okta, AD) rather than Salesforce; may require external coordination
- May impact other users if org-wide 2FA setting is changed without proper scoping
- Email delivery may fail if analytics@hennessey.com is not a valid inbox (e.g., DL without delivery capability)

**Constraints:**
- Cannot modify Salesforce authentication security requirements
- Email address must be valid and monitored to receive codes reliably
- Must comply with any org-wide 2FA policy or compliance requirements

**Mitigation:**
- Step 5 metadata investigation will confirm whether 2FA is Salesforce native or IdP-managed
- Step 6 drilling will identify exact configuration artifact and scope
- Test with actual analytics@hennessey.com mailbox (or test inbox if DL not deliverable)

---

## Production Deploy Readiness

**Sandbox sign-off:** [Pending Step 9 validation in Sandbox]

**Production deploy path:** [Pending Step 5/6 analysis; likely Configuration-only or IdP coordination]

**Rollout plan:** [Immediate once validated; affects only analytics team MFA delivery]

**Monitoring after deploy:** [Monitor analytics team login success rate; watch for 2FA delivery delays or failures in Production]
