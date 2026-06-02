# CaseOps Workspaces

Workspaces are local-development support for running more than one CaseOps process from the same repo.

For the NAS pilot, use the single configured `instance1` deployment unless a second container is explicitly planned.

## Launch Locally

```bash
python app.py --workspace job1 --outputs-dir instance1/outputs --env-file instance1/.env.jira --port 5000
python app.py --workspace job2 --outputs-dir instance2/outputs --env-file instance2/.env.jira --port 5351
```

## Isolation

Each workspace should have its own:

- env file
- outputs directory
- metadata workspace
- port
- Sandbox allowlist

## Metadata

When `--outputs-dir instance1/outputs` is used, metadata defaults beside it:

```text
instance1/.temp/metadata/
```

Do not share a metadata workspace between two active instances.

## Operational Guidance

- Keep one active pipeline per issue.
- Check `/api/status` before restarting or deleting state.
- Do not copy Salesforce auth caches between workspaces. Use env-token auth.
