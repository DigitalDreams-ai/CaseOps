#!/bin/bash
set -e

# Initialize Claude Code settings to pre-approve /app/outputs writes
mkdir -p ~/.claude

if [ ! -f ~/.claude/settings.json ]; then
  cat > ~/.claude/settings.json <<'EOF'
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
  echo "Created ~/.claude/settings.json with /app/outputs approval"
fi

# Run Flask app with arguments
exec python app.py "$@"
