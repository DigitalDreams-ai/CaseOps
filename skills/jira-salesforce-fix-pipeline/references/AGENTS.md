# Browser and Magic Link Configuration for CaseOps

This document covers browser setup and Salesforce magic link (frontdoor) management for Production and Sandbox investigation/deployment in the CaseOps pipeline.

---

## Browser Setup

### Chrome Dev Path

CaseOps sub-agents run Salesforce UI investigations in a headless Chrome Dev browser. Configure in `.env.jira`:

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

Magic links are pre-authenticated Salesforce session URLs that allow CaseOps sub-agents to bypass login screens and directly access Production or Sandbox orgs.

**Security:** Magic links are **secrets** equivalent to API keys. Treat them as passwords:
- Store only in `.env.jira` (never in git)
- Rotate regularly (see expiry schedule below)
- Do not share via email or chat
- Use HTTPS URLs only

### Production Magic Link

Used for **read-only Production investigation** (Steps 5, 6 metadata retrieval).

```
CASEOPS_PRODUCTION_MAGIC_LINK=https://10xhealth.my.salesforce.com/secur/frontdoor.jsp?sid=00D0b000000vHFc!AQEAQBx...
```

**How to get:**
1. Log in to Production as admin
2. Click profile menu → **Settings** → **Copy Login URL** (if available)
3. OR manually construct: Production org base URL + `/secur/frontdoor.jsp?sid=<session_id>`
4. Obtain session ID: setup → session management → active session → copy URL
5. Test in private browser: paste URL, should authenticate without login prompt

**Expiry:** Typically 30 days from generation. If sub-agents see login page or 401, link has expired — refresh.

### Sandbox Magic Link

Used for **read-write Sandbox access** (Step 9 deploy/test, full CRUD operations).

```
CASEOPS_SANDBOX_MAGIC_LINK=https://10xhealth--sean.sandbox.my.salesforce.com/secur/frontdoor.jsp?sid=00DEa00000RViur!AQEAQPx...
```

**How to get:**
1. Log in to Sandbox with `CASEOPS_SANDBOX_TARGET_ORG` credentials
2. Click profile menu → **Settings** → **Copy Login URL**
3. OR obtain from setup → session management
4. Test in private browser: paste URL, should authenticate without login prompt

**Expiry:** Typically 30 days. If Step 9 (deploy/test) fails with auth errors, refresh.

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

1. Log out of all Salesforce sessions (clear old magic links)
2. Log in fresh to **Production** as admin
3. Navigate to Setup → Session Management → copy fresh session URL
4. Update `CASEOPS_PRODUCTION_MAGIC_LINK` in `.env.jira`
5. Repeat for Sandbox: log in with `CASEOPS_SANDBOX_TARGET_ORG` user, refresh `CASEOPS_SANDBOX_MAGIC_LINK`
6. **Do NOT commit .env.jira** — it remains gitignored
7. Test: manually visit each URL in a private browser window
8. Alert team: inform about rotation so they know to expect new links if they need to debug sub-agent runs

### Validation After Rotation

```bash
# Quick validation: attempt a curl to the magic link
# (CaseOps sub-agents will do this automatically)
curl -s -o /dev/null -w "%{http_code}" "$CASEOPS_PRODUCTION_MAGIC_LINK" 
# Expected: 200 or 302 (redirect to dashboard)
# If: 401, 403, 404 → link is expired or invalid
```

---

## Sub-Agent Integration

When sub-agents (Steps 5, 6, 9) require Salesforce UI access:

1. **Step 5, 6 (metadata retrieval):** Use `CASEOPS_PRODUCTION_MAGIC_LINK`
   - Read-only: query objects, flows, triggers, permission sets, etc.
   - No modifications to Production

2. **Step 9 (deploy/test):** Use `CASEOPS_SANDBOX_MAGIC_LINK` + `CASEOPS_SANDBOX_TARGET_ORG`
   - Full CRUD: deploy metadata, create test records, modify fields, run tests
   - Mandatory allowlist: only `CASEOPS_SANDBOX_TARGET_ORG` can be modified

3. **Sub-agent failure (auth error):** 
   - Check magic link expiry in `.env.jira`
   - Refresh link if older than 30 days
   - Verify browser path (`CASEOPS_CLAUDE_BROWSER`) exists
   - Re-run sub-agent

---

## Troubleshooting

### Sub-Agent Times Out or Can't Access Salesforce

**Cause:** Browser not found, magic link expired, or network issue

**Fix:**
1. Verify `CASEOPS_CLAUDE_BROWSER` points to valid Chrome Dev executable
2. Refresh magic links (see Rotation Schedule above)
3. Test magic link manually: `curl -s "$CASEOPS_PRODUCTION_MAGIC_LINK" | head -c 200`
   - Should return HTML (dashboard) or redirect headers, not error
4. Check network: `ping salesforce.com`

### 401 / 403 Unauthorized

**Cause:** Magic link expired or session revoked

**Fix:**
- Refresh magic link immediately (see Rotation Schedule)
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
