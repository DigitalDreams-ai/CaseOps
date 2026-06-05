# CaseOps Documentation

Start with the shareable docs below. They are written for a tester or friend who needs to install, configure, and use CaseOps without internal deployment details.

## Shareable Docs

- [CaseOps Quickstart](CASEOPS_QUICKSTART.md) - fastest path to run the Docker image.
- [Tester Guide](TESTER_GUIDE.md) - what to test, safety rules, and troubleshooting.
- [User Guide](USER_GUIDE.md) - dashboard, Settings, auth, pipeline actions, generated files.
- [Docker Setup](DOCKER_SETUP.md) - compose, env file, update, logs, and backups.
- [Project Overview](PROJECT_OVERVIEW.md) - what CaseOps is and how the pipeline works.

## Maintainer Reference

These docs are useful for development and architecture work, but they are not required for a tester:

- [Architecture](ARCHITECTURE.md)
- [Technical Overview](TECHNICAL_OVERVIEW.md)
- [API](API.md)
- [Agents](AGENTS.md)
- [Pipeline Architecture](PIPELINE_ARCHITECTURE.md)
- [Instance Routing](INSTANCE_ROUTING.md)
- [Workspaces](WORKSPACES.md)
- [Nightly Setup](NIGHTLY_SETUP.md)
- [Deprecated Components](DEPRECATED.md)

Planning prompts and implementation plans are maintainer-only. Do not include them in a shared tester package.

## Current Non-Negotiables

- Production Salesforce is read-only.
- The only writable Salesforce org is `CASEOPS_SANDBOX_TARGET_ORG`.
- Salesforce retrieve/deploy uses modern `sf` CLI commands.
- Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps retrieve/deploy.
- Frontdoor and magic links are for visual inspection only, not API/SOQL/retrieve/deploy auth.
- Runtime data belongs in persistent appdata mounted at `/data`.
- Do not share credentials, Jira issue keys, customer names, Salesforce record IDs, internal hostnames, or full logs in bug reports.
