FROM python:3.11-slim

WORKDIR /app

# Install system deps + Node.js (for sf CLI)
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    jq \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Salesforce CLI
RUN npm install -g @salesforce/cli

# Install CumulusCI (for CI/CD, scratch orgs, sandboxes)
RUN pip install --no-cache-dir cumulusci

# Copy project (includes .credentials.json for pre-authenticated Claude Code CLI)
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir flask markdown anthropic

# Create non-root user for Claude Code CLI (avoids root permission restrictions)
RUN useradd -m -s /bin/bash -d /home/caseops caseops && \
    chown -R caseops:caseops /app

# Create outputs volume mount point with proper permissions
RUN mkdir -p /app/outputs && chown caseops:caseops /app/outputs

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Create and set up Claude Code credentials before switching to caseops user
RUN mkdir -p /home/caseops/.claude && \
    chmod 700 /home/caseops/.claude && \
    chown caseops:caseops /home/caseops/.claude

# Credentials mounted at runtime via docker-compose volumes (not baked into image)

# Copy entrypoint script and make executable (before switching to caseops user)
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Run as non-root user
USER caseops

# CaseOps runs on port 5000; Claude Code CLI will be invoked as subprocess
# .env.jira is mounted at runtime (see docker-compose.yml)
# Entrypoint initializes Claude Code sandbox settings before starting Flask
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--port", "5000"]
