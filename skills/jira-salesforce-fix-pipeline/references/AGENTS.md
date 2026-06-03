# Browser and Magic Link Configuration for CaseOps

This document covers browser setup and Salesforce magic link (frontdoor) management for visual UI checks in the CaseOps pipeline. Default Salesforce investigation, retrieval, deploy, test, and SOQL access must use `sf` CLI.

---

## Browser Setup

### Chrome Dev Path

CaseOps sub-agents may run Salesforce UI checks in a Chrome Dev browser when visual inspection is necessary. Configure in `.env.jira`:

```
CASEOPS_CLAUDE_BROWSER=C:\Program Files\Google\Chrome Dev\Application\chrome.exe
```

**Windows path examples:**
- Chrome Dev: `C:\Program Files\Google\Chrome Dev\Application\chrome.exe`
- Chrome Stable: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Chromium: `C:\Program Files\Chromium\Application\chrome.exe`

**macOS examples:**
- `/Applications/Google Chrome Dev.app/Contents/MacOS/Google Chrome Dev`
- `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`

**Linux examples:**
- `/usr/bin/google-chrome-dev`
- `/snap/bin/chromium`

Verify the path exists before running sub-agents. Agents will fail with timeout if browser is not found.

---

## Magic Links (Frontdoor Session URLs)

Magic links are pre-authenticated Salesforce browser URLs that allow CaseOps sub-agents to bypass login screens for UI inspection only. They are not API credentials.

**Security:** Magic links are **sensitive browser session secrets**. Treat them as passwords:
- Store only in `.env.jira` (never in git)
- Rotate regularly (see expiry schedule below)
- Do not share via email or chat
- Use HTTPS URLs only

### Production Magic Link

Used only for **read-only visual Production UI inspection** when CLI/SOQL cannot answer the question. Use `sf` CLI for Steps 5 and 6 metadata retrieval.

```
CASEOPS_PRODUCTION_MAGIC_LINK=https://prod-read.my.salesforce.com/secur/frontdoor.jsp?sid=00D0b000000vHFc!AQEAQBx...
```

**How to get:**
1. Log in to Production as an authorized admin.
2. Use the org's supported login URL/session copy process if available.
3. Save the complete frontdoor URL in `.env.jira`.
4. Test in a private browser: paste URL, should authenticate without login prompt.

**Expiry:** Typically 30 days from generation. If sub-agents see a login page in browser UI, link has expired — refresh. Do not use frontdoor SIDs for API `curl` tests.

### Sandbox Magic Link

Used only for **visual Sandbox UI inspection** or UI-only actions. Use `sf project deploy`, `sf data query`, and Apex test commands for Step 9 deploy/test.

```
CASEOPS_SANDBOX_MAGIC_LINK=https://prod-read--sean.sandbox.my.salesforce.com/secur/frontdoor.jsp?sid=00DEa00000RViur!AQEAQPx...
```

**How to get:**
1. Log in to Sandbox with `CASEOPS_SANDBOX_TARGET_ORG` credentials
2. Use the org's supported login URL/session copy process if available
3. Save the complete frontdoor URL in `.env.jira`
4. Test in private browser: paste URL, should authenticate without login prompt

**Expiry:** Typically 30 days. If browser UI checks hit login, refresh. If CLI deploy/test fails with auth errors, fix `sf` CLI auth instead.

### Single Combined Magic Link (Optional)

If your org uses the same login for Production and Sandbox (not recommended):

```
CASEOPS_SALESFORCE_MAGIC_LINK=https://...
```

Set this **instead of** separate PRODUCTION and SANDBOX links. Workflow will use the single link for both.

---

## Rotation Schedule

### When to Rotate

- **Planned:** Every 30 days (aligned with Salesforce session expiry)
- **Emergency:** After staff turnover, suspected compromise, or login failure
- **Proactive:** When any administrator updates their password

### How to Rotate

