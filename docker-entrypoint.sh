#!/bin/bash
set -e

# Load .env.jira config
if [ -f /app/.env.jira ]; then
  source /app/.env.jira
  echo "Loaded .env.jira"
fi

# Initialize Claude Code settings and credentials
mkdir -p ~/.claude 2>/dev/null || true

# Check for pre-mounted credentials
if [ -f ~/.claude/.credentials.json ]; then
  echo "Found ~/.claude/.credentials.json"
else
  echo "Warning: ~/.claude/.credentials.json not found - Claude Code CLI will require /login"
fi

# Authenticate Salesforce orgs via sf CLI
echo "Authenticating Salesforce orgs..."

# 10xhealth production
if [ -n "$SF_PROD_ACCESS_TOKEN" ] && [ -n "$SF_PROD_INSTANCE_URL" ]; then
  echo "Authenticating 10xhealth (production)..."
  sf org login access-token \
    --alias 10xhealth \
    --instance-url "$SF_PROD_INSTANCE_URL" \
    --access-token "$SF_PROD_ACCESS_TOKEN" \
    --no-prompt || echo "Warning: Failed to auth 10xhealth"
else
  echo "Skipping 10xhealth - missing SF_PROD_ACCESS_TOKEN or SF_PROD_INSTANCE_URL"
fi

# 10xhealth-sean sandbox
if [ -n "$SF_SANDBOX_ACCESS_TOKEN" ] && [ -n "$SF_SANDBOX_INSTANCE_URL" ]; then
  echo "Authenticating 10xhealth-sean (sandbox)..."
  sf org login access-token \
    --alias 10xhealth-sean \
    --instance-url "$SF_SANDBOX_INSTANCE_URL" \
    --access-token "$SF_SANDBOX_ACCESS_TOKEN" \
    --no-prompt || echo "Warning: Failed to auth 10xhealth-sean"
else
  echo "Skipping 10xhealth-sean - missing SF_SANDBOX_ACCESS_TOKEN or SF_SANDBOX_INSTANCE_URL"
fi

# Set default org
sf config set defaultusername=10xhealth --global 2>/dev/null || true

# Verify environment is set before running Flask
echo "Environment ready:"
echo "  CASEOPS_LLM_AUTH=$CASEOPS_LLM_AUTH"
echo "  SF orgs authenticated"

# Run Flask app with arguments
exec python app.py "$@"
