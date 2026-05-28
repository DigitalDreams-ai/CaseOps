# CaseOps Instance 1 Launcher
# Port: 5000
# Isolated state: .sfdx/, .claude/, outputs/

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Instance = "instance1"
$Port = 5000

# Get absolute paths
$SfDataDir = Join-Path $ScriptDir ".sfdx"
$ClaudeCodeDir = Join-Path $ScriptDir ".claude"
$OutputsDir = Join-Path $ScriptDir "outputs"
$EnvFile = Join-Path $ScriptDir ".env.jira"

Write-Host "=== CaseOps Instance 1 ===" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot" -ForegroundColor Cyan
Write-Host "State dir: $ScriptDir" -ForegroundColor Cyan
Write-Host ""

# Set environment variables for isolated state
$env:SF_DATA_DIR = $SfDataDir
$env:CLAUDE_CODE_DIR = $ClaudeCodeDir
$env:CASEOPS_WORKSPACE = $Instance

Write-Host "Environment:" -ForegroundColor Green
Write-Host "  SF_DATA_DIR=$SfDataDir" -ForegroundColor Green
Write-Host "  CLAUDE_CODE_DIR=$ClaudeCodeDir" -ForegroundColor Green
Write-Host "  CASEOPS_WORKSPACE=$Instance" -ForegroundColor Green
Write-Host ""

# Launch Flask app from repo root
Push-Location $RepoRoot
Write-Host "Starting Flask app..." -ForegroundColor Yellow
python app.py `
  --workspace $Instance `
  --port $Port `
  --outputs-dir $OutputsDir `
  --env-file $EnvFile
Pop-Location
