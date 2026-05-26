# CaseOps Docker + Cloudflare Tunnel Setup

## Quick Start

### 1. Build image
```powershell
docker build -t caseops:latest .
```

### 2. Run container (with Cloudflare tunnel)

#### Option A: Local dev (localhost:5350)
```powershell
docker-compose up -d
# Access at http://localhost:5350
```

#### Option B: Synology NAS via Docker GUI
1. Open Synology Docker app
2. Images → Upload → select Dockerfile (or build via CLI)
3. Containers → Create → choose `caseops:latest`
4. Set:
   - Container name: `caseops`
   - Memory limit: 2GB+ (Claude Code CLI is heavy)
   - Port settings: Container port 5000 → Local port 5350
   - Volume: Add path `/app/outputs` → map to `/volume1/docker/caseops/outputs`
   - Volume: Add path `/app/.env.jira` → bind mount your local `.env.jira`
5. Start container

---

## Cloudflare Tunnel (Remote Access)

### Install Cloudflared locally on Synology

SSH into Synology:
```bash
# Download cloudflared ARM64 (for Synology x86, use amd64)
wget https://github.com/cloudflare/cloudflared/releases/download/2025.1.0/cloudflared-linux-arm64
chmod +x cloudflared-linux-arm64
```

### Authenticate Cloudflared
```bash
./cloudflared-linux-arm64 tunnel login
# Opens browser → authorize with Cloudflare account → returns cert.pem
```

### Create tunnel config
Create `~/.cloudflared/config.yml`:
```yaml
tunnel: caseops
credentials-file: /root/.cloudflare/cert.pem

ingress:
  - hostname: caseops.yourdomain.com
    service: http://localhost:5350
  - service: http_status:404
```

**Replace `yourdomain.com` with your actual Cloudflare domain.**

### Start tunnel
```bash
./cloudflared-linux-arm64 tunnel run caseops
```

Or daemonize (systemd):
```bash
./cloudflared-linux-arm64 service install
systemctl start cloudflared
```

---

## Environment & Secrets

### Config Files

**Local Windows development:** `.env.jira`
**NAS/Linux deployment:** `.env.jira.nas` (copy of .env.jira, Windows paths removed)

### .env.jira (Windows — DO NOT COMMIT)
Create `.env.jira` in repo root:
```env
JIRA_BASE_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token
ANTHROPIC_API_KEY=sk-...
CASEOPS_LLM_AUTH=claude_code
CASEOPS_SANDBOX_TARGET_ORG=sandbox-alias
CASEOPS_PRODUCTION_READ_ORG=prod-alias
CASEOPS_SANDBOX_MAGIC_LINK=https://...
CASEOPS_PRODUCTION_MAGIC_LINK=https://...
```

### .env.jira.nas (NAS/Linux — DO NOT COMMIT)
For NAS deployment, copy `.env.jira` → `.env.jira.nas` and remove Windows paths:
```env
# Same as .env.jira, EXCEPT:
# DELETE this line (Windows-specific path):
# CASEOPS_CLAUDE_BROWSER=C:\Program Files\Google\Chrome Dev\Application\chrome.exe

# Keep everything else (Jira, Salesforce, Anthropic, etc.)
JIRA_BASE_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
...
```

**In docker-compose.yml:**
```yaml
volumes:
  - ./.env.jira.nas:/app/.env.jira:ro
```

This keeps your Windows `.env.jira` pristine for local dev, while `.env.jira.nas` is for NAS deployment.

### Claude Code CLI inside container

`claude` CLI is pre-installed in Dockerfile.

### Auth approach: Mount ~/.claude from NAS host (recommended)

**On NAS host (one-time):**
```bash
npm install -g @anthropic-ai/claude-code
claude login  # authenticate once
# Credentials stored in ~/.claude/
```

**In docker-compose.yml:**
```yaml
volumes:
  - ~/.claude:/root/.claude:ro  # Container reads pre-authenticated Claude session
```

Now container can invoke `claude` commands with host authentication.

**Alternative:** Use Anthropic API instead (CASEOPS_LLM_AUTH=api_key)

If you prefer direct API calls: set `CASEOPS_LLM_AUTH=api_key` in `.env.jira.nas` and provide `ANTHROPIC_API_KEY`. No Claude CLI auth needed.

---

## Salesforce CLI inside container

`sf` CLI is pre-installed in Dockerfile. 

### Auth approach: Mount ~/.sfdx from NAS host (recommended)

