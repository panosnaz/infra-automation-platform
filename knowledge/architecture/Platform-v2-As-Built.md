---
type: architecture
domain: platform
status: active
tags: [platform-v2, as-built]
owner: platform-engineering-team
last_updated: 2026-07-29
---

# Platform v2 — As-Built Record

**Project:** Network Platform Engineering Platform

**Document Type:** As-Built (implementation record)

**Status:** Live — Phase 1 infrastructure implemented and validated; gitlab-runner and MinIO status corrected 2026-07-29 (both were already in active use, this doc had not been updated since Execution Framework Milestones 1-4 shipped)

**Owner:** Platform Engineering Team

**Date:** 2026-07-28

> **Relationship to other documents:** [`Platform-v2-Reference-Architecture.md`](Platform-v2-Reference-Architecture.md) is the **target** architecture — what should exist. This document is the **as-built** record — what actually exists today, what deviates from the target and why, and what evidence backs each claim. Validation evidence lives in [`Phase1-Infrastructure-Validation-Report.md`](Phase1-Infrastructure-Validation-Report.md). Where this document and the reference architecture disagree, the reference architecture still wins as the intended target — this document exists to make the gap visible, not to redefine the target.

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
| `gitlab-runner` | New — Core | ✅ Registered and online (`phase2-shared-runner`) | Registered during Milestone 1 (Execution-Framework.md); this row predates that and was never updated |
| `mcp-server` | New — Core | ❌ Not built | Milestone 5 scope (Execution-Framework.md §6) — this is the biggest remaining gap vs. the reference architecture |
| `prometheus` | New — Reusable | ✅ Deployed, healthy | Scrape targets for `nautobot`/`platform-api` are configured but **down** — see §3 |
| `grafana` | New — Reusable | ✅ Deployed, healthy | Datasources provisioned and health-checked OK |
| `loki` | New — Reusable | ✅ Deployed, running | Healthcheck removed (image has no shell/wget — §2.2); subnet fixed after causing an external connectivity regression (§4) |
| `minio` | New — Optional | ✅ Deployed, healthy, **in active use** | `knowledge-capture` bucket holds real Execution Framework Milestone 4 Knowledge Capture JSONL records (see Execution-Framework.md §6) |
| `traefik` | New — Optional | ✅ Deployed, running | 4/4 routes verified; no healthcheck defined yet (`/ping` not configured) |
| `docs` (MkDocs) | New — Optional, low priority | ❌ Not built | Unchanged from reference architecture (still low priority) |

**Overall:** 12 of 14 reference-architecture services are deployed and healthy or in active use. `mcp-server` and `docs` are not yet built (expected — Milestone 5+ and low-priority scope respectively). `gitlab-runner` is registered and online (updated 2026-07-29; this table previously said "not started", which was stale as of Milestone 1).

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

# 4. Docker Networking — Consolidated (resolved 2026-07-28)

The reference architecture's Docker Networking Diagram (§3) describes three explicit named networks (`app-net`, `obs-net`, `proxy-net`) with deliberately chosen, non-conflicting subnets. This is now fully implemented: a single root [`docker/docker-compose.yml`](../../docker/docker-compose.yml) uses Compose's `include:` to bring all 9 non-Nautobot stacks plus Nautobot's own (referenced, never edited — it remains an independently-managed nested git repository) under one Compose project (`infra-automation-lab`), on three centrally-managed networks with explicit subnets (`app-net` 10.200.0.0/22, `obs-net` 10.200.4.0/24, `proxy-net` 10.200.5.0/24) — all outside Docker's `172.16.0.0/12` default auto-allocation pool, eliminating the entire class of subnet-collision bug that hit this stack twice (Loki, then GitLab Runner) during Phase 1.

**Two real issues were hit and fixed during this consolidation, both now documented as lessons in repo memory:**

1. **Project-name reconciliation risk.** Compose reconciles *all* resources sharing a project name during `up`/`down`, not just what's declared in the current invocation. An early attempt that didn't include Nautobot's files (while still using the same project name) caused Compose to treat Nautobot's network as orphaned and briefly disrupt it. Fixed by including Nautobot's existing files by reference.
2. **Volume/network key collisions under `include:`.** Compose merges all included files' top-level `volumes:`/`networks:` keys into one flat namespace — generic local key names (e.g. `data`, `config`) used by multiple files collide, with one silently winning and unrelated services ending up mounted on the wrong volume (confirmed: MinIO briefly mounted onto GitLab's own data volume). Fixed by renaming every volume key to be globally unique (`grafana_data`, `gitlab_config`, `gitlab_runner_config`, etc.) — the external Docker volume `name:` values were never affected, only the local YAML keys.

Full incident detail: [`Current-State-v1.md`](archive/Current-State-v1.md)'s 2026-07-28 entries. **This closes the deviation this section used to describe as "worth revisiting in Phase 2" — it is no longer a deviation.**

---

# 5. What Has Not Changed

Consistent with ADR-016's "replacement, not migration" framing and this phase's explicit "extend, not rebuild" scope: `platform-api`, `nautobot`, `postgres`, `redis`, `opa`, and `vault` were not modified in any functional way. Vault's only change was a compose-project-path reconciliation (no content/data change). The full 44-unit + 7-integration regression suite that Milestone 6A established continues to pass unmodified (re-verified this phase — see validation report).

---

# 6. Summary of Remaining Gaps vs. Reference Architecture

> **Updated 2026-07-29:** items 2 and 4 below were stale — both are now resolved (see the corrected component table in §1 and §4's own "no longer a deviation" note). Left below with strikethrough-equivalent annotations rather than deleted, so the history of what was closed and when stays visible.

1. `mcp-server` — not built (largest gap; Milestone 5+ scope per Execution-Framework.md §6).
2. ~~`gitlab-runner` — created but not registered/started.~~ **Resolved:** registered and online (`phase2-shared-runner`) since Milestone 1.
3. Prometheus scrape targets for `nautobot`/`platform-api` — configured but non-functional (no metrics endpoints exposed).
4. ~~Three named networks (`app-net`/`obs-net`/`proxy-net`) — not adopted.~~ **Resolved:** see §4 — implemented via the root `docker/docker-compose.yml`'s `include:`.
5. `docs` (MkDocs) — not built (still explicitly low priority in the reference architecture itself).
6. Traefik `/ping` healthcheck and `*.lab.local` `/etc/hosts` entries — not yet added.
