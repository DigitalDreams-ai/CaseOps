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

For **Claude Code** in this repo, a thin entrypoint mirrors the skill name under `.claude/skills/jira-salesforce-fix-pipeline/SKILL.md`; it points at the canonical `skills/.../SKILL.md` — edit workflow and prompts under `skills/.../references/` (see `workflow.md`, `sub-agent-prompts.md`).

Do not add a required custom registry or runner unless the user explicitly asks for local helper tooling.

## Implementation Priorities

Build `skills/jira-salesforce-fix-pipeline/` first.

Expected initial files:

```text
skills/jira-salesforce-fix-pipeline/
  SKILL.md
  references/
    workflow.md
    sub-agent-prompts.md
    quality-checklist.md
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
- Append-only pipeline stream history under `outputs/pipeline-logs/` (JSONL per run key; gitignored).
- Do not store credentials or sensitive production data in this repo.
- Keep Salesforce integrations read-only until the user explicitly approves write/deploy behavior.
- **Never modify Profile permissions** (Salesforce Profile metadata or profile-level FLS / app visibility / tab settings). Prefer permission-set changes; if the issue requires profile edits, escalate to Engineering or an admin.
- In investigations, notes, Jira drafts, and rollups: **always** separate **Sandbox-validated** work from **Production**—state whether **Gearset (or deploy) to Production** is required vs **metadata already in Production** vs **N/A**. Do not imply Production was updated unless the operator explicitly deployed.
- Escalate to Engineering instead of implementing when the solution requires changing Apex/code, flows, approval processes, validation rules, or other business-critical automation.
- For Engineering escalations, produce a simple handoff: issue summary, root cause, affected metadata, proposed fix, validation evidence, and any records needed to reproduce.

## CaseOps GUI + LLM (API vs Claude Code / Chrome Dev / Salesforce magic link)

A committed template **[`.env.jira.example`](.env.jira.example)** lists **`CASEOPS_LLM_AUTH`** and other common keys—copy it to **`.env.jira`** and edit (your real `.env.jira` is gitignored).

When the Flask app runs an LLM step (**Run Pipeline For This Issue** after `run_pipeline.py`, or **Send to Claude**), **`CASEOPS_LLM_AUTH`** selects the **backend**:

- **`api_key` (default):** CaseOps calls the **Anthropic Messages API** with **`ANTHROPIC_API_KEY`** (install **`pip install anthropic`**). This is **text-only**: no filesystem, shell, browser, or Claude Code skills. The prompt explains limits; use this to avoid **Claude Code subscription / CLI** limits when a single-turn answer is enough.
- **`claude_code`:** CaseOps spawns the **`claude`** CLI with **`ANTHROPIC_API_KEY` omitted** so **Claude Code** uses **subscription / `claude login`**, including **tools** and full playbook execution in the repo.

Environment variables can steer **Claude Code** browser automation toward **Chrome Dev** and **Salesforce magic links** (those apply to **`claude_code`** runs, not to API-only turns):

Add to **`.env.jira`** (gitignored; never commit):

| Variable | Purpose |
| -------- | ------- |
| `CASEOPS_LLM_AUTH` | **`api_key`**: Anthropic **Messages API** + `ANTHROPIC_API_KEY` (see `requirements.txt`). **`claude_code`**: **`claude`** subprocess with API key **omitted** (subscription / login). Aliases for `claude_code`: `claude`, `subscription`, `max`. |
| `CASEOPS_ANTHROPIC_MODEL` | Optional. Model id for **API** mode (default `claude-sonnet-4-20250514`). |
| `CASEOPS_ANTHROPIC_MAX_TOKENS` | Optional. Max output tokens for **API** mode (default `16384`, capped). |
| `CASEOPS_CLAUDE_BROWSER` | Full path to **Chrome Dev** `chrome.exe` (Windows), or the `Google Chrome Dev` binary on macOS/Linux. Passed to the **`claude` subprocess** as `BROWSER` and `CLAUDE_CODE_CHROME_PATH` ( **`claude_code`** mode only). |
| `CASEOPS_SALESFORCE_MAGIC_LINK` | Optional single frontdoor URL when you do not split prod vs sandbox — clarify org and permission limits in chat if you use this. |
| `CASEOPS_PRODUCTION_MAGIC_LINK` | Production **frontdoor / session** URL. Use **only for read-only** access in Production: investigation, viewing, querying. **No** create/update/delete or deploy to Production. Prompt label uses `CASEOPS_PRODUCTION_READ_ORG`. |
| `CASEOPS_SANDBOX_MAGIC_LINK` | Sandbox **frontdoor / session** URL. **Full CRUD** is expected in Sandbox: deploy metadata, test, create/edit/delete records as the playbook requires. Prompt label uses `CASEOPS_SANDBOX_TARGET_ORG`. |
| `CASEOPS_SANDBOX_TARGET_ORG` | **Allowlisted writable org** for the **`salesforce-sandbox-deploy-test`** skill: the only Salesforce username/alias where deploys and mutating ops are permitted on the Support-resolvable path. Must match your CLI target. See **`skills/jira-salesforce-fix-pipeline/references/safety-policy.md`**. |

**Playbook:** On Support-resolvable fixes, **`jira-salesforce-fix-pipeline`** **always** reaches deploy+test via **`salesforce-sandbox-deploy-test`**; that skill may write **only** to **`CASEOPS_SANDBOX_TARGET_ORG`**.

Use a **separate** Salesforce user or permission set for Production session if needed so the Production link truly reflects **read-only** (e.g. View Setup, Read on objects only). Sandbox session should use a user with normal dev/test permissions.

Injected into the **CaseOps LLM user prompt** for **`claude_code`** runs they configure the CLI; in **`api_key`** mode the same text is included but **no browser tool** runs—treat links as reference only. **These URLs are as sensitive as passwords** while valid—never commit, ticket, or screenshot them.

Example (Windows paths vary; prefer splitting prod vs sandbox):

```env
CASEOPS_LLM_AUTH=api_key
CASEOPS_CLAUDE_BROWSER=C:\Program Files\Google\Chrome Dev\Application\chrome.exe
CASEOPS_PRODUCTION_MAGIC_LINK=https://...
CASEOPS_SANDBOX_MAGIC_LINK=https://...
```

Use **`GET /api/status`**: `caseops_llm_auth` is `api_key` or `claude_code`; `caseops_llm_backend` is `anthropic_messages_api` or `claude_code_cli`.

**Note:** **Full Triage** / **Full Run** only run `run_pipeline.py` (no LLM). Configure `.env.jira` for Claude Code **interactively** in a terminal as needed; for IDE-only runs, set the equivalent in Claude Code `settings.json` → `env` if needed.

## Validation

When adding or changing a skill:

- Confirm `SKILL.md` frontmatter is valid.
- Confirm the frontmatter `name` matches the folder name.
- Confirm referenced scripts, references, and assets exist.
- Add or update tests for deterministic scripts.

Use `skills-ref validate ./skills/<skill-name>` if the tool is available, but do not require it for basic work.


<claude-mem-context>
# Memory Context

# [CaseOps] recent context, 2026-05-15 4:52pm MST

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (21,542t read) | 453,353t work | 95% savings

### May 8, 2026
669 10:52a 🔵 Wide Repo Search Confirms Zero Local Metadata for Order Notes or Field History
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
1045 12:29p 🔵 Salesforce Sharing Rule for Round Robin Assignment Object
### May 15, 2026
1810 4:06p 🔵 HEAL-33647: Shopify→Salesforce Address Mismatch Root Cause Traced to External Connector Layer
1812 " ✅ HEAL-33647: Customer-Facing Jira Reply and Engineering Handoff Artifacts Prepared
1813 4:07p 🔵 HEAL-33647: Patient_Patient Apex Action Cleared; Root Cause Narrowed to External TenX API Write-Back Path
1814 4:09p ✅ HEAL-33647: Internal Notes Updated With Confirmed Evidence Block and Revised Deployment Guidance
1818 " ✅ HEAL-33647: Jira Message Draft Updated to Reflect Patient_Patient Clearance and Revised Engineering Steps
1836 4:30p 🔵 HEAL-33647 Investigation: Salesforce Account Address and Shopify ID Context

Access 453k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
