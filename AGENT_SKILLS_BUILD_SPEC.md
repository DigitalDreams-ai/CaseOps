# CaseOps Jira To Salesforce Fix Pipeline

## What This Is

This project should build a CaseOps Agent Skills pack for taking Jira issues through a controlled Salesforce investigation, implementation, sandbox deployment, test loop, and response-drafting process.

References:

- Anthropic skills repository: <https://github.com/anthropics/skills>
- Agent Skills specification: <https://agentskills.io/specification>
- Script guidance: <https://agentskills.io/skill-creation/using-scripts>
- Best practices: <https://agentskills.io/skill-creation/best-practices>

The important correction: do not start by building a custom agent framework, registry, or orchestration layer. The standard unit is a skill folder. A compatible agent discovers the skill by reading `SKILL.md` frontmatter, then loads the full instructions and referenced files only when the task calls for that skill.

## Core Pattern

An Agent Skill is a folder.

Minimum structure:

```text
skill-name/
  SKILL.md
```

Common expanded structure:

```text
skill-name/
  SKILL.md
  scripts/
  references/
  assets/
```

The skill gives an agent specialized workflow context without creating a new agent for every workflow.

Progressive disclosure:

1. Discovery: the agent sees only `name` and `description` from `SKILL.md`.
2. Activation: if the task matches, the agent reads the full `SKILL.md`.
3. Execution: the agent follows the instructions and loads referenced scripts, references, or assets only when needed.

## Product Goal

Build a reusable CaseOps skills pack that supports this pipeline:

1. Retrieve Jira issues.
2. Process and understand Jira issues.
3. Determine the Salesforce problem.
4. Determine the solution.
5. Investigate and retrieve relevant metadata from Production.
6. If the solution requires code, approval process, validation rule, or flow changes, stop and prepare an Engineering escalation handoff.
7. For non-escalation fixes only, implement the solution.
8. Deploy non-escalation fixes to Sandbox.
9. Test to determine whether the problem is fixed.
10. If the problem is not fixed, repeat steps 3-9.
11. When the solution is confirmed or escalated, draft internal notes and a Jira message.
12. Create or update the dated issue summary.
13. Inform the user with the details.

## Non-Goals

Do not build these first:

- A custom agent.
- A multi-agent orchestration system.
- A required `skill-registry.json`.
- A local runner as the main product.
- A web UI.
- Production Salesforce writes or deployments.
- Direct implementation of fixes that require Engineering ownership, including Apex/code, flows, approval processes, validation rules, or other business-critical automation.

A local validation helper can be added later, but the first deliverable should be standards-compatible skill folders.

## Required Skill Format

Each skill directory must contain `SKILL.md`.

`SKILL.md` must start with YAML frontmatter:

```markdown
---
name: jira-salesforce-fix-pipeline
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, diagnose the Salesforce problem, investigate Production metadata, implement a fix, deploy to Sandbox, test the fix, iterate if needed, and draft internal notes plus a Jira response.
---

# Jira Salesforce Fix Pipeline

Instructions go here.
```

Required frontmatter:

- `name`: lowercase letters, numbers, and hyphens only.
- `description`: describes what the skill does and when to use it.

Important rules:

- `name` must match the parent folder name.
- `description` should include trigger language users are likely to say.
- The body should contain only instructions the agent needs after activation.
- Move detailed references into `references/`.
- Move reusable templates, schemas, examples, and static files into `assets/`.
- Move executable repeatable logic into `scripts/`.

Optional frontmatter:

- `license`
- `compatibility`
- `metadata`
- `allowed-tools`

Treat `allowed-tools` as client-dependent. It can document intent, but the local workflow should not rely on every agent enforcing it the same way.

## Recommended Repository Layout

```text
CaseOps/
  AGENTS.md
  AGENT_SKILLS_BUILD_SPEC.md

  skills/
    jira-salesforce-fix-pipeline/
      SKILL.md
      references/
        workflow.md
        safety-policy.md
      assets/
        investigation-record-template.md
        engineering-handoff-template.md
        internal-notes-template.md
        jira-message-template.md
        issue-summary-template.md
        test-report-template.md

    jira-issue-analysis/
      SKILL.md
      references/
        issue-analysis-guide.md
      assets/
        issue-analysis-template.md

    salesforce-production-metadata-investigation/
      SKILL.md
      references/
        metadata-investigation-guide.md
      assets/
        metadata-inventory-template.md

    salesforce-sandbox-deploy-test/
      SKILL.md
      references/
        deploy-test-guide.md
      assets/
        test-report-template.md

    jira-response-drafting/
      SKILL.md
      assets/
        engineering-handoff-template.md
        internal-notes-template.md
        jira-message-template.md

  outputs/
    jira/
    investigations/
    engineering-escalations/
    test-reports/
    internal-notes/
    jira-messages/
    issue-summary-YYYY-MM-DD.md

  logs/
    skill-runs/
```

