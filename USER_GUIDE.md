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
1. First authenticate Salesforce orgs locally:
   ```bash
   sf org login web --alias 10xhealth
   sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com
   ```
2. Get access tokens:
   ```bash
   sf org auth show-access-token -o 10xhealth --json
   sf org auth show-access-token -o 10xhealth-sean --json
   ```
   Copy each `result.accessToken`.
3. Get refresh-token source URLs:
   ```bash
   sf org auth show-sfdx-auth-url -o 10xhealth --json
   sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
   ```
   Copy each `result.sfdxAuthUrl`. CaseOps accepts the full SFDX auth URL and extracts the refresh token.
4. Go to `http://localhost:5350/setup/refresh-salesforce-tokens`
5. Paste Prod access, Prod SFDX auth URL, Sandbox access, and Sandbox SFDX auth URL
6. Click **"Save & Refresh Tokens"**
7. Tokens auto-refresh every 4 hours from now on

### Manual Refresh (If Needed)
1. Authenticate orgs locally (if not already done):
   ```bash
   sf org login web --alias 10xhealth
   sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com
   ```
2. Get current tokens:
   ```bash
   sf org auth show-access-token -o 10xhealth --json
   sf org auth show-access-token -o 10xhealth-sean --json
   ```
3. Navigate to `http://localhost:5350/setup/refresh-salesforce-tokens`
4. Copy each `result.accessToken` into the form
5. Click submit

### Token Refresh Timeline (Without Refresh Tokens)
| Time | Status | Action |
|------|--------|--------|
| 0-4h | ✅ Valid | Pipeline works freely |
| 4-8h | ⚠️ Warning | Auto-refresh attempted at startup |
| 8h+ | ❌ Expired | Tokens fail; pipeline blocked |

### Where Tokens Are Stored
- **Local:** Salesforce CLI auth cache, usually `~/.sf/` for current `sf` CLI versions; some older installations also use `~/.sfdx/`
- **Container:** `/app/.env.jira` (refreshed by startup script)
- **NAS:** `/volume1/docker/stacks/caseops/.env.jira.nas` (persistent)

---

## Issue Workflows

### Workflow 1: Automatic Investigation (Full Pipeline)

**Click: "Auto-Process All"**

Both Support-resolvable and Engineering-escalation issues follow **the same Steps 1-12**. The difference is the Step 10 outcome: Support-resolvable issues produce a Sandbox-validated package ready for operator-controlled Production promotion, while Engineering-escalation issues produce an Engineering handoff with a Sandbox-validated proposed solution. CaseOps does not deploy to Production.

| Step | What Happens | Time | Output |
|------|-------------|------|--------|
| 1-2 | Sync + Triage from Jira | 3 min | `jira/` folder; issues classified by status |
| 3 | Analysis (per issue) | 3 min | Root cause understanding |
| 4 | Hypothesis | 2 min | `step-4-hypothesis/HEAL-*.md` with proposed fix |
| 5-6 | Metadata Investigation | 3 min | Problem location identified (artifact, type, location, failure point) |
| 7 | Escalation Gate | 1 min | Decide: Support-resolvable or Engineering-required |
| 8 | Implement | 1 min | Propose local code changes (both paths) |
| 9 | Sandbox Test | 3 min | Deploy proposed fix to Sandbox, test, validate; save `test-reports/HEAL-*.md` |
| 10 | Customer Message | 1 min | `jira-messages/HEAL-*.md` + `internal-notes/HEAL-*.md` + (if escalating) `engineering-escalations/HEAL-*.md` with proposed solution |
| 11-12 | Summary + Report | 2 min | `issue-summary-YYYY-MM-DD.md` + completion output |

**Total:** ~18 minutes per issue; ~25 minutes for batch of 25 issues (both paths run full pipeline; proposed solutions provided to Engineering for escalations).

**Watch progress:** Click issue to see real-time investigation log.

### Salesforce Metadata Workspace

CaseOps keeps raw metadata, test attempts, and confirmed packages separate:

| Purpose | Path |
| --- | --- |
| Raw Production metadata, read-only | `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/` |
| Sandbox test attempts | `${CASEOPS_METADATA_SANDBOX_WORK_DIR}/<KEY>/attempt-N/` |
| Confirmed Support package | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/support-owned/` |
| Confirmed Engineering proposal | `${CASEOPS_METADATA_CONFIRMED_DIR}/<KEY>/engineering-proposal/` |

Failed or abandoned Sandbox attempts must be reverted from the captured `baseline-sandbox/` before another candidate is tested.

### Workflow 2: Manual Case-by-Case

**Click issue in sidebar → Click "Settings" (⚙)**

Available actions:
- **Investigate** — Run issue analysis and investigation steps
- **Propose Fix** — Build or refine the hypothesis and metadata scope
- **Test in Sandbox** — Deploy and validate the proposed fix in the allowlisted Sandbox
- **Draft Message** — Generate internal notes and customer-facing draft

Each action saves output to the issue-specific folders under `outputs/`.

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
**A:** Only if your Salesforce CLI session was created by `sf org login web`. Run:
```bash
sf org auth show-sfdx-auth-url -o 10xhealth --json
```
If `result.sfdxAuthUrl` is missing, you'll need to re-authenticate:
```bash
sf org login web --alias 10xhealth
```

### Q: What if I lose my Claude Code token?
**A:** Generate and save a new one:
1. Run `claude setup-token` on your local machine
2. Go to `/setup/claude-login`
3. Paste only the token printed by the command
4. CaseOps saves it as `CLAUDE_CODE_OAUTH_TOKEN`

### Q: Can the pipeline run without Salesforce tokens?
**A:** No. Steps 5-7 require Salesforce API access. Steps 1-4 (sync, triage, analysis, hypotheses) can run without SF access, but pipeline will stop at Step 5.

### Q: How do I check if tokens are valid?
**A:** Tokens are automatically checked at startup. If expired:
- App warns in logs but continues (with auto-refresh if refresh tokens available)
- Pipeline preflight blocks Salesforce work if the `sf` CLI cannot access the configured Production and Sandbox orgs
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
- Investigations use `sf` CLI and SOQL for read-only metadata and data checks
- Magic links/frontdoor links are visual UI fallback only, not API authentication
- All fixes tested in Sandbox first
- Operator-controlled Production promotion is required outside CaseOps
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

### Deploy Local Updates to NAS
For pilot deployments, CaseOps bind-mounts `app.py`, `templates/`, `static/`, and `skills/` from `/volume1/docker/stacks/caseops`.

- App, UI, CSS, or skill/playbook changes: sync local files to the NAS stack folder, then restart `caseops`.
- Dockerfile, dependency, Claude CLI, Salesforce CLI, or OS package changes: sync local files, rebuild the image, then restart `caseops`.
- Verify the running container after restart; do not rely only on the files in the NAS stack folder.

### Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| "Salesforce tokens EXPIRED" | 8h+ since last refresh | Refresh tokens via Settings |
| "Claude Code auth token not configured" | Claude token missing or expired | Run `claude setup-token`, then save it in `/setup/claude-login` |
| "Sandbox deploy failed" | Metadata conflict | Check test-report for details |
| "Pipeline stalled" | Jira API unreachable | Check .env.jira JIRA_* settings |

---

## Next Steps

- See [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) for architecture details
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design
- See [INSTANCE_ROUTING.md](INSTANCE_ROUTING.md) for instance isolation and metadata workspace rules
- See [skills/jira-salesforce-fix-pipeline/references/workflow.md](skills/jira-salesforce-fix-pipeline/references/workflow.md) for the authoritative pipeline workflow
