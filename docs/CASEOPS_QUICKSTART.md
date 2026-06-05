# CaseOps Quickstart

Use this when setting up CaseOps from the published Docker image.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose.
- A Jira account with API token access.
- Salesforce CLI authenticated to:
  - one Production org for read-only investigation,
  - one Sandbox org for deploy and test.
- Claude Code installed locally so you can run `claude setup-token`.

## Start CaseOps

Create a folder for the deployment and add:

- `docker-compose.yml`
- `.env.example`

Copy the env template:

```bash
cp .env.example .env
```

Edit `.env` with your Jira URL, Jira API credentials, Salesforce aliases, and Salesforce URLs.

Start the container:

```bash
docker compose pull
docker compose up -d
```

Open:

```text
http://localhost:5350
```

## Complete Settings

Open Settings in the app.

1. Confirm the CaseOps version is shown beside the Settings title.
2. In Jira, verify the Jira URL, email, and token.
3. In Salesforce, paste Production and Sandbox access tokens.
4. Paste SFDX auth URLs if you want CaseOps to refresh Salesforce access tokens.
5. In Claude, run:

```bash
claude setup-token
```

Paste the printed token into the Claude section.

## First Test

1. Click `Sync This Issue` for one approved issue, or run a limited Jira sync.
2. Open the issue.
3. Confirm the Jira Summary tab shows current status and comments.
4. Run the pipeline only after Settings shows Jira, Salesforce, and Claude are ready.
5. Review generated artifacts before sending any Jira message.

## Safety

- Production Salesforce is read-only.
- The Sandbox target is the only writable org.
- CaseOps does not deploy to Production.
- Do not use frontdoor links as API credentials.
- Keep credentials out of screenshots, bug reports, and logs.
