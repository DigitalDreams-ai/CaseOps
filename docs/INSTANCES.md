# CaseOps Instances

CaseOps supports multiple instances by running the same codebase with different outputs and env files.

The active pilot uses a single NAS instance:

```text
instance1/
  outputs/
    metadata-cache/
    metadata-workspaces/
```

## Local Multi-Instance Pattern

Example:

```powershell
python app.py --workspace instance1 --outputs-dir instance1/outputs --env-file instance1/.env.jira --port 5000
python app.py --workspace instance2 --outputs-dir instance2/outputs --env-file instance2/.env.jira --port 5351
```

Each process has separate:

- output files
- Jira manifest
- Salesforce tokens
- metadata workspace
- pipeline logs

## NAS Pilot

The NAS deployment currently runs one container:

```text
caseops -> instance1
```

Add more containers only after deciding how to isolate ports, env files, outputs, and Sandbox allowlists.

## Reset One Instance

Stop the instance first, then archive or remove its state:

```bash
tar czf caseops-instance1-backup.tgz instance1/outputs
```

Do not delete state while a pipeline is active.
