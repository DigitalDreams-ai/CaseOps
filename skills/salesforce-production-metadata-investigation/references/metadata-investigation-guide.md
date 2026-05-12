# Metadata Investigation Guide

Investigate only metadata that could plausibly affect the Jira issue.

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
