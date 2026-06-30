# CaseOps Org Knowledge Run Rules

These rules are always safe to include in Salesforce pipeline runs.

- Read this file plus only the topic files selected by `index.json`; do not bulk-read the entire org-knowledge directory.
- Use org knowledge to avoid relearning Salesforce CLI behavior. Prefer the known pattern first, then investigate only if the known pattern fails.
- Use `sf` CLI and SOQL for Salesforce API work. Do not use frontdoor links, magic links, or browser session IDs for API, SOQL, retrieve, deploy, or tests.
- Never print, export, or embed raw Salesforce access tokens. Do not run `SF_TEMP_SHOW_SECRETS=true sf org display`. If a REST call is unavoidable, use an internal helper that does not log the token.
- Stay inside the current issue workspace. Do not inspect other issue metadata or output directories unless the operator explicitly asks for cross-issue comparison.
- Stop after two failed variants of the same query/deploy pattern. Replan using the selected org knowledge instead of trying many small variations.
- Before querying an unfamiliar, optional, or managed-package object, verify the object exists and is queryable. Prefer `verify-sobject`, `sobject-fields`, `verify-field`, or `verify-flow` over broad speculative SOQL.
- Prefer `--json` output and parse concise fields. Do not read full persisted deploy/retrieve logs unless the concise status is insufficient.
- When a run discovers a durable, verified, reusable fact, write a structured knowledge signal. Do not directly update active knowledge, and do not store secrets or customer-specific narrative.
- Retrieve/deploy through modern `sf` CLI commands only. Do not use legacy `sfdx force:*` commands. Do not use `package.xml` or `--manifest` unless the operator explicitly approves a metadata-type exception.
- For `sf project` retrieve/deploy commands, use an issue-scoped Salesforce DX workspace. The CaseOps `sf` guard can create a minimal issue-scoped workspace when a command is launched outside one, but helper-based retrieve/deploy remains the preferred path.
