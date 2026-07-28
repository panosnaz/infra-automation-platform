---
type: architecture
domain: platform
status: active
tags: [platform-v2, as-built]
owner: platform-engineering-team
last_updated: 2026-07-28
---

# Platform v2 — As-Built Record

**Project:** Network Platform Engineering Platform

**Document Type:** As-Built (implementation record)

**Status:** Live — Phase 1 infrastructure implemented and validated

**Owner:** Platform Engineering Team

**Date:** 2026-07-28

> **Relationship to other documents:** [`Platform-v2-Reference-Architecture.md`](Platform-v2-Reference-Architecture.md) is the **target** architecture — what should exist. This document is the **as-built** record — what actually exists today, what deviates from the target and why, and what evidence backs each claim. Validation evidence lives in [`../runbooks/Phase1-Infrastructure-Validation-Report.md`](../runbooks/Phase1-Infrastructure-Validation-Report.md). Where this document and the reference architecture disagree, the reference architecture still wins as the intended target — this document exists to make the gap visible, not to redefine the target.

---

# 1. Component Status vs. Reference Architecture

| Service | Reference architecture status | As-built status | Notes |
|---|---|---|---|
| `nautobot` | Core (existing) | ✅ Deployed, healthy | Unchanged by Phase 1 |
| `postgres` | Core (existing) | ✅ Deployed, healthy | Unchanged |
| `redis` | Core (existing) | ✅ Deployed, healthy | Unchanged |
| `vault` | Core (existing) | ✅ Deployed, healthy | Stale compose-project path reconciled this phase; no content change |
| `opa` | Core (existing) | ✅ Deployed, running (no healthcheck — image has no shell, documented precedent) | Unchanged |
| `gitlab` | New — Core | ✅ Deployed, healthy | Two Omnibus config errors found and fixed (§2) |
| `gitlab-runner` | New — Core | ⏳ Compose file created, **not started** | Deliberately deferred — needs a GitLab registration token (Phase 2) |
| `mcp-server` | New — Core | ❌ Not built | Phase 2/3 scope — this is the biggest remaining gap vs. the reference architecture |
| `prometheus` | New — Reusable | ✅ Deployed, healthy | Scrape targets for `nautobot`/`platform-api` are configured but **down** — see §3 |
| `grafana` | New — Reusable | ✅ Deployed, healthy | Datasources provisioned and health-checked OK |
| `loki` | New — Reusable | ✅ Deployed, running | Healthcheck removed (image has no shell/wget — §2.2); subnet fixed after causing an external connectivity regression (§4) |
| `minio` | New — Optional | ✅ Deployed, healthy | No buckets in use yet — not wired to anything (expected; Phase 2 scope) |
| `traefik` | New — Optional | ✅ Deployed, running | 4/4 routes verified; no healthcheck defined yet (`/ping` not configured) |
| `docs` (MkDocs) | New — Optional, low priority | ❌ Not built | Unchanged from reference architecture (still low priority) |

**Overall:** 11 of 14 reference-architecture services are deployed and healthy. `mcp-server` and `docs` are not yet built (expected — out of Phase 1 scope). `gitlab-runner` is intentionally staged but not started.

---

# 2. GitLab — Deviations and Fixes Applied

The reference architecture's Container Architecture table (§2) specifies GitLab Omnibus with a `/-/health` healthcheck and no further detail on `gitlab.rb` contents. Two real-world Omnibus configuration errors were discovered during implementation that the reference architecture did not anticipate, since it predates any actual GitLab deployment:

## 2.1 `grafana['enable']` — removed config key

GitLab 17.2.2 no longer supports `grafana['enable']` as an Omnibus config key at all (bundled Grafana was removed from Omnibus in an earlier GitLab release). Setting it to any value — even `false` — causes `gitlab-ctl reconfigure` to fail with `Mixlib::Config::UnknownConfigOptionError` on every restart, producing a crash-loop. **Fix:** removed the line entirely from the `GITLAB_OMNIBUS_CONFIG` heredoc in `docker/other-containers/gitlab/docker-compose.yml`. `prometheus_monitoring['enable'] = false` and `alertmanager['enable'] = false` remain valid and are kept, since this lab already runs its own Prometheus/Grafana/Loki stack.

