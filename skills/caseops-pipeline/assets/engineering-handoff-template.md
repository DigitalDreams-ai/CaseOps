<!--
Engineering handoff format. Output should start at "Problem".
Follow Markdown formatting rules in ../references/markdown-output-rules.md.
Keep this concise and Jira-ready. 
Do not include internal pipeline sections,
metadata dumps, confidence scoring, long investigation narrative, tokens,
private URLs, or internal filesystem paths.
Use plain text only.
Do not wrap anything in backticks.
Do not use fenced code blocks.
Record IDs, API names, endpoint paths, field names, class names, flow names,
object names, commands, and payload fragments must be plain text.
Do not include Markdown links, sf:// links, 
deploy IDs, package paths, metadata workspace paths, or operator initials.
Remove ALL 'SB' suffixes.
Group exact details under short parent bullets with sub-bullets.
-->

Problem

- [Salesforce component and location, such as Flow, Apex class, validation rule, field, permission set, integration, or process.]
  - [Exact target name in plain text, if needed.]
  - [Second related target name in plain text, if needed.]
- [Where the failure happens and what visible behavior it creates.]
- [User/customer impact, stated once and without repeating details from the first bullet.]



Reproduce

1. [Log in as the affected user type or role.]
2. [Navigate to the record, screen, process, button, automation path, or API action.]
3. [Perform the smallest action that triggers the issue.]
4. [See the actual broken behavior.]



Expected behavior

- [State what should happen instead.]
- [Include required output, field value, validation message, notification, record update, integration payload, or report behavior.]



Affected record IDs

- [Example 1 source record in plain text.]
  - [Related affected record ID or IDs in plain text.]
- [Example 2 source record in plain text, or "None confirmed".]
  - [Related affected record ID or IDs in plain text.]



Proposed Solution

- [Specific implementation change Engineering should make.]
  - [Component or element to update.]
  - [Condition, filter, query, field, payload, or rule to change.]
  - [Expected resulting behavior.]
