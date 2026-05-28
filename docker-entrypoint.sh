#!/bin/bash
set -e

# Load specific environment variables from .env.jira (some values have spaces, so can't use 'source')
if [ -f /app/.env.jira ]; then
  # Extract only clean variable lines (key=value with no spaces in key)
  export CASEOPS_LLM_AUTH=$(grep "^CASEOPS_LLM_AUTH=" /app/.env.jira | sed 's/^CASEOPS_LLM_AUTH=//' | tr -d ' ')
  export ANTHROPIC_API_KEY=$(grep "^ANTHROPIC_API_KEY=" /app/.env.jira | sed 's/^ANTHROPIC_API_KEY=//')
  if [ -n "$CASEOPS_LLM_AUTH" ]; then
    echo "Loaded .env.jira: CASEOPS_LLM_AUTH=$CASEOPS_LLM_AUTH"
  fi
fi

# Initialize Claude Code settings and credentials
# ~/.claude is mounted from host via docker-compose.yml
mkdir -p ~/.claude 2>/dev/null || true

# settings.json: configure sandbox permissions for /app/outputs
# (ignore permission errors if directory is mounted read-only or with wrong ownership)
if [ ! -f ~/.claude/settings.json ] || ! grep -q "autoApprove" ~/.claude/settings.json 2>/dev/null; then
  cat > ~/.claude/settings.json <<'EOF' 2>/dev/null || true
{
  "sandbox": {
    "approvedDirectories": ["/app/outputs"],
    "trustedPaths": ["/app/outputs/**"]
  },
  "permissions": {
    "autoApprove": ["/app/outputs"]
  }
}
EOF
  [ -f ~/.claude/settings.json ] && echo "Created/updated ~/.claude/settings.json with /app/outputs approval"
fi

# .credentials.json should be pre-mounted from host via docker-compose.yml
if [ -f ~/.claude/.credentials.json ]; then
  echo "Found ~/.claude/.credentials.json (mounted from host)"
else
  echo "Warning: ~/.claude/.credentials.json not found - Claude Code CLI will require /login"
fi

# Run Flask app with arguments
exec python app.py "$@"
