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

# Install Salesforce CLI (sf)
RUN npm install -g @salesforce/cli @salesforce/cli-plugins-analytics

# Copy project
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir flask markdown anthropic

# Create outputs volume mount point
RUN mkdir -p /app/outputs

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# CaseOps runs on port 5000; Claude Code CLI will be invoked as subprocess
# .env.jira is mounted at runtime (see docker-compose.yml)
CMD ["python", "app.py", "--port", "5000"]
