# Metadata Investigation Guide

Investigate only metadata that could plausibly affect the Jira issue.

## Workspace rules

- Store Production retrievals under `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/`.
- Treat this directory as read-only evidence. Never edit retrieved Production files in place.
- Use focused retrieve commands with `--output-dir "${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>"`.
- Do not use root-level `temp*`, `retrieve*`, `deploy*`, or `metadata*` directories.
- If a later step needs to test a modified version, copy only the required files into that step's Sandbox attempt directory.

Common metadata targets:

- Objects and fields.
- Record types.
- Validation rules.
- Flows and process automation.
- Apex classes and triggers.
- Permission sets and profiles.
- Assignment rules.
- Queues.
- Page layouts and Lightning pages.
- Custom metadata and custom settings.

For each retrieved item, record:

- Metadata name.
- Why it was retrieved.
- Relevant behavior found.
- Whether it confirms or rejects a hypothesis.

Do not retrieve the entire Production org unless the user explicitly asks and the scope justifies it.
