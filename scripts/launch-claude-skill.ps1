# CaseOps Claude Code Launcher
# Opens a new PowerShell terminal and launches Claude with a jira-salesforce-fix-pipeline prompt
#
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File launch-claude-skill.ps1 -IssueKey HEAL-12345
#
# Usage (from Flask/Python):
#   subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", "launch-claude-skill.ps1", "-IssueKey", "HEAL-12345"])

param(
    [Parameter(Mandatory=$true)]
    [string]$IssueKey
)

# Validate issue key format
if ($IssueKey -notmatch '^HEAL-\d+$') {
    Write-Host "ERROR: Invalid issue key format. Expected HEAL-XXXXX" -ForegroundColor Red
    exit 1
}

# Get repo root
$RepoRoot = Split-Path -Parent $PSCommandPath
if (-not (Test-Path "$RepoRoot\.env.jira")) {
    Write-Host "ERROR: .env.jira not found at $RepoRoot" -ForegroundColor Red
    exit 1
}

# Build the Claude prompt
$Prompt = @"
Process $IssueKey through the full jira-salesforce-fix-pipeline Skill.

Issue key: $IssueKey
Repo root: $RepoRoot
Environment: .env.jira configured with CASEOPS_LLM_AUTH=claude_code

Execute Steps 1-12:
1. Sync/triage from Jira
2. Route (closed/escalated/active)
3. Analyze issue
4. Hypothesis
5. Production metadata
6. Problem location
7. Escalation gate
8. Implement (if Support)
9. Deploy+test in Sandbox
10. Draft messages
11. Dated summary
12. Report

Use the jira-salesforce-fix-pipeline Skill.
"@

# Escape the prompt for PowerShell
$EscapedPrompt = $Prompt -replace '"', '\"'

# Open new PowerShell window and launch claude
try {
    $LaunchCommand = "cd '$RepoRoot'; `$prompt = @`"`n$EscapedPrompt`n`"@; claude -p `$prompt; pause"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $LaunchCommand -WindowStyle Normal
    Write-Host "Launched Claude Code CLI for $IssueKey in new window" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Could not launch Claude Code: $_" -ForegroundColor Red
    exit 1
}