## 2.2 `sidekiq['max_concurrency']` — renamed config key

Removed in GitLab 17.0, replaced by `sidekiq['concurrency']`. Omnibus reconfigure aborts on the **first** unrecognized key it finds per run — this second error was only discovered after fixing the first and re-running reconfigure. **Fix:** renamed to `sidekiq['concurrency'] = 10`.

## 2.3 Loki healthcheck removed (adjacent finding, same session)

`grafana/loki:latest` is a minimal image with **no shell, no wget, no curl** at all (confirmed via failed `docker exec ... wget`/`which`). A `CMD`-array healthcheck referencing `wget` can never succeed. **Fix:** removed the healthcheck block entirely — Loki now shows a plain running state with no health column, the same precedent already established by the existing `opa` container in this repo (also shell-less, also undocumented-as-a-defect).

**Result after fixes:** GitLab reports `healthy` in `docker ps`; root page returns `302` to sign-in; the container-internal healthcheck (`curl -f http://localhost:8929/-/health`, run from loopback inside the container) passes. External curls to `/-/health` return `404` — expected GitLab behavior (monitoring endpoints IP-whitelisted to loopback by default), not a defect.

---

# 3. Prometheus — Scrape Target Gap

The reference architecture's networking diagram (§3, §4) shows Prometheus scraping `app-net` targets including implicitly Nautobot and Platform API. In practice:

* Neither `nautobot` nor `platform-api` currently expose a Prometheus-format `/metrics` endpoint (`nautobot` returns `406 Not Acceptable`; `platform-api` returns `404 Not Found`).
* Prometheus's own scrape of itself (`localhost:9090/metrics`) is healthy.

This is a genuine implementation gap versus the target, not a Prometheus configuration problem — see the validation report §2 for full evidence, and §10's action items.

---

# 4. Docker Networking — One Real Deviation from the "No New Bridge Network" Principle

The reference architecture's Docker Networking Diagram (§3) describes three explicit named networks (`app-net`, `obs-net`, `proxy-net`) with deliberately chosen, non-conflicting subnets. Phase 1's actual implementation deviated from this: each new service was given **its own Docker Compose default network** (unnamed, Docker-auto-allocated), following the pattern already proven by `platform-api` rather than pre-declaring the three named networks up front.

This worked cleanly for every service except `loki`, whose auto-allocated subnet (`172.30.0.0/16`) happened to fully contain the real ACI simulator's address (`172.30.46.103`), hijacking routing for any container that needed to reach it. This is documented in full, with root-cause evidence, in the validation report §9.

**Fix applied:** pinned an explicit subnet (`10.220.0.0/24`) on `loki`'s network rather than retroactively adopting the reference architecture's three-named-network model. **This remains a deviation worth revisiting in Phase 2** — the reference architecture's explicit `app-net`/`obs-net`/`proxy-net` model with deliberately chosen subnets would prevent this entire class of collision by design, rather than requiring a manual pin per-service after the fact. Recommendation: adopt the three-named-network model when the MCP Server is introduced, since that is also the point at which cross-network traffic (MCP → Nautobot, MCP → GitLab, MCP → Vault) becomes real rather than host-port-mediated.

---

# 5. What Has Not Changed

Consistent with ADR-016's "replacement, not migration" framing and this phase's explicit "extend, not rebuild" scope: `platform-api`, `nautobot`, `postgres`, `redis`, `opa`, and `vault` were not modified in any functional way. Vault's only change was a compose-project-path reconciliation (no content/data change). The full 44-unit + 7-integration regression suite that Milestone 6A established continues to pass unmodified (re-verified this phase — see validation report).

---

# 6. Summary of Remaining Gaps vs. Reference Architecture

1. `mcp-server` — not built (largest gap; Phase 2/3 scope per Roadmap).
2. `gitlab-runner` — created but not registered/started.
3. Prometheus scrape targets for `nautobot`/`platform-api` — configured but non-functional (no metrics endpoints exposed).
4. Three named networks (`app-net`/`obs-net`/`proxy-net`) — not adopted; per-service default networks used instead, with one subnet pinned manually after a collision.
5. `docs` (MkDocs) — not built (still explicitly low priority in the reference architecture itself).
6. Traefik `/ping` healthcheck and `*.lab.local` `/etc/hosts` entries — not yet added.
