# Docker

Local lab environment for the Network Platform Engineering Platform. All services run as
Docker containers, most managed by Docker Compose directly, with the Nautobot stack also
using the `invoke` task runner.

**This file covers directory layout and the Nautobot stack in detail (the original,
Phase-1 content). For every other service (Vault, GitLab, GitLab Runner, OPA, MCP Server,
Prometheus, Grafana, Loki, MinIO, Traefik) — ports, credentials, startup/restart
procedures, and troubleshooting — see
[`Platform-Administration-Guide.md`](../Platform-Administration-Guide.md), the
authoritative operational reference for the whole lab. This file does not duplicate that
content.**

---

## Directory Structure

```
docker/
├── README.md
├── docker-compose.yml                # root entry point: shared project name + networks via `include:` -- see below
├── nautobot/                        # Nautobot stack (nested git repo, see below)
├── vault/                            # HashiCorp Vault -- secrets for Terraform/Ansible/pyATS/MCP Server
├── mcp-server/                       # MCP Server container
├── platform-api/                     # OPA only today -- the legacy platform-api app is archived, see below
└── other-containers/
    ├── gitlab/                       # GitLab CE -- the execution engine
    ├── gitlab-runner/                # GitLab Runner
    ├── prometheus/                   # Metrics
    ├── grafana/                      # Dashboards
    ├── loki/                         # Log aggregation
    ├── minio/                        # S3-compatible Knowledge Capture storage
    └── traefik/                      # Reverse proxy
```

## Starting the whole lab

From `docker/`, `docker compose up -d` (or `down`) at the root starts/stops every service
under one shared Compose project (`infra-automation-lab`) via `include:` — see the comment
block at the top of `docker/docker-compose.yml` for why the Nautobot stack is included by
reference rather than owned here, and the operational hazards in
[`Platform-Status-and-Pending-Items.md`](../knowledge/architecture/Platform-Status-and-Pending-Items.md)
§3 for why `docker compose down` should never be run scoped to a single service's own
subdirectory. Required environment variables and the full startup sequence are in
[`Platform-Administration-Guide.md`](../Platform-Administration-Guide.md) §1.8.

---

## Nautobot stack

The rest of this document covers the Nautobot stack specifically, since it's managed
differently from every other service (its own nested git repository, `invoke` task runner
instead of plain `docker compose`, and a custom-built image).

---

## Nautobot's Compose files

The Nautobot stack is composed of three merged Compose files. Together they define the
`infra-automation-lab` project:

| Compose file | Purpose |
|---|---|
| `docker-compose.postgres.yml` | Postgres service and persistent volume |
| `docker-compose.base.yml` | All other services + healthchecks + labels |
| `docker-compose.local.yml` | Local dev overrides: ports, bind mounts, healthcheck timing |

### Services

| Container | Image | Role | Port |
|---|---|---|---|
| `infra-automation-lab-nautobot-1` | `infra-automation-lab/nautobot:local` (custom built) | Nautobot web app | `8080` → `8080` |
| `infra-automation-lab-celery_worker-1` | `infra-automation-lab/nautobot:local` | Background task worker | — |
| `infra-automation-lab-celery_beat-1` | `infra-automation-lab/nautobot:local` | Periodic task scheduler | — |
| `infra-automation-lab-redis-1` | `redis:7-alpine` (Docker Hub) | Message broker / cache | — |
| `infra-automation-lab-db-1` | `postgres:14-alpine` (Docker Hub) | Relational database | — |

### Custom Image — `infra-automation-lab/nautobot:local`

Built from `environments/Dockerfile`. Base image: `ghcr.io/nautobot/nautobot-dev`.

The build installs all Python dependencies from `pyproject.toml` via Poetry, including:

- `nautobot-ssot[aci]` — ACI SSoT sync plugin
- `invoke`, `toml` — dev task runner dependencies

The image is built once with `invoke build` and reused by all three Nautobot containers
(`nautobot`, `celery_worker`, `celery_beat`).

### Volumes

| Volume | Type | Purpose |
|---|---|---|
| `environments_postgres_data` | External (pre-existing) | Persistent Postgres database data |

The volume is declared `external: true` — Docker Compose does not own it and will never
create or delete it. This prevents accidental data loss when running `docker compose down -v`.

### Environment Files

| File | Tracked | Contents |
|---|---|---|
| `local.env` | Yes | Non-secret settings (DB host, Redis host, log level, etc.) |
| `local.example.env` | Yes | Template for `local.env` |
| `creds.env` | **No** (gitignored) | Passwords, API tokens, ACI credentials |
| `creds.example.env` | Yes | Template for `creds.env` |

Copy and fill in before first run:

```bash
cp environments/creds.example.env environments/creds.env
# Edit creds.env with real values
```

### Bind Mounts (local dev)

Applied by `docker-compose.local.yml` to `nautobot` and `celery_worker`:

| Host path | Container path | Purpose |
|---|---|---|
| `../config/nautobot_config.py` | `/opt/nautobot/nautobot_config.py` | Live config edits without rebuild |
| `../jobs/` | `/opt/nautobot/jobs` | Live job edits without rebuild |

---

## Task Runner (`invoke`)

All common operations are wrapped in `tasks.py` and run with `invoke`:

```bash
# from docker/nautobot/
invoke build          # Build the custom Nautobot image
invoke start          # Start the full stack (detached)
invoke stop           # Stop all containers
invoke restart        # Stop then start
invoke destroy        # Remove containers and volumes (CAUTION: destroys data)
invoke ps             # Show status of all lab containers
invoke debug          # Start with console output (not detached)
invoke nbshell        # Open Nautobot Django shell
invoke cli            # Open a shell inside the nautobot container
invoke createsuperuser
invoke migrate
invoke post_upgrade
invoke db_export      # Export database to file
invoke db_import      # Import database from file
```

---

## Nautobot Access

| Item | Value |
|---|---|
| URL | http://localhost:8080 |
| Default credentials | Set in `creds.env` (`NAUTOBOT_SUPERUSER_*`) |

---

## ACI SSoT Integration

The `nautobot-ssot[aci]` plugin is installed and enabled via `nautobot_config.py`:

```python
PLUGINS_CONFIG["nautobot_ssot"]["enable_aci"] = True
```

ACI credentials are loaded from `creds.env`:

| Variable | Description |
|---|---|
| `ACI_USERNAME` | APIC username |
| `ACI_PASSWORD` | APIC password |

The APIC endpoint and other connection details are configured inside Nautobot itself
(External Integrations → Cisco ACI).

---

## Platform API (`docker/platform-api/`) — legacy app archived, OPA remains

The original Platform v1 Intent Lifecycle app that used to live here (`app/`, its own
`Dockerfile`, `docker-compose.yml` with a `platform-api` service) is **archived** at
[`archive/platform-v1/docker/platform-api/`](../archive/platform-v1/docker/platform-api/)
per [ADR-016](../knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md)'s
replacement (not migration) decision — its responsibilities moved to the MCP Server,
Nautobot, and GitLab. Do not follow old instructions referencing a `platform-api`
container or a `NAUTOBOT_TOKEN`-gated `docker compose up -d --build` here; that app is not
run today.

What's still live in `docker/platform-api/` today is only
[`policy/`](platform-api/policy/) (the OPA Rego policies the GitLab CI `policy_check` job
uses) and a `docker-compose.yml` containing just the `opa` service. See
[`Platform-Administration-Guide.md`](../Platform-Administration-Guide.md) for how OPA is
run and administered.

