#!/bin/bash
set -e

# Load LLM auth mode from .env.jira (Claude Code CLI mode only, no API keys)
if [ -f /app/.env.jira ]; then
  export CASEOPS_LLM_AUTH=$(grep "^CASEOPS_LLM_AUTH=" /app/.env.jira | sed 's/^CASEOPS_LLM_AUTH=//' | tr -d ' ')
  if [ -n "$CASEOPS_LLM_AUTH" ]; then
    echo "Loaded .env.jira: CASEOPS_LLM_AUTH=$CASEOPS_LLM_AUTH"
  fi
fi

# Initialize Claude Code settings and credentials
# ~/.claude is mounted from host via docker-compose.yml; don't try to modify it
mkdir -p ~/.claude 2>/dev/null || true

# Check for pre-mounted credentials
if [ -f ~/.claude/.credentials.json ]; then
  echo "Found ~/.claude/.credentials.json (mounted from host)"
else
  echo "Warning: ~/.claude/.credentials.json not found - Claude Code CLI will require /login"
fi

# Verify environment is set before running Flask
echo "Final env check:"
echo "  CASEOPS_LLM_AUTH=$CASEOPS_LLM_AUTH"
echo "  Claude Code CLI will use ~/.claude/.credentials.json (mounted from host)"

# Run Flask app with arguments
exec python app.py "$@"
