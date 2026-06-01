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
   - Volume: Add path `/app/instance1/outputs` → map to `/volume1/docker/stacks/caseops/instance1/outputs`
   - Volume: Add path `/app/instance1/.temp` → map to `/volume1/docker/stacks/caseops/instance1/.temp` if metadata workspace persistence/audit is required
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
CASEOPS_LLM_AUTH=claude_code
CLAUDE_CODE_OAUTH_TOKEN=...
CASEOPS_SANDBOX_TARGET_ORG=sandbox-alias
CASEOPS_PRODUCTION_READ_ORG=prod-alias
CASEOPS_SANDBOX_INSTANCE_URL=https://test.salesforce.com
CASEOPS_PRODUCTION_INSTANCE_URL=https://login.salesforce.com
CASEOPS_SANDBOX_MAGIC_LINK=https://...       # optional, visual UI checks only
CASEOPS_PRODUCTION_MAGIC_LINK=https://...    # optional, visual UI checks only
```

### .env.jira.nas (NAS/Linux — DO NOT COMMIT)
For NAS deployment, copy `.env.jira` → `.env.jira.nas` and remove Windows paths:
```env
# Same as .env.jira, EXCEPT:
# DELETE this line (Windows-specific path):
# CASEOPS_CLAUDE_BROWSER=C:\Program Files\Google\Chrome Dev\Application\chrome.exe

# Keep everything else (Jira, Salesforce, Claude token, etc.)
JIRA_BASE_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
...
```

**In docker-compose.yml:**
```yaml
volumes:
  - ./.env.jira.nas:/app/.env.jira
```

This keeps your Windows `.env.jira` pristine for local dev, while `.env.jira.nas` is for NAS deployment. The NAS env file must be writable because CaseOps refreshes Salesforce tokens and saves auth Settings there. Canned message customizations are saved under the mounted outputs tree at `outputs/settings/canned-messages.json`.

### Claude Code CLI inside container

`claude` CLI is pre-installed in Dockerfile.

### Auth approach: Save a Claude Code OAuth token

**On your local machine:**
```bash
npm install -g @anthropic-ai/claude-code
claude setup-token
```

Copy only the token printed by the command. In CaseOps, open `/setup/claude-login` and paste it. CaseOps saves it to the active env file as `CLAUDE_CODE_OAUTH_TOKEN`.

The container can then invoke `claude -p ...` non-interactively without mounting `~/.claude`.

**Alternative:** Use Anthropic API instead (CASEOPS_LLM_AUTH=api_key)

If you prefer direct API calls: set `CASEOPS_LLM_AUTH=api_key` in `.env.jira.nas` and provide `ANTHROPIC_API_KEY`. No Claude CLI auth needed.

---

## Salesforce CLI inside container

`sf` CLI is pre-installed in Dockerfile. 

### Auth approach: tokens in `.env.jira.nas` (recommended)

CaseOps does not mount host `~/.sf` or `~/.sfdx` into the container. The current NAS deployment authenticates `sf` inside the container from tokens stored in `.env.jira.nas`.

**On your authenticated local machine (one-time, then whenever access tokens expire):**
```bash
# Authenticate each org locally
sf org login web --alias 10xhealth
sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com

# Access tokens: copy result.accessToken
sf org auth show-access-token -o 10xhealth --json
sf org auth show-access-token -o 10xhealth-sean --json

