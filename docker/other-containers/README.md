# Other Containers

Lab infrastructure services beyond the Nautobot stack, each its own independent Docker
Compose stack (own directory, own `docker-compose.yml`), included from the root
[`docker/docker-compose.yml`](../docker-compose.yml).

| Directory | Service | Role |
|---|---|---|
| `gitlab/` | GitLab CE | The execution engine — runs the domain pipelines (`pipelines/aci.gitlab-ci.yml`, `pipelines/evpn.gitlab-ci.yml`) |
| `gitlab-runner/` | GitLab Runner | Executes GitLab CI jobs |
| `prometheus/` | Prometheus | Metrics collection |
| `grafana/` | Grafana | Dashboards |
| `loki/` | Loki | Log aggregation |
| `minio/` | MinIO | S3-compatible storage for the Knowledge Capture JSONL log |
| `traefik/` | Traefik | Reverse proxy |

For ports, credentials, startup/restart procedures, and troubleshooting for every one of
these, see [`Platform-Administration-Guide.md`](../../Platform-Administration-Guide.md) —
the authoritative operational reference for the whole lab. This file is just a directory
map.
