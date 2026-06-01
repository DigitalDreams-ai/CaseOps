# Claude Code Manual Launch Guide

If the Flask GUI button fails to launch Claude Code CLI, use one of these methods:

## Method 1: PowerShell Script (Windows)

**Automatic window launch:**

```powershell
powershell -ExecutionPolicy Bypass -File launch-claude-skill.ps1 -IssueKey HEAL-33150
```

This opens a new PowerShell window and launches Claude with the pipeline prompt.

## Method 2: Direct Claude CLI Command

**In your terminal (macOS/Linux/Windows):**

```bash
cd CaseOps
claude -p "Process HEAL-33150 through the full jira-salesforce-fix-pipeline Skill."
```

Replace `HEAL-33150` with your issue key.

## Method 3: Claude Code IDE

1. Open Claude Code IDE
2. Open the repo: `CaseOps` folder
3. Type in the chat panel:

```
/jira-salesforce-fix-pipeline

Process HEAL-33150 through the full pipeline.
```

Or copy the long-form prompt for more control:

```
Process HEAL-33150 through the full jira-salesforce-fix-pipeline Skill.

Issue key: HEAL-33150
Repo root: CaseOps
Environment: .env.jira configured with CASEOPS_LLM_AUTH=claude_code

Execute Steps 1-12:
1. Sync/triage from Jira
2. Route (closed/escalated/active)
3. Analyze issue
4. Hypothesis
5. Production metadata
6. Problem location
7. Escalation gate
8. Implement proposed solution
9. Deploy+test in Sandbox
10. Draft messages
11. Dated summary
12. Report

Use the jira-salesforce-fix-pipeline Skill.
```

## Method 4: From Flask GUI (Manual Text Copy)

If the GUI button produces an error in the logs:

1. Find the error message in the right panel
2. Look for a prompt text
3. Copy the prompt
4. Paste it into Claude Code IDE chat or CLI:

```bash
claude -p "<paste-prompt-here>"
```

## Troubleshooting

### "claude: command not found"
- Install Claude Code: `npm install -g @anthropic-ai/claude-code`
- Run `claude --version` to verify it's installed
- Or use the Claude Code IDE directly (Method 3 above)

### PowerShell script fails with permission error
- Run: `powershell -ExecutionPolicy Bypass -File launch-claude-skill.ps1 -IssueKey HEAL-33150`
- Or change execution policy: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### "Claude Code subscription not active"
- Run `claude setup-token` and save the new token in CaseOps at `/setup/claude-login`
- Check your Claude Code subscription status
- If using API key mode (`CASEOPS_LLM_AUTH=api_key`), sub-agents won't work

## Why Manual Launch Might Be Needed

1. **Claude CLI not on PATH** — PowerShell script provides fallback
2. **IDE vs CLI difference** — Some environments prefer IDE execution
3. **Debug/inspect** — Manual launch shows full Claude reasoning in real-time
4. **Offline testing** — Test prompts without Flask overhead

## Expected Output (All Methods)

After launching, Claude should:
1. Load the CaseOps repo context
2. Read the issue from `outputs/jira/summary/HEAL-33150.md`
3. Spawn sub-agents for Steps 3, 5, 6, 9, 10
4. Write outputs to `outputs/investigations/`, `outputs/jira-messages/`, etc.
5. Report completion in chat or terminal

Total runtime: 3–8 minutes depending on issue size and Jira/Salesforce latency.

---

**For fast launches**, create an alias in your shell:

**Bash/Zsh:**
```bash
alias caseops-pipeline='cd ~/path/to/CaseOps && claude -p "Process HEAL-33150 through the full jira-salesforce-fix-pipeline Skill."'
```

**PowerShell:**
```powershell
function Invoke-CaseOpsPipeline {
  param([string]$IssueKey = "HEAL-33150")
  powershell -ExecutionPolicy Bypass -File launch-claude-skill.ps1 -IssueKey $IssueKey
}
```

Then use:
```bash
caseops-pipeline HEAL-12345
```
