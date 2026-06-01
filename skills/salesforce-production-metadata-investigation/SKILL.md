---
name: salesforce-production-metadata-investigation
description: Investigates Salesforce Production metadata read-only to identify objects, fields, flows, validation rules, permission sets, Apex, layouts, assignment rules, or other metadata relevant to a Jira issue. Use before deciding whether to implement a Support-owned fix or escalate to Engineering.
---

# Salesforce Production Metadata Investigation

## Use This Skill When

- A Jira issue requires Salesforce diagnosis.
- The likely problem depends on existing Production metadata.
- The agent needs to retrieve relevant metadata before implementing a fix.
- The `jira-salesforce-fix-pipeline` delegates metadata investigation as Step 5.

## Do Not Use This Skill When

- The user asks to modify Production.
- The task is not Salesforce-related.

## Workflow

1. Start from the Jira issue analysis and problem hypothesis.
2. Identify the smallest relevant metadata set.
3. Retrieve metadata from Production read-only using `sf` CLI and `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/`, or inspect provided metadata exports.
4. Treat retrieved Production files as read-only evidence.
5. Record why each metadata item was retrieved.
6. Summarize findings and likely implementation surface.
7. Stop before making changes.

## References

- `references/metadata-investigation-guide.md`: Metadata retrieval and review checklist.

## Assets

- `assets/metadata-inventory-template.md`: Metadata findings template.

## Quality Checks

- Production access remains read-only.
- Retrieval is targeted to the issue.
- Raw metadata is stored under `${CASEOPS_METADATA_RAW_PROD_DIR}/<KEY>/`.
- Findings separate facts from hypotheses.
