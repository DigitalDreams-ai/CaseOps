#!/bin/bash
set -e

# Load specific environment variables from .env.jira (some values have spaces, so can't use 'source')
if [ -f /app/.env.jira ]; then
  # Extract and EXPORT variables individually so they persist to subprocess
  export CASEOPS_LLM_AUTH=$(grep "^CASEOPS_LLM_AUTH=" /app/.env.jira | sed 's/^CASEOPS_LLM_AUTH=//' | tr -d ' ')
  export ANTHROPIC_API_KEY=$(grep "^ANTHROPIC_API_KEY=" /app/.env.jira | sed 's/^ANTHROPIC_API_KEY=//')
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
echo "  ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:0:10}***"

# Run Flask app with arguments
exec python app.py "$@"
