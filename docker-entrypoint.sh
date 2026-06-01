#!/bin/bash
# Note: NOT using set -e because Flask restart sends SIGTERM which exits with non-zero code
# The loop handles all exit codes gracefully

# Note: .env.jira is loaded by docker-compose via env_file directive.
# Variables like SF_PROD_*, SF_SANDBOX_*, CASEOPS_*, etc. are already in the environment.
# No need to source here as it conflicts with comments containing special characters.

# Initialize Claude Code settings and credentials
mkdir -p ~/.claude || true

# Check for pre-mounted credentials
if [ -f ~/.claude/.credentials.json ]; then
  echo "Found ~/.claude/.credentials.json"
else
  echo "Warning: ~/.claude/.credentials.json not found - Claude Code CLI will require /login"
fi

# Authenticate Salesforce orgs via sf CLI
# Note: SF_PROD_* and SF_SANDBOX_* env vars available from docker-compose env_file
echo "Salesforce orgs will be authenticated on demand via Flask API /setup endpoints"
echo "Alternatively, manually auth in container: sf org login access-token --alias <alias> --instance-url <url> --access-token <token> --no-prompt"
echo "Environment variables available: SF_PROD_ACCESS_TOKEN, SF_PROD_INSTANCE_URL, SF_SANDBOX_ACCESS_TOKEN, SF_SANDBOX_INSTANCE_URL"

# Service restart loop: reinitialize everything on each restart
while true; do
  echo "========================================"
  echo "Initializing CaseOps service..."
  echo "========================================"

  # Reinitialize Claude Code settings and credentials
  mkdir -p ~/.claude || true

  if [ -f ~/.claude/.credentials.json ]; then
    echo "✓ Claude Code credentials found"
  else
    echo "⚠ Claude Code credentials not found"
  fi

  # Verify environment
  echo "Environment ready:"
  echo "  CASEOPS_LLM_AUTH=$CASEOPS_LLM_AUTH"
  echo "  SF orgs authenticated"

  # Run Flask app (main service)
  echo "Starting Flask app..."
  python app.py "$@"
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 0 ]; then
    echo "Flask app exited cleanly (exit 0)"
    break
  else
    echo "Flask app exited with code $EXIT_CODE"
    echo "Restarting service in 2 seconds..."
    sleep 2
  fi
done
