<!--
Engineering handoff format. Output should start at "Problem".
Follow Markdown formatting rules in ../references/markdown-output-rules.md.
Keep this concise and Jira-ready. Do not include internal pipeline sections,
metadata dumps, confidence scoring, long investigation narrative, tokens,
private URLs, or internal filesystem paths.
-->

Problem

- [Specific Salesforce component and location, such as Flow, Apex class, validation rule, field, permission set, integration, or process.]
- [Exact failure point or broken behavior.]
- [Why this creates user/customer/business impact.]


Reproduce

1. [Log in as the affected user type or role.]
2. [Navigate to the exact Salesforce record, screen, process, button, automation path, or API action.]
3. [Perform the action that triggers the issue.]
4. [Observe the actual broken behavior.]


Expected behavior

- [State what should happen instead.]
- [Include required output, field value, validation message, notification, record update, integration payload, or report behavior.]


Affected record IDs

- [Specific record IDs, report/list-view references, user IDs, account/order/opportunity/case examples, or "None confirmed".]


Proposed Solution

- [Specific implementation change Engineering should make.]
  - [Component/element to update.]
  - [Condition/filter/query/field/payload/rule to change.]
  - [Expected resulting behavior.]
- [Production deploy requirement, such as "Production deploy required after Engineering review" or "No metadata deploy required".]
