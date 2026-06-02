# CaseOps Enhancement Plan

This is the current pilot hardening backlog. It does not describe completed runtime behavior unless marked complete.

## Complete

- Docker/NAS deployment with bind-mounted `app.py`, `templates/`, `static/`, `skills/`, and `scripts/`.
- Salesforce token auth through Settings and active env file.
- Claude Code OAuth token through Settings.
- Persistent canned-message customizations under `outputs/settings/`.
- Pipeline log copy support.
- Real-time `STEP_N` progress markers.
- ANSI/control-code cleanup in logs.
- Salesforce access-token redaction in logs.
- Org knowledge seeding and topic selection.
- General Salesforce gotcha seed files.
- Deterministic Salesforce helper script.
- Modern `sf` CLI-only retrieve/deploy rule.

## Pilot Hardening

1. Metadata storage hybrid
   - Complete: new work uses `outputs/metadata-cache/` and `outputs/metadata-workspaces/`.
   - Remaining: add UI/API review of workspace manifests and optional cleanup/archive tools.

2. Org-knowledge review workflow
   - Current: file-based updates are possible.
   - Target: proposed lessons, approve/edit/reject in Settings, changelog.

3. Runtime status split
   - Current: Settings status should return quickly.
   - Target: separate deep preflight for slower Salesforce/Claude checks.

4. Pipeline efficiency
   - Continue reducing repeated Salesforce CLI learning.
   - Prefer helper scripts and selected org knowledge.
   - Keep sub-agent summaries compact.

5. Docker image size
   - Review npm/global installs and apt packages.
   - Keep appdata out of the image.

## Not Current

- Salesforce MCP replacement is not implemented.
- Automatic Production deployment is not implemented.
- Automatic Jira posting is not the default.
