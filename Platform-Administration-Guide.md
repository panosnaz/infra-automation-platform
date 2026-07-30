---
title: "Platform Administration Guide"
description: "Operational handbook for administering the nautobot-infra-automation Docker-based lab: access, configuration, monitoring, and troubleshooting for every platform component."
---

# Platform Administration Guide

This is the operational handbook for the **Network Platform Engineering Platform** — a Docker Compose-based lab that automates Cisco ACI infrastructure through Nautobot, GitLab CI/CD, Terraform, Ansible, and an MCP Server that AI agents call directly. It assumes you have never seen this environment before.

For architectural background (why the platform is designed this way), see [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) and [`knowledge/architecture/Execution-Framework.md`](knowledge/architecture/Execution-Framework.md). This guide is about *operating* the platform, not its design rationale.

> **Lab environment notice:** every credential in this guide is a shared, non-production lab default (documented openly in this repo's own tracked config files). Do not reuse any of these values outside this lab.

---

## Table of Contents

1. [Platform-Wide Administration](#1-platform-wide-administration)
2. [Nautobot](#2-nautobot)
3. [PostgreSQL (Nautobot database)](#3-postgresql-nautobot-database)
4. [Redis (Nautobot)](#4-redis-nautobot)
5. [Celery Worker & Celery Beat](#5-celery-worker--celery-beat)
6. [HashiCorp Vault](#6-hashicorp-vault)
7. [GitLab CE](#7-gitlab-ce)
8. [GitLab Runner](#8-gitlab-runner)
9. [MCP Server](#9-mcp-server)
10. [Platform API (legacy) & OPA](#10-platform-api-legacy--opa)
11. [Prometheus](#11-prometheus)
12. [Grafana](#12-grafana)
13. [Loki](#13-loki)
14. [MinIO](#14-minio)
15. [Traefik](#15-traefik)
16. [Quick Reference Table](#16-quick-reference-table)

---

## 1. Platform-Wide Administration

### 1.1 Overall Architecture

```
User (natural language) → AI Agent (VS Code Copilot / Claude Desktop)
    → MCP Server → Nautobot (Source of Truth)
        → GitLab webhook → GitLab CI pipeline
            → generate (Nautobot → NetAsCode YAML)
            → validate → policy (OPA) → manual approval gate
            → terraform apply (Cisco ACI simulator)
            → ansible (Day-2 config)
            → pyATS (independent validation)
            → write_results (status → Nautobot) + knowledge_capture (→ MinIO)
```

Every arrow is a native capability of an existing tool (Nautobot's webhook, GitLab's pipeline engine) — the MCP Server never orchestrates the pipeline itself, it only writes to Nautobot and later reads status back. See [`knowledge/architecture/Platform-v2-Reference-Architecture.md`](knowledge/architecture/Platform-v2-Reference-Architecture.md) for the full rationale.

### 1.2 Docker Compose Overview

All services run under **one Docker Compose project name: `infra-automation-lab`**. The single entry point is [`docker/docker-compose.yml`](docker/docker-compose.yml), which uses Compose's `include:` directive to pull in every sub-stack's own compose file without moving any of them:

| Included file | Service(s) |
|---|---|
| `nautobot/environments/docker-compose.base.yml` | `nautobot`, `celery_worker`, `celery_beat`, `redis` |
| `nautobot/environments/docker-compose.postgres.yml` | `db` (Postgres) |
| `nautobot/environments/docker-compose.local.yml` | Local dev overrides (ports, bind mounts) for `nautobot`/`celery_worker` |
| `vault/docker-compose.yml` | `vault` |
| `platform-api/docker-compose.yml` | `platform-api` (legacy), `opa` |
| `mcp-server/docker-compose.yml` | `mcp-server` |
| `other-containers/gitlab/docker-compose.yml` | `gitlab` |
| `other-containers/gitlab-runner/docker-compose.yml` | `gitlab-runner` |
| `other-containers/prometheus/docker-compose.yml` | `prometheus` |
| `other-containers/grafana/docker-compose.yml` | `grafana` |
| `other-containers/loki/docker-compose.yml` | `loki` |
| `other-containers/minio/docker-compose.yml` | `minio` |
| `other-containers/traefik/docker-compose.yml` | `traefik` |

**⚠️ Critical safety rule:** because every included file shares the same project name, Docker Compose reconciles **all** resources under that project during any `up`/`down`, regardless of which specific compose file you invoke it from. Running `docker compose down` (even with a matching `-p infra-automation-lab`) from inside a subdirectory like `docker/mcp-server/` will stop and remove **every container in the entire lab**, not just that one service. This has happened before in this lab.

**Correct usage — always from `docker/` (the directory containing the root file):**

```bash
cd docker
docker compose up -d                    # start the whole lab
docker compose up -d --no-deps <service> # start/recreate ONE service only, safely
docker compose ps                        # status of everything
docker compose down                      # stop the whole lab (does NOT delete named volumes)
docker compose logs -f <service>         # tail logs for one service
```

**Never** run `docker compose down` scoped to a subdirectory's own compose file. If you must recreate a single container, use `docker compose up -d --no-deps <service>` from `docker/`, or `docker stop <container>` + `docker compose up -d <service>` from `docker/`.

### 1.3 Container Dependency Map

```
db (Postgres) ──┐
redis ──────────┼──> nautobot ──> celery_worker, celery_beat
                                        │
vault ──────────────────────────────────┤ (secrets, read by Terraform/Ansible/generator)
                                        │
gitlab ──> gitlab-runner (registers against gitlab, executes CI jobs)
                                        │
mcp-server ──> (reads/writes) nautobot, (reads) gitlab
                                        │
opa <── platform-api (legacy, not part of the active pipeline path)
                                        │
prometheus <── scrapes app-net targets
grafana ──> prometheus, loki (dashboards)
loki <── log aggregation target (not yet wired to ship container logs by default)
minio ──> knowledge_capture CI job (deployment history JSONL)
traefik ──> (reverse proxy, dynamic.yml — not required for core pipeline operation)
```

Startup order that matters: `db`/`redis` before `nautobot`; `nautobot` (healthy) before `celery_worker`/`celery_beat`; `gitlab` before `gitlab-runner` can register/run jobs; `mcp-server` needs `nautobot` and `gitlab` reachable at startup (fails fast otherwise). Everything else (`vault`, `opa`, `prometheus`, `grafana`, `loki`, `minio`, `traefik`) is independent and can start in any order.

### 1.4 Network Configuration

Three explicit, centrally-managed Docker networks (deliberately outside Docker's default `172.16.0.0/12` auto-allocation pool, which collides with the real ACI simulator's `172.30.46.0/24` subnet):

| Network | Subnet | Used by |
|---|---|---|
| `infra-automation-lab_app-net` | `10.200.0.0/22` | Nautobot stack, Vault, GitLab, GitLab Runner, MinIO, platform-api/OPA |
| `infra-automation-lab_obs-net` | `10.200.4.0/24` | Prometheus, Grafana, Loki |
| `infra-automation-lab_proxy-net` | `10.200.5.0/24` | Traefik |

The Nautobot stack's own compose files (managed in a nested, independently-versioned repo) still auto-allocate their own default network subnet from the `172.16.0.0/12` pool — a known, low-severity residual risk since Nautobot itself never talks to the ACI simulator directly.

Containers reach host-published services via `host.docker.internal` (via `extra_hosts: host-gateway`), not via container names, except within the same compose-managed network.

### 1.5 Persistent Storage Locations

All persistent data lives in **named Docker volumes** (not bind mounts, except where noted), all prefixed `infra-automation-lab_*`:

| Volume | Service | Contents |
|---|---|---|
| `environments_postgres_data` | Postgres | Nautobot database (declared `external: true` — Compose never deletes it) |
| `infra-automation-lab_vault_data` | Vault | Encrypted secrets storage |
| `infra-automation-lab_gitlab_config` | GitLab | `/etc/gitlab` — Omnibus config |
| `infra-automation-lab_gitlab_logs` | GitLab | `/var/log/gitlab` |
| `infra-automation-lab_gitlab_data` | GitLab | `/var/opt/gitlab` — repos, CI artifacts, DB |
| `infra-automation-lab_gitlab_runner_config` | GitLab Runner | `/etc/gitlab-runner/config.toml` |
| `infra-automation-lab_prometheus_data` | Prometheus | TSDB |
| `infra-automation-lab_grafana_data` | Grafana | Dashboards, users, sessions |
| `infra-automation-lab_loki_data` | Loki | Log chunks/index |
| `infra-automation-lab_minio_data` | MinIO | Object storage (Knowledge Capture bucket) |

Bind mounts (host filesystem, not volumes): `docker/nautobot/config/nautobot_config.py`, `docker/nautobot/jobs/`, `docker/vault/config`, `docker/vault/init`, `docker/vault/state` (contains `vault-keys.txt` — gitignored), `docker/other-containers/*/*.yml` config files, `docker/other-containers/grafana/provisioning/`.

`docker compose down` (without `-v`) never deletes named volumes — this is what makes container recreation safe. Only `docker compose down -v` or `docker volume rm` destroys data.

### 1.6 Secrets Management

Two mechanisms exist side by side:

1. **Environment files** (`docker/nautobot/environments/creds.env`, gitignored) — used directly by the Nautobot/Postgres/Redis containers via `env_file:`.
2. **HashiCorp Vault** (`secret/lab/nautobot`, `secret/lab/aci`, `secret/lab/platform`) — used by Terraform, Ansible, and the generator when run manually outside CI. See [§6](#6-hashicorp-vault).

Required environment variables that **must** be exported before running `docker compose up -d` from `docker/` (the compose files fail fast with a clear error if missing):

| Variable | Used by | Where to get it |
|---|---|---|
| `VAULT_TOKEN` | `platform-api` | `docker/vault/state/vault-keys.txt` ("Initial Root Token") |
| `NAUTOBOT_TOKEN` | `platform-api`, `mcp-server` | Shared lab dev token `0123456789abcdef0123456789abcdef01234567` (see [§2](#2-nautobot)) |
| `MCP_GITLAB_TOKEN` | `mcp-server` | A dedicated GitLab Project Access Token (`read_api` scope) — see [§9](#9-mcp-server) |
| `GRAFANA_ADMIN_PASSWORD` | `grafana` | Operator-chosen; only enforced at first container creation |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `minio` | **Must match** the value GitLab CI/CD project variables actually expect (see [§14](#14-minio)) — using a different placeholder on container recreation silently breaks the `knowledge_capture` CI job |

GitLab CI/CD's own pipeline secrets are managed as GitLab project variables — see [§7.6](#76-cicd-variables-and-secrets).

### 1.7 Certificate Management

**Requires Manual Configuration.** No TLS certificates are configured anywhere in this lab — every service is plain HTTP on `localhost`. GitLab's Omnibus config sets `external_url 'http://gitlab.local:8929'` (not HTTPS). Traefik has no TLS entrypoint configured (`--entrypoints.web.address=:80` only). If TLS is required, it must be added explicitly (Traefik `--entrypoints.websecure`, GitLab's `letsencrypt` Omnibus block, etc.) — not currently present.

### 1.8 Startup and Shutdown Procedures

**Full platform startup:**
```bash
cd docker
export VAULT_TOKEN=$(grep -oP '(?<=Initial Root Token: ).*' vault/state/vault-keys.txt)
export NAUTOBOT_TOKEN=0123456789abcdef0123456789abcdef01234567
export MCP_GITLAB_TOKEN=<see §9>
export GRAFANA_ADMIN_PASSWORD=<your choice>
export MINIO_ROOT_USER=<must match GitLab CI variable — see §14>
export MINIO_ROOT_PASSWORD=<must match GitLab CI variable — see §14>
docker compose up -d
```

**Full platform shutdown (data-preserving):**
```bash
cd docker
docker compose down          # stops and removes containers; named volumes survive
```

**Full platform teardown (destroys all data — confirm before running):**
```bash
cd docker
docker compose down -v
```

**Single-service restart (safe pattern):**
```bash
cd docker
docker compose up -d --no-deps <service-name>
```

### 1.9 Platform Update Procedure

**Requires Manual Configuration** — no automated update/upgrade tooling exists for this lab. In practice:
- Application code changes (`mcp-server`, `platform-api`): `docker compose build <service>` then `docker compose up -d --no-deps <service>` from `docker/`.
- Nautobot: rebuilt via `invoke build` in `docker/nautobot/` (see [§2.11](#211-common-administration-tasks)).
- Third-party images (GitLab, Vault, Grafana, Prometheus, Loki, MinIO, Traefik): pin/change the image tag in the relevant compose file, then `docker compose pull <service> && docker compose up -d --no-deps <service>` from `docker/`.

### 1.10 Disaster Recovery Considerations

- **Named volumes are the source of durable state.** As long as they survive, `docker compose up -d` from `docker/` fully reconstructs the platform (see the documented full-stack recovery in repo memory — a real incident recovered with zero data loss this way).
- **Vault's unseal key and root token** (`docker/vault/state/vault-keys.txt`) are required to unseal Vault after any full restart where the file itself is lost — back this file up separately if Vault's data must survive a host rebuild. Vault auto-unseals on every container restart as long as this file is present (single key-share, threshold 1 — a lab-only convenience, not a production pattern).
- **GitLab Project Access Tokens survive container recreation** (stored hashed in GitLab's own database/volume) — do not assume a token is invalid just because the `gitlab` container was recreated; check `GET /projects/:id/access_tokens` before minting a new one.
- **Nautobot's Postgres volume** (`environments_postgres_data`) is declared `external: true` specifically so `docker compose down -v` cannot accidentally delete it — it must be removed manually and deliberately (`docker volume rm environments_postgres_data`) if truly intended.
- There is no automated off-host backup for any volume in this lab — see each service's own "Backup Considerations" subsection below for manual procedures.

---

## 2. Nautobot

**Purpose:** the platform's Source of Truth for network inventory, topology, and desired state (Tenants, VRFs, Bridge Domains, EPGs, Contracts, L3Outs). All automation flows either read from or write to Nautobot.

### 2.1 Container Name
`infra-automation-lab-nautobot-1`

### 2.2 Service URL
`http://localhost:8080`

### 2.3 Default Ports
`8080` (HTTP, web UI + REST/GraphQL API)

### 2.4 Login URL
`http://localhost:8080/login/`

### 2.5 Default Administrator Credentials
| Field | Value | Source |
|---|---|---|
| Username | `admin` | `NAUTOBOT_SUPERUSER_NAME` in `docker/nautobot/environments/creds.env` |
| Password | `admin` | `NAUTOBOT_SUPERUSER_PASSWORD` in the same file |
| Email | `admin@example.com` | `NAUTOBOT_SUPERUSER_EMAIL` |
| API Token | `0123456789abcdef0123456789abcdef01234567` | `NAUTOBOT_SUPERUSER_API_TOKEN` — a fixed 40-char lab dev token used throughout this platform's automation |

### 2.6 Authentication Method
Django session auth (web UI, username/password) and Token auth (API — `Authorization: Token <token>` header). No SSO/LDAP configured by default, though `docker/nautobot/environments/docker-compose.ldap.yml` exists as an optional overlay (`NAUTOBOT_AUTH_LDAP_*` variables in `local.env`, currently placeholder `"changeme"` values — **Requires Manual Configuration** if LDAP is desired).

### 2.7 Important Configuration Files
| File | Purpose |
|---|---|
| `docker/nautobot/config/nautobot_config.py` | Main Nautobot settings (bind-mounted, live-editable without rebuild) — enables the `nautobot_ssot` plugin with `enable_aci = True` |
| `docker/nautobot/environments/local.env` | Non-secret settings (DB host, Redis host, log level, `ALLOWED_HOSTS`, etc.) |
| `docker/nautobot/environments/creds.env` | Secrets (DB/Redis passwords, secret key, superuser credentials, ACI simulator credentials) — **gitignored** |
| `docker/nautobot/environments/docker-compose.base.yml` | Service definitions for `nautobot`, `celery_worker`, `celery_beat`, `redis` |
| `docker/nautobot/environments/docker-compose.local.yml` | Local dev overrides: exposes port 8080, bind-mounts config/jobs for live editing |
| `docker/nautobot/jobs/` | Custom Nautobot Jobs (bind-mounted, live-editable) |
| `docker/nautobot/environments/Dockerfile` | Custom image build (base: `ghcr.io/nautobot/nautobot-dev`, installs `nautobot-ssot[aci]` via Poetry from `docker/nautobot/pyproject.toml`) |

### 2.8 Persistent Volumes and Stored Data
`environments_postgres_data` (external volume, holds the actual Nautobot database — see [§3](#3-postgresql-nautobot-database)). Nautobot's own container is stateless; all durable data lives in Postgres.

### 2.9 Environment Variables Administrators Should Know
| Variable | Purpose |
|---|---|
| `NAUTOBOT_ALLOWED_HOSTS` | Django `ALLOWED_HOSTS` — set to `*` in this lab |
| `NAUTOBOT_DB_HOST` / `NAUTOBOT_DB_NAME` / `NAUTOBOT_DB_USER` | Postgres connection (host `db`, db/user `nautobot`) |
| `NAUTOBOT_REDIS_HOST` / `NAUTOBOT_REDIS_PORT` | Redis connection (`redis:6379`) |
| `NAUTOBOT_LOG_LEVEL` | Default `WARNING` |
| `NAUTOBOT_CREATE_SUPERUSER` | `true` in `creds.env` — auto-creates the superuser on first migrate |
| `NAUTOBOT_METRICS_ENABLED` | `True` — exposes Prometheus-format metrics (scraped by `prometheus`, see [§11](#11-prometheus)) |
| `NAUTOBOT_MAX_PAGE_SIZE` | `0` (unlimited) — relevant to API pagination behavior |

### 2.10 Health Check / Status Verification
```bash
curl http://localhost:8080/health/                 # Django health endpoint
curl -H "Authorization: Token 0123456789abcdef0123456789abcdef01234567" http://localhost:8080/api/   # API root, version info
docker compose ps nautobot                           # container-level healthcheck status (from docker/)
```
Container healthcheck: an internal `urllib.request` fetch of `http://127.0.0.1:8080/`, every 30s.

### 2.11 Common Administration Tasks
All wrapped in `invoke` tasks, run from `docker/nautobot/`:
```bash
invoke build            # rebuild the custom Nautobot image
invoke start / stop / restart
invoke destroy           # CAUTION: removes containers AND volumes
invoke ps                 # status of all lab containers
invoke nbshell            # Django shell inside Nautobot
invoke cli                # interactive shell inside the nautobot container
invoke createsuperuser
invoke migrate
invoke post_upgrade
invoke db_export / invoke db_import   # database export/import
```

### 2.12 Log Locations and Viewing
```bash
docker compose logs -f nautobot          # from docker/
docker compose logs -f celery_worker
docker compose logs -f celery_beat
```
No file-based log persistence outside `docker logs` — logs are not currently shipped to Loki by default (**Requires Manual Configuration** if centralized log shipping is desired).

### 2.13 Backup Considerations
Use `invoke db_export` (wraps `pg_dump` against the `db` container) to produce a portable database export. The `environments_postgres_data` volume itself can also be backed up directly with `docker run --rm -v environments_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data`.

### 2.14 Dependencies on Other Services
Depends on `db` (Postgres) and `redis` at startup (`depends_on`). `celery_worker`/`celery_beat` depend on `nautobot` being healthy first.

### 2.15 Restart Procedures
```bash
cd docker
docker compose up -d --no-deps nautobot
docker compose up -d --no-deps celery_worker celery_beat   # after nautobot is healthy again
```

### 2.16 Common Troubleshooting Steps
- **Container unhealthy / won't start:** check `docker compose logs nautobot` for migration errors; confirm `db` is healthy first (`docker compose ps db`).
- **API returns 401/403:** confirm the token matches `NAUTOBOT_SUPERUSER_API_TOKEN` in `creds.env`; tokens are also viewable/creatable at `http://localhost:8080/user/api-tokens/`.
- **Job/plugin not showing up:** confirm `docker/nautobot/jobs/` is correctly bind-mounted (via `docker-compose.local.yml`) and that `nautobot_config.py` lists the plugin in `PLUGINS`/`PLUGINS_CONFIG`.
- **GraphQL query errors:** test directly with `curl -X POST http://localhost:8080/api/graphql/ -H "Authorization: Token <token>" -d '{"query": "{ tenants { name } }"}'`.

### API Endpoint, Token Management, Database Connection, Plugins, Jobs (Nautobot specifics requested)
- **API endpoint:** `http://localhost:8080/api/` (REST), `http://localhost:8080/api/graphql/` (GraphQL).
- **API token management:** Web UI → `http://localhost:8080/user/api-tokens/`, or `POST /api/users/tokens/` (admin can also manage others' tokens via `/api/users/tokens/` as superuser). The platform's own automation (generator, MCP Server) all use the single fixed dev token above; production use would require per-integration tokens.
- **Database connection:** `db:5432`, database `nautobot`, user `nautobot`, password from `NAUTOBOT_DB_PASSWORD` (`creds.env`, default `changeme`).
- **Installed plugins:** `nautobot_ssot` with `enable_aci = True` (ACI Data Source sync job) — configured in `docker/nautobot/config/nautobot_config.py`.
- **Jobs and scheduled tasks:** custom Jobs live in `docker/nautobot/jobs/` (bind-mounted); the "Cisco ACI Data Source" SSoT job is run manually or on a schedule via Nautobot's own Jobs UI (`http://localhost:8080/extras/jobs/`). Celery Beat (`celery_beat` container) handles any periodic task scheduling.
- **Device synchronization:** handled by the `nautobot_ssot` ACI Data Source job, which syncs Tenants/VRFs/Devices from the ACI simulator into Nautobot.
- **Object import/export:** Nautobot's built-in CSV import/export (per-model, via the web UI list views) plus `invoke db_export`/`db_import` for full-database operations.
- **Backup and restore:** see [§2.13](#213-backup-considerations) above; restore via `invoke db_import <file>`.

---

## 3. PostgreSQL (Nautobot database)

**Purpose:** relational database backing Nautobot — the actual storage for all Tenant/VRF/Prefix/Device/Job data.

**Container name:** `infra-automation-lab-db-1`
**Service URL:** not exposed on the host by default (internal `db:5432` only)
**Default ports:** `5432` (container-internal only — no host port mapping in the current compose files)
**Login:** no web UI; connect with any Postgres client to `db:5432` from within the `app-net`/Nautobot network, or `docker exec -it infra-automation-lab-db-1 psql -U nautobot -d nautobot`
**Credentials:** user `nautobot`, password from `NAUTOBOT_DB_PASSWORD` (`docker/nautobot/environments/creds.env`, default `changeme`)
**Authentication method:** Postgres native password auth
**Configuration files:** `docker/nautobot/environments/docker-compose.postgres.yml` (`max_connections=1000` set via command-line flag)
**Persistent volume:** `environments_postgres_data` (declared `external: true` — never deleted by `docker compose down -v`)
**Environment variables:** `POSTGRES_USER`, `POSTGRES_DB` (both derived from `NAUTOBOT_DB_USER`/`NAUTOBOT_DB_NAME`), `POSTGRES_PASSWORD`
**Health check:** `pg_isready --username=$POSTGRES_USER --dbname=$POSTGRES_DB` (container healthcheck, every 10s)
**Common admin tasks:** `invoke db_export`/`invoke db_import` (from `docker/nautobot/`); direct `psql` access via `docker exec`
**Logs:** `docker compose logs -f db` (from `docker/`)
**Backup considerations:** `pg_dump` via `invoke db_export`, or raw volume backup (see [§2.13](#213-backup-considerations))
**Dependencies:** none (base service); `nautobot` depends on it
**Restart:** `docker compose up -d --no-deps db` (from `docker/`) — note this restarts Nautobot's primary datastore, so expect brief Nautobot unavailability
**Troubleshooting:** connection refused from Nautobot → check `docker compose logs db` for startup errors; `too many connections` → review `max_connections=1000` setting and actual concurrent load

---

## 4. Redis (Nautobot)

**Purpose:** message broker for Celery (async task queue) and Nautobot's cache backend.

**Container name:** `infra-automation-lab-redis-1`
**Service URL:** not exposed on the host (internal `redis:6379` only)
**Default ports:** `6379` (container-internal only)
**Login:** `docker exec -it infra-automation-lab-redis-1 redis-cli -a <password>`
**Credentials:** password from `NAUTOBOT_REDIS_PASSWORD` (`creds.env`, default `changeme`) — used both as the Redis server's `--requirepass` and in Nautobot's `NAUTOBOT_CACHEOPS_REDIS` connection string (`redis://:<password>@redis:6379/1`)
**Authentication method:** Redis `requirepass`
**Configuration files:** command defined inline in `docker-compose.base.yml` (`redis-server --appendonly yes --requirepass $NAUTOBOT_REDIS_PASSWORD`)
**Persistent volume:** none declared (AOF persistence enabled via `--appendonly yes`, but no named volume — **data does not survive container removal**; Requires Manual Configuration if Redis durability is needed)
**Environment variables:** `NAUTOBOT_REDIS_HOST`, `NAUTOBOT_REDIS_PORT`, `NAUTOBOT_REDIS_PASSWORD`
**Health check:** none configured explicitly (**Requires Manual Configuration** if needed — `redis-cli ping` is the standard pattern)
**Common admin tasks:** `redis-cli` for inspection; Celery task queue is otherwise transparent to admins
**Logs:** `docker compose logs -f redis`
**Backup considerations:** none by default (no persistent volume); low priority since Redis here is a cache/broker, not a system of record
**Dependencies:** none
**Restart:** `docker compose up -d --no-deps redis` — will clear any in-flight Celery tasks
**Troubleshooting:** Celery tasks not processing → check `celery_worker` logs and confirm it can reach `redis:6379` with the correct password

---

## 5. Celery Worker & Celery Beat

**Purpose:** `celery_worker` executes Nautobot's asynchronous background jobs (SSoT syncs, bulk operations); `celery_beat` schedules periodic tasks.

**Container names:** `infra-automation-lab-celery_worker-1`, `infra-automation-lab-celery_beat-1`
**Service URL / ports:** none published — these are background workers, no web interface
**Login:** N/A (no UI); inspect via Nautobot's own Jobs UI (`http://localhost:8080/extras/jobs/`) which shows job run history/results
**Credentials:** same `creds.env`/`local.env` as Nautobot (shared `env_file`)
**Configuration:** entrypoint overridden inline in `docker-compose.base.yml` (`nautobot-server celery worker -l $NAUTOBOT_LOG_LEVEL --events` / `celery beat -l $NAUTOBOT_LOG_LEVEL`)
**Persistent volumes:** none (stateless — task state lives in Redis/Postgres)
**Health check:** `celery_worker` checks `celery worker` process presence via `/proc/1/cmdline`; `celery_beat` has healthcheck explicitly disabled
**Common admin tasks:** monitor via Nautobot Jobs UI; restart if jobs appear stuck
**Logs:** `docker compose logs -f celery_worker` / `celery_beat`
**Dependencies:** both depend on `nautobot` being `service_healthy` before starting
**Restart:** `docker compose up -d --no-deps celery_worker celery_beat`
**Troubleshooting:** jobs stuck in "pending" → check `celery_worker` logs for connection errors to Redis; verify `celery_beat` is running if a scheduled job never fires

---

## 6. HashiCorp Vault

**Purpose:** secrets storage for Terraform, Ansible, and the NetAsCode generator when run outside CI (holds Nautobot, ACI simulator, and platform tooling credentials).

**Container name:** `infra-automation-lab-vault`
**Service URL:** `http://localhost:8200`
**Default ports:** `8200`
**Login URL (UI):** `http://localhost:8200/ui`
**Administrator credentials:** the **root token**, printed to `docker/vault/state/vault-keys.txt` on first initialization (line `Initial Root Token: ...`). Retrieve with:
```bash
grep "Initial Root Token" docker/vault/state/vault-keys.txt
```
**Authentication method:** Vault root token (this lab uses a single-key-share, threshold-1 unseal — a lab-only convenience, never a production pattern)
**Important configuration files:**
| File | Purpose |
|---|---|
| `docker/vault/config/vault.hcl` | Server config — file storage backend at `/vault/data`, TLS disabled, UI enabled |
| `docker/vault/init/entrypoint.sh` | Custom entrypoint: starts Vault, auto-initializes on first run, auto-unseals on every restart, populates lab secrets |
| `docker/vault/state/vault-keys.txt` | Unseal key + root token (gitignored, generated on first init — **back this up if Vault data must survive a host rebuild**) |

**Persistent volumes:** `infra-automation-lab_vault_data` (`/vault/data` — encrypted secret storage)
**Environment variables:** `VAULT_ADDR=http://127.0.0.1:8200` (set internally in the compose file)
**Health check:** container healthcheck runs `vault status`, every 10s (90s start period, 10 retries — Vault's own init/unseal sequence takes time)
**Secrets stored (KV v2 engine at `secret/`):**
| Path | Contents |
|---|---|
| `secret/lab/nautobot` | `db_password`, `redis_password`, `secret_key`, `superuser_password`, `superuser_api_token` |
| `secret/lab/aci` | `username`, `password`, `url`, `insecure` (ACI simulator credentials) |
| `secret/lab/platform` | Combined Nautobot + ACI values consumed by Terraform/Ansible/generator when run manually |

**Common administration tasks:**
```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(grep "Initial Root Token" docker/vault/state/vault-keys.txt | awk '{print $NF}')
vault kv get secret/lab/platform          # read a secret
vault kv put secret/lab/platform key=value  # write/update a secret
vault status                                 # sealed/unsealed status, version
```
**Log locations:** `docker compose logs -f vault`
**Backup considerations:** back up `docker/vault/state/vault-keys.txt` (unseal key + root token) and the `infra-automation-lab_vault_data` volume together — the keys file alone is useless without the matching data volume, and vice versa.
**Dependencies:** none
**Restart procedure:** `docker compose up -d --no-deps vault` (from `docker/`) — auto-unseals automatically using the existing keys file, no manual intervention needed as long as `vault-keys.txt` is intact.
**Troubleshooting:**
- **Sealed after restart and auto-unseal didn't happen:** check that `docker/vault/state/vault-keys.txt` still exists and is readable inside the container; manually unseal with `vault operator unseal <unseal-key-from-file>`.
- **"connection refused" from Terraform/Ansible:** confirm `VAULT_ADDR`/`VAULT_TOKEN` are exported in the calling shell, and that the container is `Up (healthy)`.

---

## 7. GitLab CE

**Purpose:** the platform's execution engine — hosts the Git repository mirror, runs all CI/CD pipelines (validate → policy → plan → apply → configure → verify → capture), and receives Nautobot's webhook trigger.

### 7.1 GitLab URL
`http://gitlab.local:8929` (also reachable as `http://localhost:8929`)

### 7.2 Administrator Account
**Requires Manual Configuration for the actual password** — GitLab CE's initial root password is normally auto-generated on first boot and written to `/etc/gitlab/initial_root_password` inside the container (valid for 24 hours only, then GitLab deletes it). If that window has passed, reset it with:
```bash
docker exec -it infra-automation-lab-gitlab gitlab-rails runner "u = User.find_by(username: 'root'); u.password = 'NewPassword123!'; u.password_confirmation = 'NewPassword123!'; u.save!"
```
Username: `root`.

### 7.3 Container Name
`infra-automation-lab-gitlab`

### 7.4 Ports
`8929` (HTTP web UI/API), `8922` (SSH, mapped from the container's internal port 22 — configured via `gitlab_rails['gitlab_shell_ssh_port'] = 8922`)

### 7.5 Repository Locations
This project: `root/nautobot-infra-automation`, project ID **1**. Repository data lives inside the `infra-automation-lab_gitlab_data` volume (`/var/opt/gitlab`), not on the host filesystem directly.

### 7.6 CI/CD Variables and Secrets
Managed via the web UI (`Settings → CI/CD → Variables`) or the API (`GET/POST /api/v4/projects/1/variables`), or `gitlab-rails runner` for admin-level access when the API token lacks permission. Key variables used by this platform's pipeline:

| Variable | Purpose |
|---|---|
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Used by the `knowledge_capture` job to write to MinIO — **must match** the MinIO container's actual running credentials (see [§14](#14-minio)) |
| (Nautobot webhook trigger token) | A `Ci::Trigger` (`nautobot-tenant-webhook`) configured in Nautobot's own webhook settings, not a CI/CD variable — see [§7.8](#78-how-pipelines-are-triggered) |

Three distinct GitLab credentials exist in this lab, each for a different purpose — do not conflate them: `GIT_PUSH_TOKEN` (generator's auto-commit-and-push step writes generated YAML back to the repo), `PIPELINE_STATUS_TOKEN` (CI jobs like `write_results`/`knowledge_capture` read pipeline status from inside CI), and `mcp-server-status-reader` (the MCP Server's `show_status` tool reads pipeline status from outside CI — `read_api` scope only).

### 7.7 CI/CD Pipeline Overview
Defined in [`pipelines/aci.gitlab-ci.yml`](pipelines/aci.gitlab-ci.yml), which extends shared stage templates in [`pipelines/includes/common.gitlab-ci.yml`](pipelines/includes/common.gitlab-ci.yml). Seven stages, one job each:

```
generate_nac → validate_nac → policy_check → terraform_plan → terraform_apply
                                                                      ↓
                                                    ansible_configure → pyats_verify
                                                                      ↓
                                              write_results → knowledge_capture
```

| Job | What it does |
|---|---|
| `generate_nac` | Queries Nautobot via GraphQL, generates `platform/netascode/aci/tenants.yaml`, runs it twice to prove determinism, commits the result back to Git (`[skip ci]`) |
| `validate_nac` | Schema-validates the generated YAML |
| `policy_check` | Calls OPA (`platform/workflows/scripts/policy_check.py`) — fails closed if OPA is unreachable |
| `terraform_plan` / `terraform_apply` | Runs Terraform against the ACI simulator; `terraform_apply` requires manual approval (GitLab's protected-branch gate, a Premium "Protected Environments" substitute) |
| `ansible_configure` | Day-2 configuration via Ansible |
| `pyats_verify` | Independent validation via pyATS |
| `write_results` | Writes deployment status back to Nautobot custom fields |
| `knowledge_capture` | Appends a deployment record to MinIO (`knowledge-capture/aci/deployments.jsonl`) |

### 7.8 How Pipelines Are Triggered
Two paths:
1. **Nautobot webhook (the normal, AI-driven path):** any `tenancy.tenant` write in Nautobot (create/update) fires a webhook configured to call GitLab's Pipeline Trigger API using a dedicated `Ci::Trigger` token (`nautobot-tenant-webhook`, trigger ID 1). Pipelines from this path show `source: "trigger"` in the GitLab UI/API.
2. **Manual `git push` to `main`:** a normal push-triggered pipeline (`source: "push"`).

To manually fire the same trigger the webhook uses (for diagnostics only):
```bash
curl -X POST "http://localhost:8929/api/v4/projects/1/trigger/pipeline" \
  -F "token=<trigger-token>" -F "ref=main"
```

### 7.9 How to Monitor Pipeline Executions
- Web UI: `http://gitlab.local:8929/root/nautobot-infra-automation/-/pipelines`
- API: `GET /api/v4/projects/1/pipelines`, `GET /api/v4/projects/1/pipelines/:id/jobs`
- Via the MCP Server: `show_status(name=<tenant>)` merges the latest pipeline's live GitLab status with Nautobot's own recorded `validation_status` custom field.
- Job logs (trace): `GET /api/v4/projects/1/jobs/:id/trace`, or via `gitlab-rails runner` (`Ci::Build.find(id).trace.raw`) for admin-level access without a scoped token.

### 7.10 Runner Configuration
See [§8](#8-gitlab-runner) below — a single shared runner (`phase2-shared-runner`), Docker executor, `concurrent = 1`.

### 7.11 Common Administrative Operations
```bash
# Reset root password
docker exec -it infra-automation-lab-gitlab gitlab-rails runner "..."
# Check overall GitLab health
docker exec infra-automation-lab-gitlab gitlab-rake gitlab:check
# Reconfigure after an Omnibus config change
docker exec infra-automation-lab-gitlab gitlab-ctl reconfigure
# Tail logs
docker exec infra-automation-lab-gitlab gitlab-ctl tail
```

### 7.12 Authentication Method
GitLab's own username/password + session auth (web UI), Personal/Project Access Tokens (API), and SSH keys (Git over SSH on port 8922).

### 7.13 Health Check / Status Verification
```bash
curl -f http://localhost:8929/-/health
docker compose ps gitlab       # from docker/
```
Container healthcheck: `curl -f http://localhost:8929/-/health`, 30s interval, 180s start period (GitLab is slow to boot).

### 7.14 Log Locations
`infra-automation-lab_gitlab_logs` volume (`/var/log/gitlab` inside the container) — view via `docker exec infra-automation-lab-gitlab gitlab-ctl tail`, or `docker compose logs -f gitlab` for container stdout.

### 7.15 Backup Considerations
GitLab's own backup tooling works from inside the container:
```bash
docker exec infra-automation-lab-gitlab gitlab-backup create
```
Backups land in `/var/opt/gitlab/backups` inside the container (part of the `gitlab_data` volume) — copy them out to the host before any volume deletion.

### 7.16 Dependencies on Other Services
None required to start; `gitlab-runner` depends on `gitlab` being reachable to register and pick up jobs; the CI pipeline itself depends on Nautobot, OPA, the ACI simulator, and MinIO being reachable at the appropriate stages.

### 7.17 Restart Procedure
```bash
cd docker
docker compose up -d --no-deps gitlab
```
Allow several minutes for Omnibus services to fully come up (`start_period: 180s` in the healthcheck reflects this).

### 7.18 Troubleshooting
- **502/503 from the web UI right after restart:** GitLab Omnibus takes minutes to fully start all internal services (Puma, Sidekiq, Postgres, Redis, Gitaly) — wait for the healthcheck to report healthy.
- **Pipeline stuck at `created`, jobs never reach `pending`:** in this lab, pipelines fired via the raw trigger-token API have been observed to need a manual nudge: `docker exec infra-automation-lab-gitlab gitlab-rails runner "Ci::ProcessPipelineService.new(Ci::Pipeline.find(<id>)).execute"`. Not yet root-caused; webhook-triggered pipelines have not shown this symptom.
- **`policy_check`/`terraform_plan` failing on unrelated data:** the generator bundles *all* Nautobot tenants into one YAML file — a single bad tenant/VRF elsewhere can fail the whole pipeline. Check the job's trace log for the specific OPA/Terraform error before assuming a platform bug.

---

## 8. GitLab Runner

**Purpose:** executes GitLab CI/CD jobs (Docker executor) — the actual compute behind every pipeline stage.

**Container name:** `infra-automation-lab-gitlab-runner`
**Service URL / ports:** none published (outbound-only connection to GitLab)
**Login:** N/A (no UI) — managed entirely via `docker exec` and its registered config
**Credentials:** runner registration token, stored in `/etc/gitlab-runner/config.toml` inside the container (persisted in the `infra-automation-lab_gitlab_runner_config` volume)
**Authentication method:** runner auth token (`glrt-...`, registered against GitLab at container first-start)
**Configuration file:** `/etc/gitlab-runner/config.toml` (inside the container / `gitlab_runner_config` volume) — key settings:
```toml
concurrent = 1
[[runners]]
  name = "phase2-shared-runner"
  url = "http://host.docker.internal:8929"
  executor = "docker"
  [runners.docker]
    image = "alpine:latest"
    network_mode = "host"
    volumes = ["/cache"]
```
**Persistent volume:** `infra-automation-lab_gitlab_runner_config`
**Environment variables:** none required beyond the standard Docker socket mount (`/var/run/docker.sock`, giving the runner container the ability to spawn sibling job containers)
**Health check:** none configured explicitly — verify via `gitlab-runner verify` or checking the runner shows "online" in GitLab's Admin Area → CI/CD → Runners
**Common administration tasks:**
```bash
docker exec infra-automation-lab-gitlab-runner gitlab-runner verify
docker exec infra-automation-lab-gitlab-runner gitlab-runner list
```
**Log locations:** `docker compose logs -f gitlab-runner` (from `docker/`)
**Backup considerations:** low priority — the runner is stateless except for its registration token; re-registering is simple if lost
**Dependencies:** `gitlab` must be reachable for the runner to register and pick up jobs
**Restart procedure:** `docker compose up -d --no-deps gitlab-runner`
**Troubleshooting:**
- **Runner shows offline in GitLab:** check `docker compose logs gitlab-runner` for connection errors to `host.docker.internal:8929`.
- **Jobs fail with Docker-in-Docker errors:** confirm `/var/run/docker.sock` is correctly mounted and the host Docker daemon is running.
- **Only one job runs at a time:** expected — `concurrent = 1` is intentional for this lab-scale setup, not a misconfiguration.

---

## 9. MCP Server

**Purpose:** the AI-facing entry point to this platform. Exposes business-operation tools (`create_tenant`, `create_vrf`, `create_bridge_domain`, `create_epg`, `create_contract`, `create_l3out`, `show_status`) over the Model Context Protocol, letting AI agents (VS Code Copilot Agent, Claude Desktop) drive real infrastructure changes through natural language. It never orchestrates the pipeline itself — it only writes to Nautobot and reads status back from Nautobot/GitLab.

**Container name:** `infra-automation-lab-mcp-server`
**Service URL:** `http://localhost:8071` (MCP endpoint at `http://localhost:8071/mcp`)
**Default ports:** `8071`
**Login URL:** N/A — no human-facing web UI; accessed exclusively as an MCP server by AI clients
**Administrator/API credentials:** optional `MCP_API_KEY` (empty/disabled by default in this lab). Its *own* credentials to reach Nautobot/GitLab are `NAUTOBOT_TOKEN` (shared lab dev token) and `MCP_GITLAB_TOKEN` (a dedicated `read_api`-scoped GitLab Project Access Token, e.g. `mcp-server-status-reader` — never the root PAT)
**Authentication method:** two distinct auth boundaries — (1) AI client → MCP Server: optional API key (`MCP_API_KEY`, currently unset/disabled in this lab); (2) MCP Server → Nautobot/GitLab: token auth, held only server-side, never returned to the AI client
**Important configuration files:**
| File | Purpose |
|---|---|
| `mcp-server/src/mcp_server/config.py` | Environment-based settings (`NAUTOBOT_URL`, `NAUTOBOT_TOKEN`, `GITLAB_URL`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `MCP_API_KEY`, `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `LOG_LEVEL`) |
| `mcp-server/src/mcp_server/tools/aci.py` | Tool definitions (`create_tenant`, `create_vrf`, etc.) |
| `mcp-server/src/mcp_server/schemas/aci.py` | Per-tool Pydantic request schemas (thin validation, no shared intent envelope) |
| `mcp-server/src/mcp_server/clients/nautobot.py` | The only place tool code touches the Nautobot SDK directly |
| `docker/mcp-server/docker-compose.yml` | Container definition — `build:` (not a live volume mount), so code changes require a rebuild |
| `.vscode/mcp.json` | Client-side config wiring VS Code's Copilot Agent to this server (`type: http`, `url: http://localhost:8071/mcp`) |
**Persistent volumes:** none — the MCP Server is fully stateless
**Environment variables:**
| Variable | Purpose |
|---|---|
| `NAUTOBOT_URL` / `NAUTOBOT_TOKEN` | Nautobot connection |
| `GITLAB_URL` / `GITLAB_TOKEN` / `GITLAB_PROJECT_ID` | GitLab connection for `show_status` (project ID `1`) |
| `MCP_API_KEY` | Optional AI-client-facing auth (empty = disabled) |
| `MCP_TRANSPORT` | `stdio` (default, for locally-spawned clients) or `streamable-http` (used by this containerized deployment) |
| `MCP_HOST` / `MCP_PORT` | Bind address for `streamable-http` — `0.0.0.0:8071` in this deployment |
**Health check:** `GET http://localhost:8071/health` → `{"status": "ok", "checks": {"nautobot": "reachable", "gitlab": "reachable"}}`. Container healthcheck runs this same check every 15s.
**Common administration tasks:** rebuild after code changes:
```bash
cd docker/mcp-server && docker compose build mcp-server
cd docker && docker compose up -d --no-deps mcp-server
```
**Log locations:** `docker compose logs -f mcp-server` (from `docker/`)
**Backup considerations:** none needed — fully stateless; all durable state lives in Nautobot/GitLab
**Dependencies:** Nautobot and GitLab must both be reachable at startup — the container fails its healthcheck (though not its startup) if either is unreachable
**Restart procedure:** `docker compose up -d --no-deps mcp-server` (from `docker/`) — **never** `docker compose down` scoped to `docker/mcp-server/`, see [§1.2](#12-docker-compose-overview)
**Troubleshooting:**
- **Tools not appearing in VS Code:** confirm `.vscode/mcp.json` exists and points to the correct URL; run "MCP: List Servers" in the Command Palette to check connection state.
- **`/health` shows `"gitlab": "unreachable"`:** verify `GITLAB_TOKEN` is a valid, non-revoked Project Access Token with at least `read_api` scope.
- **Code changes not taking effect:** this container uses `build:`, not a live bind mount — you must rebuild the image, not just restart the container.

---

## 10. Platform API (legacy) & OPA

**⚠️ Platform API is legacy (Platform v1)** per [ADR-016](knowledge/adr/ADR-016-Platform-v2-Replacement-Architecture.md) — it is not extended or used by the current pipeline path, but its container (and the bundled OPA container) remain running because OPA is still actively used by the CI pipeline's `policy_check` job.

### Platform API
**Container name:** `infra-automation-lab-platform-api`
**Service URL:** `http://localhost:8000`
**Ports:** `8000`
**Purpose (legacy):** originally the Vertical Slice v0.1 Intent Lifecycle implementation; superseded by the MCP Server + GitLab CI Execution Framework. Do not build new functionality on it.
**Configuration:** `docker/platform-api/docker-compose.yml`; requires `NAUTOBOT_TOKEN` and `VAULT_TOKEN` environment variables at startup
**Persistent volumes:** `./data` bind mount (policy denial audit log, execution store SQLite DB, knowledge capture JSONL — all legacy artifacts)
**Health check:** `GET http://localhost:8000/health`
**Logs:** `docker compose logs -f platform-api`
**Restart:** `docker compose up -d --no-deps platform-api`

### OPA (Open Policy Agent)
**Container name:** `infra-automation-lab-opa`
**Service URL:** `http://localhost:8181`
**Ports:** `8181` (published specifically so GitLab CI jobs can reach it at `localhost:8181` via the runner's `network_mode: host`)
**Purpose:** evaluates the `cisco_aci` policy package against generated NetAsCode YAML during the `policy_check` CI stage — called directly by `platform/workflows/scripts/policy_check.py`, not through the legacy Platform API.
**Configuration files:** Rego policy files bind-mounted read-only from `docker/platform-api/policy/` to `/policy` inside the container.
**Persistent volumes:** none (policy files are bind-mounted, not stored in a volume)
**Health check:** none possible — the official OPA image has no shell/wget/curl to run one; `depends_on` only waits for container start, not readiness. `policy_check.py` fails closed (treats an unreachable OPA as a denial) so this is a correctness non-issue.
**Logs:** `docker compose logs -f opa`
**Restart:** `docker compose up -d --no-deps opa`
**Troubleshooting:** `policy_check` job failing with a connection error → confirm the `opa` container is `Up` (`docker compose ps opa`) and that `OPA_URL` in the CI job matches `http://localhost:8181` (the runner uses `network_mode: host`, so `localhost` resolves to the host machine, not the container).

---

## 11. Prometheus

**Purpose:** metrics collection — scrapes Nautobot's Prometheus-format metrics endpoint (and any other configured targets) for observability.

**Container name:** `infra-automation-lab-prometheus`
**Service URL:** `http://localhost:9090`
**Ports:** `9090`
**Login URL:** `http://localhost:9090` (no authentication configured — open access within the lab)
**Credentials:** none configured (**Requires Manual Configuration** if auth is needed)
**Authentication method:** none
**Configuration file:** `docker/other-containers/prometheus/prometheus.yml` (scrape configs — bind-mounted read-only)
**Persistent volume:** `infra-automation-lab_prometheus_data` (`/prometheus` — TSDB)
**Environment variables:** none required
**Health check:** `GET http://localhost:9090/-/healthy` (container healthcheck, 15s interval)
**Common administration tasks:** edit `prometheus.yml` to add scrape targets, then restart (config is not hot-reloaded via API in this setup — **Requires Manual Configuration** to enable `--web.enable-lifecycle` if hot-reload is desired)
**Logs:** `docker compose logs -f prometheus`
**Backup considerations:** TSDB volume can be backed up directly (`docker run --rm -v infra-automation-lab_prometheus_data:/data ...`); typically low priority for a lab
**Dependencies:** scrapes Nautobot (`app-net`) — network connectivity between `obs-net` and scrape targets should be verified if metrics appear missing
**Restart procedure:** `docker compose up -d --no-deps prometheus`
**Troubleshooting:** missing metrics → check `http://localhost:9090/targets` for scrape target health; connectivity issues between `obs-net` and `app-net` targets are the most likely cause

---

## 12. Grafana

**Purpose:** dashboards and visualization over Prometheus metrics and Loki logs.

**Container name:** `infra-automation-lab-grafana`
**Service URL:** `http://localhost:3000`
**Ports:** `3000`
**Login URL:** `http://localhost:3000/login`
**Administrator credentials:** username `admin`; password from the `GRAFANA_ADMIN_PASSWORD` environment variable (**must be exported before first container creation** — the compose file fails fast if unset: `GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:?...}"`). This value only takes effect the first time the container/volume is created — subsequent restarts with a different value do **not** change the already-provisioned admin password.
**Authentication method:** Grafana native username/password
**Configuration files:** `docker/other-containers/grafana/.env`, `docker/other-containers/grafana/provisioning/` (dashboard/datasource provisioning, bind-mounted read-only)
**Persistent volume:** `infra-automation-lab_grafana_data` (`/var/lib/grafana` — dashboards, users, sessions, the actual effective admin password)
**Environment variables:** `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`
**Health check:** `GET http://localhost:3000/api/health`
**Common administration tasks:** add datasources/dashboards via the UI or drop provisioning YAML into `provisioning/`
**Logs:** `docker compose logs -f grafana`
**Backup considerations:** back up the `grafana_data` volume to preserve dashboards/users; provisioning files are already version-controlled
**Dependencies:** Prometheus and Loki (as datasources) — not a hard startup dependency, but dashboards will show no data if they're down
**Restart procedure:** `docker compose up -d --no-deps grafana`
**Troubleshooting:** forgot admin password → reset via `docker exec infra-automation-lab-grafana grafana-cli admin reset-admin-password <newpassword>`; a mismatched `GRAFANA_ADMIN_PASSWORD` env var on restart does **not** fix this — the volume already has the real password.

---

## 13. Loki

**Purpose:** log aggregation backend, queried by Grafana. **Note:** container logs are not currently shipped to Loki automatically in this lab — it is provisioned as a target but no log-shipping agent (Promtail, etc.) is configured (**Requires Manual Configuration** if centralized logging is desired).

**Container name:** `infra-automation-lab-loki`
**Service URL:** `http://localhost:3100`
**Ports:** `3100`
**Login:** N/A — no UI (queried through Grafana or its own API directly)
**Credentials:** none configured
**Authentication method:** none
**Configuration file:** `docker/other-containers/loki/loki-config.yml` (bind-mounted read-only)
**Persistent volume:** `infra-automation-lab_loki_data` (`/loki`)
**Health check:** none configured — the `grafana/loki` image is minimal/shell-less with no `wget`/`curl` available for a healthcheck command; verify via `curl http://localhost:3100/ready` from the host instead
**Common administration tasks:** query via Grafana's Explore view, or directly: `curl http://localhost:3100/loki/api/v1/query?query={job="..."}`
**Logs:** `docker compose logs -f loki` (Loki's own container logs, not the logs it stores)
**Backup considerations:** back up `loki_data` volume if historical logs must be preserved; typically low priority for a lab
**Dependencies:** none
**Restart procedure:** `docker compose up -d --no-deps loki`
**Troubleshooting:** no logs visible in Grafana → confirm nothing is actually shipping logs to Loki yet (expected in the current setup) rather than assuming Loki itself is broken

---

## 14. MinIO

**Purpose:** S3-compatible object storage — stores the Knowledge Capture deployment history (`knowledge-capture/aci/deployments.jsonl`), written by the `knowledge_capture` CI job after every pipeline run.

**Container name:** `infra-automation-lab-minio`
**Service URL:** `http://localhost:9000` (S3 API), `http://localhost:9091` (web console)
**Ports:** `9000` (API), `9091` (console)
**Login URL:** `http://localhost:9091`
**Administrator credentials:** from `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` environment variables, **required at container start** (compose file fails fast if unset). These become the container's *actual* root credentials every time it starts — this is not a first-run-only value.

**⚠️ Critical operational note:** GitLab CI/CD has its own stored project variables for `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (used by the `knowledge_capture` job). If you ever recreate the `minio` container with different values than what GitLab CI expects, the `knowledge_capture` job will fail with `InvalidAccessKeyId` even though nothing else appears wrong. **Always check GitLab's stored project variables first** (`Settings → CI/CD → Variables`, or via `gitlab-rails runner "Project.find(1).variables.each { |v| puts v.key }"`) before choosing values to export for a MinIO restart.

**Authentication method:** S3-style access key/secret key (root user), same credentials serve both the API and the web console
**Configuration files:** none beyond the compose file's environment block — no separate config file
**Persistent volume:** `infra-automation-lab_minio_data` (`/data`)
**Environment variables:** `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
**Health check:** `GET http://localhost:9000/minio/health/live` (container healthcheck, 15s interval)
**Common administration tasks:** browse/manage the `knowledge-capture` bucket via the web console at `http://localhost:9091`, or the `mc` CLI against `http://localhost:9000`
**Logs:** `docker compose logs -f minio`
**Backup considerations:** back up the `minio_data` volume to preserve deployment history; the same data can also be re-derived from GitLab's own pipeline artifacts if lost, since `knowledge_capture` also writes a local JSONL artifact
**Dependencies:** none required to start; the `knowledge_capture` CI job depends on it being reachable
**Restart procedure:** `docker compose up -d --no-deps minio` (from `docker/`) — **always confirm the exported `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` match GitLab's stored CI variables first**, per the note above
**Troubleshooting:** `knowledge_capture` job fails with `InvalidAccessKeyId` → this is almost always a credential mismatch between the running container and GitLab's stored CI variables; verify both match exactly.

---

## 15. Traefik

**Purpose:** reverse proxy / dashboard, configured but not required for core pipeline operation in this lab — no service currently depends on routing through it for correctness.

**Container name:** `infra-automation-lab-traefik`
**Service URL:** `http://localhost:8090` (proxied HTTP entrypoint), `http://localhost:8091` (Traefik API/dashboard)
**Ports:** `8090` (web entrypoint, mapped from container port 80), `8091` (dashboard/API, mapped from container port 8080)
**Login URL:** `http://localhost:8091/dashboard/` (dashboard is `--api.insecure=true` — **no authentication**, lab-only setting)
**Credentials:** none — insecure dashboard mode
**Authentication method:** none configured
**Configuration file:** `docker/other-containers/traefik/dynamic.yml` (bind-mounted read-only, file provider with watch enabled)
**Persistent volume:** none
**Environment variables:** none required
**Health check:** none configured explicitly (**Requires Manual Configuration** if needed — `traefik healthcheck` command is the standard pattern)
**Common administration tasks:** edit `dynamic.yml` to add routing rules — hot-reloaded automatically (`--providers.file.watch=true`)
**Logs:** `docker compose logs -f traefik`
**Backup considerations:** none needed — fully stateless, configuration is version-controlled
**Dependencies:** routes to whatever backends are defined in `dynamic.yml`
**Restart procedure:** `docker compose up -d --no-deps traefik`
**Troubleshooting:** routing not working → check `dynamic.yml` syntax and confirm the target service is reachable from the `proxy-net` network; check the dashboard at `:8091/dashboard/` for router/service health

---

## 16. Quick Reference Table

| Component | Purpose | URL | Admin Login | Configuration Location | Logs | Health Check |
|---|---|---|---|---|---|---|
| **Nautobot** | Source of Truth (network inventory/state) | http://localhost:8080 | `admin` / `admin` (`creds.env`) | `docker/nautobot/config/nautobot_config.py`, `environments/*.env` | `docker compose logs -f nautobot` | `GET /health/` |
| **PostgreSQL** | Nautobot database | internal `db:5432` | `nautobot` / `NAUTOBOT_DB_PASSWORD` | `docker-compose.postgres.yml` | `docker compose logs -f db` | `pg_isready` |
| **Redis** | Celery broker / Nautobot cache | internal `redis:6379` | password `NAUTOBOT_REDIS_PASSWORD` | `docker-compose.base.yml` | `docker compose logs -f redis` | None configured |
| **Celery Worker/Beat** | Async job execution/scheduling | N/A (no UI) | N/A | `docker-compose.base.yml` | `docker compose logs -f celery_worker` | Process-presence check |
| **HashiCorp Vault** | Secrets storage | http://localhost:8200/ui | Root token in `docker/vault/state/vault-keys.txt` | `docker/vault/config/vault.hcl` | `docker compose logs -f vault` | `vault status` |
| **GitLab CE** | Execution engine (CI/CD, Git) | http://gitlab.local:8929 | `root` / (initial password expires in 24h — reset via `gitlab-rails runner`) | `other-containers/gitlab/docker-compose.yml` (Omnibus config inline) | `gitlab-ctl tail` | `GET /-/health` |
| **GitLab Runner** | CI job executor | N/A (no UI) | N/A | `/etc/gitlab-runner/config.toml` (in volume) | `docker compose logs -f gitlab-runner` | `gitlab-runner verify` |
| **MCP Server** | AI-agent entry point (business-operation tools) | http://localhost:8071/mcp | N/A (optional `MCP_API_KEY`) | `mcp-server/src/mcp_server/config.py` | `docker compose logs -f mcp-server` | `GET /health` |
| **Platform API** (legacy) | Superseded Intent Lifecycle API | http://localhost:8000 | N/A | `docker/platform-api/docker-compose.yml` | `docker compose logs -f platform-api` | `GET /health` |
| **OPA** | Policy evaluation (`policy_check` CI stage) | http://localhost:8181 | N/A | `docker/platform-api/policy/` (Rego files) | `docker compose logs -f opa` | None possible (no shell in image) |
| **Prometheus** | Metrics collection | http://localhost:9090 | None configured | `other-containers/prometheus/prometheus.yml` | `docker compose logs -f prometheus` | `GET /-/healthy` |
| **Grafana** | Dashboards | http://localhost:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` (env var, first-run only) | `other-containers/grafana/provisioning/` | `docker compose logs -f grafana` | `GET /api/health` |
| **Loki** | Log aggregation (not yet fed by log shippers) | http://localhost:3100 | None configured | `other-containers/loki/loki-config.yml` | `docker compose logs -f loki` | `GET /ready` (no container healthcheck) |
| **MinIO** | Object storage (Knowledge Capture) | http://localhost:9091 (console) | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (env vars — must match GitLab CI variables) | `other-containers/minio/docker-compose.yml` (env-only, no config file) | `docker compose logs -f minio` | `GET /minio/health/live` |
| **Traefik** | Reverse proxy / dashboard | http://localhost:8091/dashboard/ | None (insecure dashboard mode) | `other-containers/traefik/dynamic.yml` | `docker compose logs -f traefik` | None configured |

---

*This guide reflects the platform state as of 2026-07-29. If a service is added, removed, or reconfigured, update the corresponding section and the Quick Reference table above.*
