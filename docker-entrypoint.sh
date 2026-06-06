#!/bin/bash
# Note: NOT using set -e because Flask restart sends SIGTERM which exits with non-zero code
# The loop handles all exit codes gracefully

# Note: .env is loaded by docker-compose via env_file directive.
# Variables like SF_PROD_*, SF_SANDBOX_*, CASEOPS_*, etc. are already in the environment.
# No need to source here as it conflicts with comments containing special characters.

env_file_path="${CASEOPS_ENV_FILE:-${CASEOPS_JIRA_ENV_FILE:-/app/.env}}"

load_env_value_if_unset() {
  key="$1"
  current_value="$(eval "printf '%s' \"\${$key:-}\"")"
  if [ -n "$current_value" ] || [ ! -f "$env_file_path" ]; then
    return
  fi
  file_value="$(grep -m1 "^${key}=" "$env_file_path" | cut -d= -f2- | tr -d '\r')"
  if [ -n "$file_value" ]; then
    export "$key=$file_value"
  fi
}

# Load selected runtime secrets from the mounted env file. Do not source the
# entire file; values such as Windows paths and comments can break shell parsing.
load_env_value_if_unset "CLAUDE_CODE_OAUTH_TOKEN"
load_env_value_if_unset "CASEOPS_LLM_AUTH"

# Initialize Claude Code settings directory.
# Use a guaranteed writable home for Claude metadata and avoid relying on inherited
# HOME values from the host/legacy shells when running as a numeric user.
caseops_home="${HOME:-/home/caseops}"
if [ -z "$caseops_home" ] || [ "$caseops_home" = "/" ] || [ "$caseops_home" = "//" ]; then
  caseops_home="/home/caseops"
fi
case "$caseops_home" in
  C:Users*) caseops_home="/home/caseops" ;;
esac
export HOME="$caseops_home"
mkdir -p "$HOME/.claude" || true

# Check for preferred non-interactive OAuth token.
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "Found CLAUDE_CODE_OAUTH_TOKEN for Claude Code CLI"
else
  echo "Warning: CLAUDE_CODE_OAUTH_TOKEN not configured - use /setup/claude-login"
fi

# Authenticate Salesforce orgs via sf CLI
# Note: SF_PROD_* and SF_SANDBOX_* env vars available from docker-compose env_file
echo "Salesforce orgs will be authenticated on demand via Flask API /setup endpoints"
echo "Alternatively, manually auth in container: export SF_ACCESS_TOKEN=<token>; sf org login access-token --alias <alias> --instance-url <url> --no-prompt"
echo "Environment variables available: SF_PROD_ACCESS_TOKEN, SF_SANDBOX_ACCESS_TOKEN, CASEOPS_PRODUCTION_INSTANCE_URL, CASEOPS_SANDBOX_INSTANCE_URL"

# Service restart loop: reinitialize everything on each restart
while true; do
  echo "========================================"
  echo "Initializing CaseOps service..."
  echo "========================================"

  # Re-load selected runtime secrets in case /app/.env changed before a restart.
  env_file_path="${CASEOPS_ENV_FILE:-${CASEOPS_JIRA_ENV_FILE:-/app/.env}}"
  load_env_value_if_unset "CLAUDE_CODE_OAUTH_TOKEN"
  load_env_value_if_unset "CASEOPS_LLM_AUTH"

  # Reinitialize Claude Code settings directory.
  if [ -z "$caseops_home" ] || [ "$caseops_home" = "/" ] || [ "$caseops_home" = "//" ]; then
    caseops_home="/home/caseops"
  fi
  case "$caseops_home" in
    C:Users*) caseops_home="/home/caseops" ;;
  esac
  export HOME="$caseops_home"
  mkdir -p "$HOME/.claude" || true

  if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    echo "Claude Code OAuth token configured"
  else
    echo "Claude Code OAuth token not configured"
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