1. Log out of stale Salesforce sessions if needed
2. Log in fresh to **Production** as admin
3. Generate or copy a fresh browser login URL using the org's supported process
4. Update `CASEOPS_PRODUCTION_MAGIC_LINK` in `.env.jira`
5. Repeat for Sandbox: log in with `CASEOPS_SANDBOX_TARGET_ORG` user, refresh `CASEOPS_SANDBOX_MAGIC_LINK`
6. **Do NOT commit .env.jira** — it remains gitignored
7. Test: manually visit each URL in a private browser window
8. Alert team: inform about rotation so they know to expect new links if they need to debug sub-agent runs

### Validation After Rotation

Validate by opening the link in Chrome Dev or a private browser window. Do not use the SID as an Authorization bearer token for Salesforce API calls.

---

## Sub-Agent Integration

When sub-agents (Steps 5, 6, 9) require Salesforce access:

1. **Step 5, 6 (metadata retrieval):** Use `sf` CLI + SOQL with `CASEOPS_PRODUCTION_READ_ORG`
   - Read-only: query objects, flows, triggers, permission sets, etc.
   - No modifications to Production
   - Open `CASEOPS_PRODUCTION_MAGIC_LINK` only for visual UI confirmation

2. **Step 9 (deploy/test):** Use `sf` CLI + `CASEOPS_SANDBOX_TARGET_ORG`
   - CLI deploy/test: deploy metadata, create test records, modify fields, run tests
   - Mandatory allowlist: only `CASEOPS_SANDBOX_TARGET_ORG` can be modified
   - Open `CASEOPS_SANDBOX_MAGIC_LINK` only for visual UI confirmation or UI-only actions

3. **Sub-agent failure (auth error):**
   - For API/SOQL/metadata/deploy/test failures, fix `sf` CLI auth first
   - For visual UI failures, check `CASEOPS_CLAUDE_BROWSER` and magic link expiry
   - Re-run sub-agent after the correct auth path is fixed

---

## Troubleshooting

### Sub-Agent Times Out or Can't Access Salesforce

**Cause:** `sf` CLI auth missing/expired, browser not found for a visual-only step, magic link expired, or network issue

**Fix:**
1. Verify `sf org list` includes `CASEOPS_PRODUCTION_READ_ORG` and `CASEOPS_SANDBOX_TARGET_ORG`
2. Verify `CASEOPS_CLAUDE_BROWSER` points to valid Chrome Dev executable if visual UI is required
3. Refresh magic links only for browser UI failures
4. Test magic link manually by opening it in Chrome Dev or a private browser
5. Check network: `ping salesforce.com`

### 401 / 403 Unauthorized

**Cause:** For CLI/API work, Salesforce CLI auth is missing or expired. For browser-only UI checks, the magic link expired or the session was revoked.

**Fix:**
- Refresh Salesforce CLI tokens for API/SOQL/metadata/deploy/test failures
- Refresh magic link only for visual browser UI failures
- Log in to Salesforce directly to confirm credentials are valid
- If Sandbox: verify CASEOPS_SANDBOX_TARGET_ORG user still exists and has required permissions

### Browser Process Hangs or Crashes

**Cause:** Chrome Dev version mismatch, insufficient disk space, or port conflict

**Fix:**
- Verify Chrome Dev is up-to-date: `chrome --version`
- Check disk space: `df -h` (Unix) or `Get-Volume` (PowerShell)
- Kill stray browser processes: `pkill chrome` (Unix) or `Stop-Process -Name chrome` (PowerShell)
- Re-run sub-agent

---

## Best Practices

1. **Rotate magic links monthly** — set a calendar reminder
2. **Never share `.env.jira`** — it contains secrets
3. **Use private/incognito browser tabs** for manual magic-link testing
4. **Log out immediately** after admin investigations — don't leave sessions open
5. **Restrict admin account access** — only CaseOps-authorized administrators should hold admin credentials
6. **Monitor session management** — regularly review active sessions in Setup → Session Management

---

## References

- Salesforce Security: https://help.salesforce.com/s/articleView?id=sf.security_general.htm
- Session Management: Setup → Session Management (Production/Sandbox)
- Browser requirements: Chrome 90+, headless mode compatible
