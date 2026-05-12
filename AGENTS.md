# AGENTS.md

## Project Purpose

This repo is for building a CaseOps Agent Skills pack, not a custom agent framework.

The source of truth is [AGENT_SKILLS_BUILD_SPEC.md](AGENT_SKILLS_BUILD_SPEC.md). Follow that spec when adding folders, scripts, references, assets, or tests.

## Agent Skills Standard

Skills must follow the Agent Skills format:

- Each skill is a folder under `skills/`.
- Each skill folder must contain `SKILL.md`.
- `SKILL.md` must start with YAML frontmatter.
- Frontmatter must include `name` and `description`.
- `name` must be lowercase kebab-case and match the parent folder name.
- Prefer the standard folders `scripts/`, `references/`, and `assets/`.

Do not add a required custom registry or runner unless the user explicitly asks for local helper tooling.

## Implementation Priorities

Build `skills/jira-salesforce-fix-pipeline/` first.

Expected initial files:

```text
skills/jira-salesforce-fix-pipeline/
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

## Coding Rules

- Keep scripts deterministic and non-interactive.
- Scripts must support `--help`.
- Scripts should accept explicit input and output paths.
- Do not write generated artifacts inside `skills/`.
- Put retrieved Jira raw data and summaries under `outputs/jira/`.
- Put investigation records under `outputs/investigations/`.
- Put Engineering escalation handoffs under `outputs/engineering-escalations/`.
- Put dated issue rollups under `outputs/issue-summary-YYYY-MM-DD.md`.
- Put Sandbox test reports under `outputs/test-reports/`.
- Put internal notes under `outputs/internal-notes/`.
- Put Jira message drafts under `outputs/jira-messages/`.
- Do not store credentials or sensitive production data in this repo.
- Keep Salesforce integrations read-only until the user explicitly approves write/deploy behavior.
- Escalate to Engineering instead of implementing when the solution requires changing Apex/code, flows, approval processes, validation rules, or other business-critical automation.
- For Engineering escalations, produce a simple handoff: issue summary, root cause, affected metadata, proposed fix, validation evidence, and any records needed to reproduce.

## Validation

When adding or changing a skill:

- Confirm `SKILL.md` frontmatter is valid.
- Confirm the frontmatter `name` matches the folder name.
- Confirm referenced scripts, references, and assets exist.
- Add or update tests for deterministic scripts.

Use `skills-ref validate ./skills/<skill-name>` if the tool is available, but do not require it for basic work.


<claude-mem-context>
# Memory Context

# [CaseOps] recent context, 2026-05-12 12:29pm MST

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (20,695t read) | 463,214t work | 96% savings

### May 8, 2026
662 10:51a 🔵 HEAL-33505 Human Ask Packet: Waiting for Sandbox Record Link or Production Confirmation
663 " 🔵 HEAL-33505 Active Blockers: Cross-Org Record Mismatch
664 " 🔵 HEAL-33505 Fix Proposal Blocked: Two Gates Failed Out of 12
665 10:52a 🔵 HEAL-33505 MCP Request Contract: Local Metadata Search Returned No Matches
666 " 🔵 HEAL-33505 Agent Discovery Draft File Absent from Output Directory
667 " 🔵 Opportunity Describe Against Sandbox Org: No "Order Notes" Field or trackHistory Entries Found
668 " 🔵 Agent Reasoning Draft Schema: Required Fields and Blocker Contract
669 " 🔵 Wide Repo Search Confirms Zero Local Metadata for Order Notes or Field History
670 " 🔵 HEAL-33505 Issue Brief: Salesforce Investigation Failed, Org Mismatch Confirmed
671 " 🔵 Opportunity Describe: Zero Fields Match Order, Note, History, or Hist in Sandbox Org
672 " 🔵 HEAL-33505 Salesforce Investigation: Exact Query Failure — Production Record Queried Against Sandbox
673 " 🔵 Opportunity Describe JSON Has Non-Standard Structure: fields Array is Empty at Root Level
674 " 🔵 Opportunity Describe stdout Field is Not JSON — Contains PowerShell Object (@) Serialization
675 " 🔵 HEAL-33505 Read Recovery Plan: Org Host Mismatch Confirmed, Fallback Searches Not Run
676 10:53a 🔵 Opportunity Describe stdout is Pre-Parsed PSCustomObject; Field List Truncated at Depth 3
677 " 🔴 HEAL-33505 Agent Reasoning Draft Written — precise_blocker Decision
678 " 🔵 Definitive Confirmation: No Order Notes or History Fields in Sandbox Opportunity Object
679 " 🔴 HEAL-33505 Repair Attempt 1 Passed Validation — "valid compact draft JSON"
680 " 🔵 Opportunity Describe Contains Only 10 Fields — This is a Record Query Result, Not a Full sobject Describe
681 " 🟣 HEAL-33505 Agent Reasoning Draft Written: precise_blocker, High Confidence
682 10:54a 🟣 HEAL-33505 Reasoning Draft Validated: Schema Compliant, Compact JSON, All Required Keys Present
714 11:03a 🔵 Agent Discovery Draft Reasoning Task for MOCK-PUBLIC-GROUP
712 " 🔵 Agent Discovery Task: HEAL-32413 Reasoning Draft Generation
715 " 🔵 HEAL-32413 Task Artifact: Four Active Blockers on SF Privilege Change Issue
716 " 🔵 MOCK-PUBLIC-GROUP Agent Task Artifact: Full Evidence Manifest and Output Contract
718 " 🔵 MOCK-PUBLIC-GROUP MCP Request: Matched Metadata File and Approved Write Scope
720 " 🔵 HEAL-32413 MCP Request: Adapter Config, Tool Safety Policy, and Metadata Search Hints
722 11:04a 🔵 Agent Reasoning Draft Schema: Field Types, Enums, and Blocker Structure
723 " 🔵 Agent Reasoning Draft Schema: Structure and Validation Rules
724 " 🔵 MOCK-PUBLIC-GROUP Issue Packet: Request Scope Confirmed as Metadata-Only Public Group Creation
725 " 🔵 HEAL-32413 Root Cause Confirmed: Salesforce Approval Process Lock on Labs Opportunities
726 " 🔵 MOCK-PUBLIC-GROUP Issue Brief: Fix Target Explicitly Named in relevantFacts
727 " 🔵 MOCK-PUBLIC-GROUP Salesforce Investigation Result: Single-File Fix Confirmed, No Errors
728 " 🔵 Salesforce Investigation Failed: Opportunity 006Ql00000ZGu8XIAT Not Found in 10xhealth-sean Org
729 11:05a 🔵 MOCK-PUBLIC-GROUP Fix Proposal: All 12 Gates Passed, Candidate File Confirmed
730 " 🔵 Read Recovery Plan: Org Config Anomaly — isSandbox=false Despite Sandbox URL
731 " 🔵 Production Read Access: Salesforce Context Is Production-Only, Gate 5 Blocked
732 " 🔵 MOCK-PUBLIC-GROUP Sandbox Work Order: 9/9 Gates Passed, Pending Human Approval in Dry-Run Mode
733 " 🔵 MOCK-PUBLIC-GROUP Issue State: ready_for_gearset_packet with Sandbox Proof Artifacts Present
734 " 🔵 Issue Brief: Proposed Approval Process Change Deployment Status Unknown
756 8:57p 🟣 HEAL-33439 Agent Reasoning Draft Created and Validated
### May 12, 2026
1036 11:40a ✅ .gitignore Reorganized and Deduplicated for CaseOps Project
1037 11:41a 🔵 .gitignore File Contains Near-Complete Duplicate Block
1038 11:48a 🔄 CaseOps .gitignore reorganized with deduplication and expanded coverage
1039 12:10p ✅ .gitignore Reorganized and Deduplicated for CaseOps
1040 12:11p ✅ CaseOps Repository Fully Staged and Committed in 4 Atomic Commits
1041 " ✅ .gitignore Significantly Expanded Beyond Deduplication
1042 " ✅ sfdx-project.json Updated: Name Added, API Version Bumped to 66.0
1043 " 🔵 CaseOps Project Structure: Flask GUI + Jira Sync + Agent Skills + Salesforce SFDX
1044 " 🟣 5-Skill CaseOps Agent Skills Pack Committed to Repository

Access 463k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
