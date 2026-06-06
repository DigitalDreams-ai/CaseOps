# Nightly Setup

Nightly automation is optional and not part of the current NAS pilot default.

Before enabling scheduled runs, confirm:

- Salesforce tokens auto-refresh reliably.
- Claude Code auth is valid.
- `/api/settings/status` is healthy.
- No user-reviewed Jira posting is expected.
- The pipeline can run unattended without Production writes.

## Recommended Pilot Approach

For the pilot, schedule only Jira sync/triage or preflight checks. Full issue processing should remain operator-triggered until the pipeline has enough run history.

Example NAS health check:

```bash
curl -fsS http://127.0.0.1:5350/api/status
```

Example local sync:

```bash
python jira_sync.py --env-file .env --incremental
```

## Do Not Schedule

Do not schedule automatic Production promotion. CaseOps does not deploy to Production.

Do not schedule automatic Jira posting unless the user explicitly approves that workflow.