**On NAS host (one-time):**
```bash
# Authenticate each org
# Production (no --instance-url needed, uses default login.salesforce.com)
sf org login web --set-default --alias 10xhealth --instance-url https://10xhealth.my.salesforce.com

# Sandbox (MUST include --instance-url with sandbox-specific test URL)
sf org login web --set-default --alias 10xhealth-sean --instance-url https://10xhealth--sean.sandbox.my.salesforce.com

# Credentials stored in ~/.sfdx/
```

**In docker-compose.yml:**
```yaml
volumes:
  - ~/.sfdx:/root/.sfdx:ro  # Container reads pre-authenticated orgs
```

**In .env.jira (or .env.jira.nas for NAS):**
```env
CASEOPS_PRODUCTION_READ_ORG=10xhealth
CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean
```

Now app.py can call `sf data query --target-org 10xhealth` and it will use the authenticated session.

### Alternative: Auth inside container (ephemeral, loses creds on restart)
```bash
docker exec -it caseops sf org login web --set-default --alias prod
docker exec -it caseops sf org login web --set-default --alias sandbox
```

Creds are stored in container's `/root/.sfdx/` (ephemeral). Not recommended unless you volume-mount ~/.sfdx separately.

---

## Volume Mounts (Synology)

Synology Docker paths (by default):
- `/volume1/docker/caseops/outputs` ← CaseOps `outputs/` folder (persistent)
- `.env.jira` ← bind mount your secrets file (read-only)

To verify:
```bash
docker exec caseops ls -la /app/outputs
docker exec caseops cat /app/.env.jira
```

---

## Persistent Data

- **outputs/** stored in named volume `caseops-outputs` (survives container delete)
- **.env.jira** mounted at runtime (not in volume, safer for secrets)
- **Salesforce CLI auth** mounted from host `~/.sfdx` (read-only, pre-authenticated orgs)

To back up outputs:
```bash
docker run --rm -v caseops-outputs:/data -v ~/backup:/backup \
  alpine tar czf /backup/caseops-outputs.tar.gz /data
```

---

## Troubleshooting

### "claude: command not found"
- Ensure Claude Code CLI is installed globally on Synology host
- Or switch to `CASEOPS_LLM_AUTH=api_key` (Anthropic API mode)

### "sf: command not found"
- Image has `sf` pre-installed via npm; check:
  ```bash
  docker exec caseops which sf
  ```

### Container exits immediately
- Check logs:
  ```bash
  docker logs caseops
  ```
- Common: missing `.env.jira` file (Flask can't start)
- Common: `.sfdx` mount path doesn't exist on host; create it:
  ```bash
  mkdir -p ~/.sfdx
  ```

### "no such file or directory: ~/.sfdx"
- On NAS host, ensure `~/.sfdx` exists:
  ```bash
  mkdir -p ~/.sfdx
  sf org login web --set-default --alias prod
  # Now ~/.sfdx/orgs.json is populated
  ```
- Then restart container

### Port 5350 not responding
- Verify container is running:
  ```bash
  docker ps | grep caseops
  ```
- Check port mapping:
  ```bash
  docker port caseops
  # Should show: 5000/tcp -> 0.0.0.0:5350
  ```
- Verify Cloudflare tunnel points to `:5350`, not `:5000`

### Cloudflare tunnel not routing
- Verify tunnel credentials:
  ```bash
  cloudflared tunnel list
  cloudflared tunnel info caseops
  ```
- Check DNS: does `caseops.yourdomain.com` resolve?

---

## Performance Notes

- Flask dev server (not production): fine for single-user, small batches
- For production: consider Gunicorn + Nginx inside container
- Memory: Claude Code CLI + Anthropic SDK can use 500MB+; allocate 2GB+ in Synology
- Network: Cloudflare tunnel adds latency (~50ms); acceptable for UI

---

## Next Steps

1. On NAS host: authenticate Salesforce orgs
   ```bash
   # Production
   sf org login web --set-default --alias 10xhealth --instance-url https://10xhealth.my.salesforce.com
   
   # Sandbox (use your sandbox domain)
   sf org login web --set-default --alias 10xhealth-sean --instance-url https://10xhealth--sean.sandbox.my.salesforce.com
   ```

2. Authenticate Claude Code CLI on NAS host:
   ```bash
   claude login
   ```

3. Build image: `docker build -t caseops:latest .`

4. Copy `.env.jira.nas` to NAS (with org aliases matching step 1)

5. In Synology Docker GUI:
   - Create container from `caseops:latest`
   - Port: 5000 (container) → 5350 (host)
   - Volumes: outputs, .env.jira.nas (bind), ~/.sfdx (pre-authenticated)

6. Start container

7. Test: `http://localhost:5350` on NAS, then `https://caseops.yourdomain.com` via Cloudflare tunnel
