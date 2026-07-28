---
title: "Knowledge Base"
description: "The authoritative engineering knowledge base for the Network Platform Engineering Platform — architecture, ADRs, runbooks, and AI notes. Doubles as the Obsidian vault and the future semantic-retrieval corpus."
---

## Knowledge Base

This is the single, authoritative home for engineering documentation — moved here from `docs/` using `git mv` to preserve history. Open this folder directly in Obsidian; nothing about its structure is Obsidian-specific.

It exists for two audiences at once: engineers reading it directly, and a future semantic-retrieval pipeline (Vector DB + LangGraph) that will index it as-is, with no repository reorganization required when that day comes.

### Folders

| Folder | Contents |
|---|---|
| `architecture/` | Reference architecture, principles, glossary, technology/validation/security/observability design, current state and roadmap. `architecture/archive/` holds superseded Platform v1 material and the retired Contracts #1-#3 — preserved for history, not deleted. |
| `adr/` | Architecture Decision Records. Each is one atomic file. `adr/archive/` holds ADRs superseded by the Platform v2 replacement decision (ADR-016). |
| `runbooks/` | Operational procedures. Sparse today — grows as real runbooks are authored. |
| `ai/` | AI/agent-facing knowledge — the Knowledge Layer design and AI architecture. Agent instructions and guardrails will be added here as atomic notes when they're actually needed. |

`standards/` and `scratch/` are reserved names, not yet created — they'll exist the day a real standard or scratch note is written, not before.

### Rules

* **Every document stays atomic.** ADRs, architecture notes, and runbooks are never merged — this matters for both human navigation and future semantic retrieval, which performs better on small, focused documents than on large merged ones.
* **This vault never contains live infrastructure state.** No device inventory, tenant lists, IPAM exports, interfaces, or VLAN allocations. That data belongs exclusively to Nautobot, queried live. Anything here is knowledge *about* the platform, never a snapshot *of* it.
* **Frontmatter is mandatory** on every note (`type`, `domain`, `status`, `tags`, `owner`, `last_updated`) — this is what will let a future indexing pipeline filter and chunk without touching the folder structure again.

### Architectural boundaries this knowledge base respects

* **This vault (`knowledge/`)** = semantic knowledge only.
* **Nautobot** = live source of truth — devices, tenants, IPAM, interfaces, topology, queried live, never duplicated here.
* **GitLab** = execution engine.
* **HashiCorp Vault** = secrets — distinct from this Obsidian vault, despite the shared word.
* **LangGraph (future)** = the reasoning layer that will combine user intent, semantic retrieval from this vault, and structured retrieval from Nautobot. It will consume `knowledge/**/*.md` directly and query Nautobot live — no repository redesign required when it's built.
