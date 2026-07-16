FROM node:22-slim

WORKDIR /app
ENV CASEOPS_VERSION=0.1.61

# Install system deps + Python runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    unzip \
    jq \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/local/bin/python && \
    ln -sf /usr/bin/pip3 /usr/local/bin/pip

# Install Claude Code CLI and Salesforce CLI (pinned for reproducible builds).
RUN npm install -g @anthropic-ai/claude-code@2.1.210 @salesforce/cli@2.143.6

# Install Python deps (pinned for reproducible builds)
RUN python3 -m pip install --no-cache-dir --break-system-packages flask==3.1.3 markdown==3.10.2 anthropic==0.116.0

# Create non-root user for Claude Code CLI (explicit 1027:100 to match Synology mounts).
RUN set -eux; \
    if ! getent group 100 >/dev/null 2>&1; then \
      groupadd -g 100 -o -r caseops-group; \
    fi; \
    if getent passwd caseops >/dev/null 2>&1; then \
      usermod -u 1027 -g 100 -d /home/caseops caseops || true; \
    else \
      useradd -m -s /bin/bash -u 1027 -g 100 -d /home/caseops caseops; \
    fi && \
    mkdir -p /home/caseops && \
    chown -R 1027:100 /home/caseops

# Copy only product files. Runtime data, credentials, local Salesforce metadata,
# Jira outputs, screenshots, and issue logs must stay in bind-mounted appdata.
COPY --chown=1027:100 app.py knowledge_service.py issue_clusters.py jira_sync.py skill_registry.py caseops_paths.py model_config.py message_rules.py pipeline_gates.py pipeline_fsm.py output_evals.py canned-messages.json docker-entrypoint.sh /app/
COPY --chown=1027:100 docker/sfdx-project.json /app/sfdx-project.json
COPY --chown=1027:100 templates/ /app/templates/
COPY --chown=1027:100 static/ /app/static/
COPY --chown=1027:100 skills/ /app/skills/
COPY --chown=1027:100 scripts/ /app/scripts/

# Create output/cache mount points with proper permissions.
RUN mkdir -p /app/outputs /app/.temp /app/force-app/main/default && \
    chown -R 1027:100 /app/outputs /app/.temp /app/force-app /app/sfdx-project.json

# Expose Flask port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${CASEOPS_PORT:-8080}/health || exit 1

# Create Claude Code settings directory before switching to caseops user.
RUN mkdir -p /home/caseops/.claude && \
    chmod 700 /home/caseops/.claude && \
    chown 1027:100 /home/caseops/.claude

# Claude Code auth is provided at runtime with CLAUDE_CODE_OAUTH_TOKEN.

RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# Run as non-root user
USER caseops

# CaseOps runs on port 8080 in the container (host maps 5350 -> 8080);
# Claude Code CLI will be invoked as subprocess
# The writable env file is mounted at runtime (see docker-compose.example.yml).
# Entrypoint initializes Claude Code sandbox settings before starting Flask
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--port", "8080"]
