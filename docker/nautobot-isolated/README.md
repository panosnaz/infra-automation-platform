# Isolated laptop Nautobot

This is a second, independent Nautobot instance for the platform repository. It does not use the existing `C:\Claude Code\ACI-Nautobot\nautobot-docker` instance.

Isolation properties:

- Compose project: `infra-automation-nautobot-isolated`
- Web/API: `http://localhost:8081`
- Dedicated PostgreSQL, Redis, media, and static volumes
- Dedicated Docker network
- ACI SSoT plugin enabled
- One Celery worker and one Celery beat by default
- No GitLab, observability stack, or MCP container in this lightweight profile

## First start

From PowerShell:

```powershell
Set-Location C:\MCP\INFRA-AUTOMATION-PLATFORM\docker\nautobot-isolated
Copy-Item .env.example .env
notepad .env
# Replace all CHANGE-ME values, then:
docker compose up -d --build
```

Check startup:

```powershell
docker compose ps
docker compose logs -f isolated-nautobot
```

Open `http://localhost:8081`. The database and Redis volumes are named with the `isolated_` prefix and must not be shared with either existing project.

## Optional MCP server against this instance

The MCP Compose definition accepts an endpoint override. From the repository root:

```powershell
$env:NAUTOBOT_URL = "http://host.docker.internal:8081"
$env:NAUTOBOT_TOKEN = "<the API token from this instance>"
$env:MCP_GITLAB_TOKEN = "<read_api token, only needed for show_status>"
docker compose -f docker/mcp-server/docker-compose.yml up -d --build
```

This targets the isolated instance and does not contact the existing Nautobot on port 8080. The MCP server still requires a GitLab token for live pipeline status; without GitLab, object-writing tools can work but status is incomplete.

## Stop and remove

```powershell
# Stops containers; keeps isolated data volumes
docker compose down

# Deletes this instance's data too; use only when intentionally resetting it
docker compose down -v
```

## Optional GitLab

GitLab is intentionally not part of the default laptop profile. The full Platform v2 pipeline requires GitLab, but GitLab CE is memory-heavy and needs its own repository, runner, credentials, and additional services. Start it only after the isolated Nautobot is stable and only when Docker Desktop has sufficient memory:

```powershell
Set-Location C:\MCP\INFRA-AUTOMATION-PLATFORM\docker\nautobot-isolated
docker compose --profile gitlab up -d gitlab
```

The GitLab service is resource-capped at 2 CPUs and 2 GB memory. These are guardrails, not a guarantee that GitLab will be responsive on a 16 GB laptop.

## Optional GitLab Runner

The Runner is required for any CI/CD pipeline to actually execute — without it, jobs queue as `pending` forever. It starts alongside GitLab under the same `gitlab` profile:

```powershell
docker compose --profile gitlab up -d gitlab-runner
```

It is unregistered by default. Register it once GitLab itself is healthy:

```powershell
# In GitLab: Settings -> CI/CD -> Runners -> New instance runner -> copy the registration command's token
docker exec -it infra-automation-nautobot-isolated-gitlab-runner-1 gitlab-runner register `
  --url "http://host.docker.internal:8929" `
  --token "<paste the token>" `
  --executor "docker" `
  --docker-image "alpine:latest"
```

Verify registration:

```powershell
docker exec infra-automation-nautobot-isolated-gitlab-runner-1 gitlab-runner verify
```

