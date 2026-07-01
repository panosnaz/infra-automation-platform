# Lab

Local lab environment for the Nautobot ACI Infrastructure Automation project.
All services run as Docker containers managed by Docker Compose and the `invoke` task runner.

---

## Directory Structure

```
lab/
├── README.md
└── docker/
    ├── nautobot/                        # Nautobot stack (primary)
    │   ├── pyproject.toml               # Python dependencies (nautobot-ssot[aci], invoke)
    │   ├── tasks.py                     # Invoke task runner entry point
    │   ├── invoke.example.yml           # Default invoke configuration reference
    │   ├── config/
    │   │   └── nautobot_config.py       # Nautobot config (bind-mounted into containers)
    │   ├── jobs/                        # Nautobot jobs (bind-mounted into containers)
    │   └── environments/
    │       ├── Dockerfile               # Custom Nautobot image build definition
    │       ├── docker-compose.base.yml  # Service definitions (nautobot, celery, redis)
    │       ├── docker-compose.postgres.yml  # Postgres service + volume
    │       ├── docker-compose.local.yml # Local dev overrides (ports, bind mounts)
    │       ├── local.env                # Non-secret environment variables
    │       ├── local.example.env        # Reference template for local.env
    │       ├── creds.env                # Secrets (passwords, API tokens, ACI credentials)
    │       └── creds.example.env        # Reference template for creds.env
    └── other-containers/                # Placeholder for future additional services
```

---

## Docker Compose Stack

The stack is composed of three merged Compose files. Together they define the
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
# from lab/docker/nautobot/
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
