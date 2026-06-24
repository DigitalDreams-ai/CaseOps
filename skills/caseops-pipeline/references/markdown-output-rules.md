# Markdown Output Rules

Use these rules for every CaseOps-generated Markdown artifact.

## General

- Keep Markdown simple and GitHub-compatible.
- Use normal headings, paragraphs, bullets, numbered lists, fenced code blocks, and valid tables.
- Do not use decorative Unicode separators or complex HTML unless the template explicitly requires it.
- Leave a blank line before and after headings, lists, tables, and fenced code blocks.
- Keep customer-facing files free of internal paths, NAS paths, local repo paths, tokens, private URLs, and implementation notes.

## Tables

- Use tables only for compact, scan-friendly comparisons or rollups.
- Keep each table row on its own line.
- Always include a header row and separator row.
- Keep every row at the same column count as the header.
- Escape literal pipe characters inside cells as `\|`.
- Use `<br>` for intentional line breaks inside a cell.
- Keep cells short.
- Do not put bullets, numbered lists, fenced code blocks, or long paragraphs inside table cells.
- If details need bullets, code, logs, commands, or long text, put a short summary in the table and place the details below it.
- Use `N/A`, `Unknown`, or `None confirmed` for empty values instead of leaving cells blank when possible.

## Customer-Facing Jira Messages

- Do not use tables unless the reporter explicitly needs a comparison.
- Prefer short paragraphs and simple bullets.
- Explain the problem and next step in human, non-technical language.
- Do not include internal diagnosis, metadata dumps, file paths, NAS paths, local repo paths, tokens, private URLs, or operator-only notes.

## Internal Notes, Issue Briefs, And Engineering Handoffs

- Tables are acceptable for compact evidence, rollups, or test matrices.
- Keep operational details outside tables when they require commands, logs, or multi-step explanation.
- Issue briefs should stay concise and Jira-ready for every processed issue: Problem, Reproduce, Expected behavior, Affected record IDs, Proposed Solution.
- Engineering handoffs should stay concise and Jira-ready: Problem, Reproduce, Expected behavior, Affected record IDs, Proposed Solution.

## Issue Brief And Engineering Handoff Template Formatting

These rules apply only to files generated from:

- `assets/issue-brief-template.md`
- `assets/engineering-handoff-template.md`

That means only:

- `outputs/issue-briefs/<KEY>.md`
- `outputs/engineering-escalations/<KEY>.md`

Do not apply these stricter formatting rules to Jira messages, internal notes, investigation records, test reports, dated summaries, Jira summaries, or generated supporting documents.

- Start the file at `Problem`. Do not add a title, issue key, author initials, date, label, or preamble.
- Use plain section labels without Markdown heading markers: `Problem`, `Reproduce`, `Expected behavior`, `Affected record IDs`, `Proposed Solution`.
- Put one blank line after each section label and leave clear whitespace between sections.
- Keep the brief focused on what another person needs to understand and act on. Do not replay the investigation.
- Use natural language. Avoid LLM phrases such as "business impact", "confirmed package", "regression passed", "metadata verify passed", and "sandbox-validated" unless that exact phrase is needed for the action.
- Do not use em dashes. Do not use hyphens as clause punctuation.
- Do not include Markdown links, Salesforce `sf://` links, Jira links, report links, or clickable record links. Use plain text names and IDs only.
- Do not use inline code backticks or fenced code blocks in these two outputs. Record IDs, API names, endpoint paths, field names, class names, flow names, object names, commands, and payload fragments must be plain text.
- Do not include Sandbox suffixes or personal markers such as `SB`, operator initials, deploy IDs, confirmed package paths, local paths, NAS paths, or metadata workspace paths.
- Prefer names people recognize over API names. Use API names only when the exact implementation target requires them.
- Group related details under a main bullet with sub-bullets instead of long link-heavy sentences.
- Do not repeat the same fact in multiple sections. If it is already clear in `Problem`, do not restate it in `Proposed Solution`.
- Keep `Problem` to the minimum set of facts: what component/process is involved, where it fails, and what the visible impact is.
- Keep `Reproduce` runnable but short. Do not include implementation analysis in reproduce steps.
- In `Affected record IDs`, use examples with sub-bullets when there are related source and child records.
- In `Proposed Solution`, state the specific change to make. Do not include test status, deploy IDs, package paths, or unrelated cleanup notes.

## Commands And Code

- Use inline backticks for short commands, file names, field names, API names, and identifiers.
- Use fenced code blocks for multi-line commands, logs, JSON, SOQL, Apex, XML, or diffs.
- Do not place fenced code blocks inside table cells.
- Exception: do not use inline backticks or fenced code blocks in issue briefs or engineering handoffs. Those two outputs are copied into Jira and must remain plain text.