# Optional auto-refresh: copy result.sfdxAuthUrl
sf org auth show-sfdx-auth-url -o 10xhealth --json
sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
```

Paste the access tokens and optional SFDX auth URLs at:

```text
http://localhost:5350/setup/refresh-salesforce-tokens
```

**In .env.jira (or .env.jira.nas for NAS):**
```env
CASEOPS_PRODUCTION_READ_ORG=10xhealth
CASEOPS_SANDBOX_TARGET_ORG=10xhealth-sean
CASEOPS_PRODUCTION_INSTANCE_URL=https://login.salesforce.com
CASEOPS_SANDBOX_INSTANCE_URL=https://test.salesforce.com
SF_PROD_ACCESS_TOKEN=<current prod access token>
SF_SANDBOX_ACCESS_TOKEN=<current sandbox access token>
SF_PROD_REFRESH_TOKEN=<optional prod refresh token extracted from sfdxAuthUrl>
SF_SANDBOX_REFRESH_TOKEN=<optional sandbox refresh token extracted from sfdxAuthUrl>
SF_TOKENS_REFRESHED_AT=<unix timestamp>
```

The Settings page's **Authenticate Salesforce Orgs** button calls `/api/setup/salesforce-auth`, which runs:

```bash
export SF_ACCESS_TOKEN=<token>
sf org login access-token --alias <CASEOPS_*_ORG> --instance-url <CASEOPS_*_INSTANCE_URL> --no-prompt
```

The `sf org login access-token` command reads the token from the `SF_ACCESS_TOKEN` environment variable; it does not have a `--access-token` flag.

### Alternative: Auth inside container (ephemeral, loses creds on container replacement)
```bash
docker exec -it caseops sf org login web --alias 10xhealth
docker exec -it caseops sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com
```

Creds are stored in the Salesforce CLI cache for the container user (current `sf` versions use `~/.sf`; older tooling may also use `~/.sfdx`). This is not recommended as the source of truth for the NAS deployment.

---

## Volume Mounts (Synology)

Synology Docker paths (by default):
- `/volume1/docker/stacks/caseops/instance1/outputs` ← CaseOps `outputs/` folder (persistent)
- `/volume1/docker/stacks/caseops/instance1/.temp` ← metadata workspace, if explicitly mounted for persistence/audit
- `.env.jira` ← bind mount your secrets file (writable; token refresh and Settings save here)
- `/volume1/docker/stacks/caseops/app.py` → `/app/app.py` (read-only source mount)
- `/volume1/docker/stacks/caseops/templates` → `/app/templates` (read-only source mount)
- `/volume1/docker/stacks/caseops/static` → `/app/static` (read-only source mount)
- `/volume1/docker/stacks/caseops/skills` → `/app/skills` (read-only source mount)

To verify:
```bash
docker exec caseops ls -la /app/instance1/outputs
docker exec caseops cat /app/.env.jira
```

---

## Persistent Data

- **outputs/** mounted from the host (survives container replacement)
- **.temp/metadata/** stores raw Production retrievals, Sandbox attempts, revert packages, and confirmed metadata packages
- **.env.jira** mounted at runtime (not in volume, safer for secrets)
- **Salesforce CLI auth** is recreated inside the container from tokens in `.env.jira`; host `~/.sf` and `~/.sfdx` are not mounted in the current NAS flow

---

## Deployment Rule

The NAS deployment intentionally bind-mounts source files and skills so pilot updates are predictable:

- Changes to `app.py`, `templates/`, `static/`, or `skills/`: sync the local repo to `/volume1/docker/stacks/caseops`, then restart `caseops`.
- Changes to `Dockerfile`, Python dependencies, npm/global CLI installs, or OS packages: sync, rebuild the image, then restart `caseops`.
- Changes to `.env.jira.nas`: save the env file, then restart `caseops` so startup auth is recreated from the new values.
- Always verify inside the running container after deployment, not just in the NAS stack folder.

Synology Docker binary:
```bash
/volume1/@appstore/ContainerManager/usr/bin/docker compose up -d --build caseops
/volume1/@appstore/ContainerManager/usr/bin/docker restart caseops
```

To back up outputs:
```bash
tar czf ~/backup/caseops-instance1-outputs.tar.gz -C /volume1/docker/stacks/caseops instance1/outputs
tar czf ~/backup/caseops-instance1-metadata.tar.gz -C /volume1/docker/stacks/caseops instance1/.temp/metadata
```

---

## Troubleshooting

### "claude: command not found"
- The Docker image installs Claude Code CLI with npm; rebuild the image if the binary is missing
- Or switch to `CASEOPS_LLM_AUTH=api_key` (Anthropic API mode)

### "sf: command not found"
- Image has `sf` pre-installed via npm; check:
  ```bash
  docker exec caseops which sf
  ```

### Intermittent `sf --version` timeout during pipeline preflight
- CaseOps disables Salesforce CLI telemetry, autoupdate, and progress output for pipeline subprocesses.
- `sf --version` is diagnostic only; pipeline gating is based on `sf org display` and SOQL access for the configured Production and Sandbox aliases.
- If org display or SOQL also time out, check NAS CPU/I/O load and restart the container after confirming `.env.jira.nas` has current Salesforce tokens.

### Container exits immediately
- Check logs:
  ```bash
  docker logs caseops
  ```
- Common: missing `.env.jira` file (Flask can't start)
- Common: `.env.jira.nas` is missing, not mounted to `/app/.env.jira`, or mounted read-only. Token refresh and Settings updates require this file to be writable.

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

1. On your authenticated local machine: authenticate Salesforce orgs and copy tokens into CaseOps
   ```bash
   sf org login web --alias 10xhealth
   sf org login web --alias 10xhealth-sean --instance-url https://test.salesforce.com
   sf org auth show-access-token -o 10xhealth --json
   sf org auth show-access-token -o 10xhealth-sean --json
   sf org auth show-sfdx-auth-url -o 10xhealth --json
   sf org auth show-sfdx-auth-url -o 10xhealth-sean --json
   ```

2. Generate and save Claude Code token:
   ```bash
   claude setup-token
   ```
   Paste the token at `/setup/claude-login`.

3. Build image: `docker build -t caseops:latest .`

4. Copy `.env.jira.nas` to NAS (with org aliases matching step 1)

5. In Synology Docker GUI:
   - Create container from `caseops:latest`
   - Port: 5000 (container) → 5350 (host)
   - Volumes: outputs, `.env.jira.nas` (writable bind)

6. Start container

7. Test: `http://localhost:5350` on NAS, then `https://caseops.yourdomain.com` via Cloudflare tunnel
