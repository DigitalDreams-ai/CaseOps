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

## Internal Notes And Engineering Handoffs

- Tables are acceptable for compact evidence, rollups, or test matrices.
- Keep operational details outside tables when they require commands, logs, or multi-step explanation.
- Engineering handoffs should stay concise and Jira-ready: Problem, Reproduce, Expected behavior, Affected record IDs, Proposed Solution.

## Commands And Code

- Use inline backticks for short commands, file names, field names, API names, and identifiers.
- Use fenced code blocks for multi-line commands, logs, JSON, SOQL, Apex, XML, or diffs.
- Do not place fenced code blocks inside table cells.
