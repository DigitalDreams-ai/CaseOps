# CaseOps User Guide

## Table of Contents
1. [Dashboard Overview](#dashboard-overview)
2. [Token Management](#token-management)
3. [Issue Workflows](#issue-workflows)
4. [Pipeline Operations](#pipeline-operations)
5. [Issue Details & Actions](#issue-details--actions)
6. [Escalation & Handoff](#escalation--handoff)
7. [Mobile Usage](#mobile-usage)
8. [FAQ](#faq)

---

## Dashboard Overview

The CaseOps dashboard displays all active support issues in stages of the investigation pipeline.

### Top Navigation Bar
- **☰ Issues** (mobile) — Toggle sidebar visibility
- **CaseOps logo** — Click to return to overview
- **Status indicator** — Green = idle, Yellow/Red = processing
- **Run buttons:**
  - **Sync New Issues** — Fetch only new cases from Jira
  - **Fetch from Jira** — Sync all active cases
  - **Prepare Issues** — Run through triage (Step 2)
  - **Auto-Process All** — Full pipeline (Steps 1-12)
- **Overview** — Show dashboard statistics
- **⚙ Settings** — Token & credential management

### Sidebar Issue List
Issues grouped by **pipeline state**:
- **Untriaged** — New issues, not yet analyzed
- **Investigating** — Analysis in progress
- **Analyzed** — Root cause found, awaiting testing
- **Validated** — Tested and confirmed working
- **Escalated to Engineering** — User-approved for handoff

Each issue shows:
- **Issue key** (e.g., HEAL-30437)
- **Summary** (first 50 chars)
- **Status badge** (from Jira: "In Progress", "Blocked", etc.)
- **Pipeline state** (colored indicator)
- **Secondary badges:**
  - Data Only — Fix requires no metadata changes
  - Needs Escalation — Pipeline determined escalation needed
  - Escalated to Eng — User explicitly escalated in Jira

### Issue Cards (Desktop)
Click an issue to view:
- Full summary
- Investigation findings
- Proposed fix
- Sandbox test results
- Customer-facing message draft
- Export/escalation options

---

## Token Management

### Why Tokens Expire
Salesforce access tokens have an **8-hour TTL** (time-to-live). After 8 hours, you must refresh them or the pipeline cannot access Salesforce.

### Auto-Refresh (Recommended)
If you provide **refresh tokens**, CaseOps automatically:
- Checks token age at startup
- Refreshes at the **4-hour mark** (before expiry)
- Updates tokens in `.env.jira`
- Continues running without interruption

**To enable auto-refresh:**
1. Go to `http://localhost:5350/setup/refresh-salesforce-tokens`
2. Get both **access tokens** AND **refresh tokens**:
   ```bash
   # On your authenticated local machine
   sf org auth show-access-token -o 10xhealth --no-prompt
   # (get both tokens from .sfdx/sbingham@10xhealthsystem.com.json)
   ```
3. Paste access tokens in "Prod (10xhealth)" and "Sandbox (10xhealth-sean)"
4. Paste refresh tokens in "Refresh" fields (optional but recommended)
5. Click **"Save & Refresh Tokens"**
6. Tokens auto-refresh every 4 hours from now on

### Manual Refresh (If Needed)
1. Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens`
2. Run locally:
   ```bash
   sf org auth show-access-token -o 10xhealth --no-prompt
   sf org auth show-access-token -o 10xhealth-sean --no-prompt
   ```
3. Copy the access token values into the form
4. (Optional) Get refresh tokens and paste those too
5. Click submit

### Token Refresh Timeline (Without Refresh Tokens)
| Time | Status | Action |
|------|--------|--------|
| 0-4h | ✅ Valid | Pipeline works freely |
| 4-8h | ⚠️ Warning | Auto-refresh attempted at startup |
| 8h+ | ❌ Expired | Tokens fail; pipeline blocked |

### Where Tokens Are Stored
- **Local:** `~/.sfdx/` directory (sf CLI cache)
- **Container:** `/app/.env.jira` (refreshed by startup script)
- **NAS:** `/volume1/docker/stacks/caseops/.env.jira.nas` (persistent)

---

## Issue Workflows

### Workflow 1: Automatic Investigation (Full Pipeline)

**Click: "Auto-Process All"**

| Step | What Happens | Time | Output |
|------|-------------|------|--------|
| 1-2 | Sync + Triage from Jira | 3 min | `jira/` folder; issues classified by status |
| 3 | Analysis (per issue) | 3 min | Root cause understanding |
| 4 | Hypothesis | 2 min | `step-4-hypothesis/HEAL-*.md` with proposed fix |
| 5-6 | Metadata Investigation | 3 min | Problem location identified (exact artifact, type, location) |
| 7 | Escalation Gate | 1 min | Decide: Support-resolvable or Engineering-required |
| 8-9 | Sandbox Implementation + Test | 5 min | Deploy fix, test, validate; save `test-reports/HEAL-*.md` |
| 10 | Customer Message | 1 min | `jira-messages/HEAL-*.md` + `internal-notes/HEAL-*.md` + `engineering-escalations/` (if needed) |
| 11-12 | Summary + Report | 2 min | `issue-summary-YYYY-MM-DD.md` + completion output |

**Total:** ~20 minutes for 25 issues.

**Watch progress:** Click issue to see real-time investigation log.

### Workflow 2: Manual Case-by-Case

**Click issue in sidebar → Click "Settings" (⚙)**

Available actions:
- **Investigate** — Run Step 3 (analysis) on this issue only
- **Propose Fix** — Run Steps 4-5 (hypothesis + metadata)
- **Test in Sandbox** — Run Step 6 (deploy + validation)
- **Draft Message** — Run Step 7 (customer response)

Each action saves output to `outputs/HEAL-*.md` files.

### Workflow 3: Re-Investigate (After Fix Fails)

**Issue tested but fix didn't work?**

1. Click issue
2. Note failure reason in investigation
3. Click **"Re-Investigate"** (restarts Step 3 with new hypothesis)
4. Pipeline generates alternative fix proposal

---

## Pipeline Operations

### Monitor Pipeline Progress

**During execution:**
- Status bar at top shows "Processing"
- Click issue to see live investigation log
- Logs stream in real-time (refresh every 2 sec)

**After completion:**
- Status returns to "Idle"
- Badge updates show progress
- Logs available in `pipeline-logs/__global__.jsonl`

### Check Pipeline Logs

**Via dashboard:**
1. Click issue
2. Scroll to "Logs" section
3. View formatted, searchable pipeline output

**Via filesystem (SSH):**
```bash
ssh docker@10.0.1.10
tail -f /volume1/docker/stacks/caseops/instance1/outputs/pipeline-logs/__global__.jsonl
```

### Stop/Pause Pipeline

**Not currently supported.** Pipeline runs to completion. If you need to stop:
- SSH to container: `docker exec caseops /bin/bash`
- Kill the Claude process: `pkill -f claude`
- Restart: `docker-compose restart caseops`

---

## Issue Details & Actions

### Issue Detail Panel

Click an issue to open the detail view:

#### Top Section
- **Issue key** (e.g., HEAL-30437)
- **Summary** — Full text from Jira
- **Badges** — Pipeline status badges
- **Jira link** — Click to open in Jira

#### Investigation Tab
**Root cause analysis** generated by Claude:
- Problem description (from Jira + context)
- Salesforce configuration findings
- Root cause hypothesis
- Recommended fix

#### Internal Notes Tab
**Engineering-facing notes:**
- Technical details
- Data validation results
- Deployment considerations
- Known risks/workarounds

#### Test Report Tab
**Sandbox testing results:**
- Deployment status (success/failed)
- Test cases executed
- Data validation passed/failed
- Performance impact
- Customer impact assessment

#### Message Tab
**Draft customer-facing response:**
- Explanation of fix (non-technical)
- When it will be available
- Any customer action needed
- Follow-up instructions

#### Settings Tab
- **Change Jira status:** Escalate, close, reopen
- **Add tags:** Flag for follow-up
- **Re-investigate:** Start analysis over
- **Export:** Download all artifacts

---

## Escalation & Handoff

### When to Escalate

An issue needs escalation when:
- Pipeline determines it requires **engineering involvement** (file-based flag)
  - Badge: "📋 Needs Escalation"
  - Action: Manually escalate in Jira
- User explicitly marks in Jira
  - Badge: "🔀 Escalated to Engineering"
  - Issue moves to engineering-escalations folder

### How to Escalate

**Option 1: Auto-flagged**
- Pipeline creates `outputs/engineering-escalations/HEAL-*.md`
- Review the **Eng Handoff** file
- Click issue → Settings → Status: "Escalated to Engineering"

**Option 2: Manual**
- Click issue → Settings → Status → Select "Escalated to Engineering"
- Issue moves to escalated list
- Summary auto-generated for handoff

### Handoff Process

1. **Generate Summary**
   - Click "Generate Escalation Summary"
   - Creates comprehensive handoff document
   - Includes: investigation, hypotheses, risks, test results

2. **Export Files**
   - Click "Download All" to zip investigation files
   - Share with engineering team
   - Include links to Sandbox test results

3. **Tag in Jira**
   - Update status to "Escalated to Engineering"
   - Add comment with CaseOps summary
   - Link to test results/investigation

---

## Mobile Usage

### Mobile Layout Changes
- **Sidebar hidden by default** (tap ☰ Issues to show)
- **Action buttons in dropdown menu** (tap ⋮ for Sync/Process/etc.)
- **Filter pills collapsible** (tap "Filters ▾" to expand)
- **Touch-friendly buttons** (44px+ height for fingers)

### Mobile Workflows

**Investigate an issue:**
1. Tap ☰ Issues to show sidebar
2. Tap issue name
3. Sidebar auto-closes, detail panel opens
4. Scroll to read investigation
5. Tap ⚙ Settings to escalate

**Run pipeline:**
1. Tap ⋮ menu
2. Tap "Auto-Process All"
3. Tap status indicator to watch progress
4. Close and refresh to see updates

**Refresh tokens:**
1. Tap ⚙ Settings
2. Scroll to "Salesforce Tokens"
3. Tap "Refresh Tokens"
4. Opens modal with token input fields

---

## FAQ

### Q: How long do tokens last?
**A:** 8 hours. Without refresh tokens, you must manually refresh every 8 hours. With refresh tokens, CaseOps auto-refreshes at 4 hours.

### Q: Can I get refresh tokens?
**A:** Only if your Salesforce CLI session has them. Run:
```bash
cat ~/.sfdx/sbingham@10xhealthsystem.com.json | grep refreshToken
```
If no refresh token field, you'll need to re-authenticate:
```bash
sf org login web --alias 10xhealth
```

### Q: What if I lose my Claude credentials?
**A:** They're persisted in the container. If lost:
1. Go to `/setup/claude-login`
2. Follow the 3-step wizard
3. Credentials saved automatically
4. Container restart will restore them

### Q: Can the pipeline run without Salesforce tokens?
**A:** No. Steps 5-7 require Salesforce API access. Steps 1-4 (sync, triage, analysis, hypotheses) can run without SF access, but pipeline will stop at Step 5.

### Q: How do I check if tokens are valid?
**A:** Tokens are automatically checked at startup. If expired:
- App warns in logs but continues (with auto-refresh if refresh tokens available)
- Pipeline will fail at Step 8-9 if Salesforce tokens required but invalid
- Go to **Settings** → **Refresh Salesforce Tokens** to manually refresh

### Q: Can I have multiple instances?
**A:** Yes! CaseOps supports multi-instance via isolated output directories:
- `instance1/outputs/` (default)
- `instance2/outputs/` (separate outputs, tokens, state)

Each instance runs in a separate Docker container with its own `CASEOPS_WORKSPACE` env var. Configure via docker-compose overrides or separate .env files per container.

### Q: How do I export investigation results?
**A:** Click issue → Settings → **"Download All"**. Gets:
- `investigation.md`
- `internal-notes.md`
- `test-report.md`
- `jira-message.md`
- Full file hierarchy as ZIP

### Q: What happens if a pipeline step fails?
**A:** 
- Step stops, logs show error
- Previous steps' outputs preserved
- You can re-run that step alone
- Or re-investigate with fresh hypothesis

### Q: Is Production data modified?
**A:** **Never.** CaseOps has **read-only** access to Production Salesforce:
- Investigations only query metadata + data
- All fixes tested in Sandbox first
- Manual approval required for Production changes
- Audit trail logged in escalation docs

---

## Support & Debugging

### Check Container Logs
```bash
ssh docker@10.0.1.10
docker logs -f caseops
```

### Restart Service
```bash
ssh docker@10.0.1.10
cd /volume1/docker/stacks/caseops
docker-compose restart caseops
```

### Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| "Salesforce tokens EXPIRED" | 8h+ since last refresh | Refresh tokens via Settings |
| "Claude credentials not found" | Claude not authenticated | Run /setup/claude-login |
| "Sandbox deploy failed" | Metadata conflict | Check test-report for details |
| "Pipeline stalled" | Jira API unreachable | Check .env.jira JIRA_* settings |

---

## Next Steps

- See [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) for architecture details
- See [references/](references/) for detailed specs
- Check [ARCHITECTURE_STRATEGY.md](ARCHITECTURE_STRATEGY.md) for pipeline design