Notes:

- `skills/` contains standards-compatible skills.
- `outputs/` is local generated output, not part of the Agent Skills standard.
- `logs/` is local audit output, not part of the Agent Skills standard.
- Do not require `skill-registry.json` unless a future tool needs it.

## Skill Authoring Rules

Each `SKILL.md` should include:

- A short purpose statement.
- Clear use cases.
- Clear non-use cases.
- Required inputs.
- Workflow steps.
- Available scripts.
- Referenced files.
- Output expectations.
- Quality checks.

Recommended body:

```markdown
# Skill Name

## Use This Skill When

- ...

## Do Not Use This Skill When

- ...

## Inputs

- ...

## Workflow

1. ...
2. ...
3. ...

## Available Scripts

- `scripts/example.py`: What it does and when to run it.

## References

- `references/example.md`: When to read it.

## Assets

- `assets/template.md`: When to use it.

## Quality Checks

- ...
```

Keep `SKILL.md` focused. The agent loads the whole file after activation, so large details should move into `references/`.

## Script Rules

Scripts are for deterministic work. They should make repeatable operations stable instead of asking the model to recreate them every time.

Good script use cases:

- Retrieve Jira issues into local raw JSON and markdown summaries.
- Normalize JSON or CSV.
- Validate required fields.
- Render markdown from a template.
- Generate DOCX after the markdown flow is stable.
- Summarize Salesforce metadata diffs into structured JSON.

Avoid scripts for:

- Open-ended judgment.
- Unclear business rules.
- Tasks requiring user approval.
- Production Salesforce changes.

Script requirements:

- Accept all inputs through flags, environment variables, or stdin.
- Do not prompt interactively.
- Provide useful `--help`.
- Print errors that say what failed and how to fix it.
- Prefer structured output for machine-readable data.
- Send diagnostics to stderr and data to stdout or an output file.
- Support `--dry-run` for destructive or stateful operations.
- Use explicit output paths.
- Do not write outside approved output directories by default.

Suggested transform script interface:

```text
python jira_sync.py --issue ISSUE-123 --no-attachments --no-forms
```

Exit codes:

- `0`: success.
- `1`: invalid arguments or validation failure.
- `2`: missing file or unsafe path.
- `3`: unexpected runtime error.

## Primary Skill: `jira-salesforce-fix-pipeline`

Build this first. It is the orchestration skill that tells the agent how to move one or more Jira issues through the full Salesforce fix lifecycle.

Structure:

```text
skills/
  jira-salesforce-fix-pipeline/
    SKILL.md
    references/
      workflow.md
      safety-policy.md
    assets/
      investigation-record-template.md
      engineering-handoff-template.md
      internal-notes-template.md
      jira-message-template.md
      issue-summary-template.md
      test-report-template.md
```

Purpose:

- Retrieve and understand Jira issues.
- Determine the Salesforce problem and solution.
- Retrieve only relevant Production metadata for investigation.
- Classify the fix as Support-resolvable or Engineering escalation.
- For Engineering-owned fixes, prepare a simple handoff instead of implementing.
- Implement Support-owned fixes locally.
- Deploy Support-owned fixes to Sandbox.
- Test and iterate until the issue is fixed, escalated, or blocked.
- Draft internal notes and a Jira response.
- Create or update the dated issue summary.
- Inform the user with concise implementation details.

`SKILL.md` description should be specific:

```yaml
description: Runs the CaseOps Jira-to-Salesforce fix pipeline. Use when the user asks to retrieve Jira issues, diagnose the Salesforce problem, investigate Production metadata, implement a fix, deploy to Sandbox, test the fix, iterate if needed, and draft internal notes plus a Jira response.
```

Workflow:

