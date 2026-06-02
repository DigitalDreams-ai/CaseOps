# CaseOps Documentation

All general CaseOps documentation lives in this directory. Skill instructions stay under `skills/` because Claude Code loads them from those paths at runtime.

## Start Here

- [Project Overview](PROJECT_OVERVIEW.md) - what CaseOps is and how it is used.
- [User Guide](USER_GUIDE.md) - dashboard usage, Settings, tokens, pipeline actions.
- [Docker Setup](DOCKER_SETUP.md) - current NAS deployment and update rules.
- [Architecture](ARCHITECTURE.md) - runtime model, pipeline, storage, org knowledge.
- [Technical Overview](TECHNICAL_OVERVIEW.md) - deeper implementation notes.

## Reference

- [API](API.md) - Flask routes and endpoint behavior.
- [Agents](AGENTS.md) - Claude Code skills and sub-agent model.
- [Pipeline Architecture](PIPELINE_ARCHITECTURE.md) - pipeline-specific orchestration notes.
- [Instance Routing](INSTANCE_ROUTING.md) - workspace and path isolation.
- [Workspaces](WORKSPACES.md) - local multi-workspace usage.
- [Claude Launcher Guide](CLAUDE_LAUNCHER_GUIDE.md) - Claude Code authentication notes.
- [Nightly Setup](NIGHTLY_SETUP.md) - scheduled operation notes.
- [Enhancement Plan](CASEOPS_ENHANCEMENT_PLAN.md) - current backlog and pilot hardening items.
- [Deprecated Components](DEPRECATED.md) - archived legacy agents retained outside the active pipeline.

## Current Non-Negotiables

- Production Salesforce is read-only.
- The only writable Salesforce org is `CASEOPS_SANDBOX_TARGET_ORG`.
- Salesforce retrieve/deploy uses modern `sf` CLI only.
- Do not use legacy `sfdx force:*`, `package.xml`, or `--manifest` for routine CaseOps retrieve/deploy.
- Frontdoor and magic links are only for visual UI inspection, not API/SOQL/retrieve/deploy.
- Runtime appdata is under the active instance outputs tree, including `instance1/outputs/metadata-cache/` and `instance1/outputs/metadata-workspaces/`.
- Org knowledge lives in `outputs/org-knowledge/` and is selected progressively by topic.