1. Retrieve the Jira issue or issue list using available Jira tools, exported files, or user-provided issue content.
2. Process each issue into a structured problem statement, acceptance criteria, affected users, observed behavior, expected behavior, and reproduction notes.
3. Determine the likely Salesforce problem.
4. Determine a solution plan and validation strategy.
5. Retrieve relevant Production metadata read-only. Do not modify Production.
6. Classify the solution as Support-resolvable or Engineering escalation.
7. Escalate to Engineering when the solution requires changing Apex/code, flows, approval processes, validation rules, or other business-critical automation. Do not implement those changes locally unless the user explicitly overrides this rule.
8. For escalations, draft a simple handoff under `outputs/engineering-escalations/<KEY>.md` that includes the issue, root cause, affected metadata, potential fix, validation evidence, and reproduction records.
9. For Support-resolvable fixes only, implement the solution locally.
10. Deploy Support-resolvable fixes to Sandbox only after the implementation is ready and the target sandbox is clear.
11. Test the Sandbox behavior against the Jira acceptance criteria and reproduction steps.
12. If the problem is not fixed, document the failed hypothesis and repeat diagnosis, metadata investigation, implementation, deploy, and test.
13. When fixed or escalated, draft internal notes and a Jira-ready message.
14. Create or update `outputs/issue-summary-YYYY-MM-DD.md`.
15. Inform the user with the issue summary, root cause, escalation/fix status, files changed if any, deployment target if any, tests run, result, notes, draft Jira message, and summary file path.

Quality checks:

- Production access is read-only.
- The Jira problem is restated before implementation.
- The solution plan identifies affected Salesforce metadata.
- The Engineering escalation gate is evaluated before implementation.
- Engineering handoffs are simple, concrete, and include a potential fix.
- Engineering handoffs are stored under `outputs/engineering-escalations/`.
- The Sandbox deployment target is explicit.
- Tests map back to the Jira acceptance criteria.
- Failed iterations are recorded instead of overwritten.
- The dated issue summary is created or updated.
- Draft Jira messaging is factual and does not overclaim.

## CaseOps Skills To Add Next

### `jira-issue-analysis`

Purpose:

- Retrieve, normalize, and understand Jira issues before Salesforce work starts.

Files:

```text
skills/jira-issue-analysis/
  SKILL.md
  references/
    issue-analysis-guide.md
  assets/
    issue-analysis-template.md
```

### `salesforce-production-metadata-investigation`

Purpose:

- Retrieve relevant Production metadata read-only and identify the implementation surface.

Files:

```text
skills/salesforce-production-metadata-investigation/
  SKILL.md
  references/
    metadata-investigation-guide.md
  assets/
    metadata-inventory-template.md
```

### `salesforce-sandbox-deploy-test`

Purpose:

- Deploy the local fix to Sandbox and test it against the Jira acceptance criteria.

Files:

```text
skills/salesforce-sandbox-deploy-test/
  SKILL.md
  references/
    deploy-test-guide.md
  assets/
    test-report-template.md
```

### `jira-response-drafting`

Purpose:

- Draft internal implementation notes and a Jira-ready response after the Sandbox fix is confirmed.

Files:

```text
skills/jira-response-drafting/
  SKILL.md
  assets/
    engineering-handoff-template.md
    internal-notes-template.md
    jira-message-template.md
```

## Validation

Validation should check standards compatibility first.

Minimum validation:

- Every skill folder has `SKILL.md`.
- Every `SKILL.md` has valid YAML frontmatter.
- Frontmatter includes `name` and `description`.
- `name` matches the folder name.
- File references in `SKILL.md` point to existing files.
- Scripts named in `SKILL.md` exist.
- Scripts have `--help`.

Use the upstream validator when available:

```text
skills-ref validate ./skills/jira-salesforce-fix-pipeline
```

Local validation can be added later for CaseOps-specific rules.

## Testing

Test scripts, not model behavior.

Initial tests:

- Skill frontmatter validates.
- Required references and assets exist.
- Pipeline templates contain required sections.
- Any future scripts fail clearly when required inputs are missing.

Recommended command:

```text
python -m pytest
```

If no test framework exists yet, start with Python `unittest`.

## Security And Data Rules

- Do not store credentials in skill folders.
- Do not store sensitive production data in `skills/`.
- Use sanitized examples in `assets/`.
- Require confirmation before any Salesforce write, deployment, or destructive action.
- Keep the first Salesforce integrations read-only.
- Prefer local files and metadata exports before connecting to live orgs.

## Acceptance Criteria

The first milestone is complete when:

- `skills/jira-salesforce-fix-pipeline/SKILL.md` exists.
- Its frontmatter has valid `name` and `description`.
- The folder name and frontmatter `name` match.
- `references/workflow.md` exists.
- `references/safety-policy.md` exists.
- Investigation, Engineering handoff, notes, Jira message, issue summary, and test report templates exist.
- Supporting skills exist for Jira analysis, Production metadata investigation, Sandbox deploy/test, and response drafting.
- The skills can be used by an agent without any custom registry.

## Later Optional Tooling

Only after the skills themselves work, consider local helper tooling:

- A validator that checks all skill folders.
- A script wrapper that logs script executions.
- A packaging script for sharing the skills pack.
- A compatibility check for Claude Code or other Agent Skills clients.

These tools should support the skills pack. They should not become the architecture.
