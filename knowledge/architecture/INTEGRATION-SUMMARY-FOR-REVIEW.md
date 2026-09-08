## EXECUTIVE SUMMARY: Platform Communication Architecture

**Document Generated:** 2026-09-02  
**Based On:** ADR-001 through ADR-019, Execution Framework v2, Platform v2 Reference Architecture  
**Status:** Ready for User Review & Feedback

---

## VISUAL COMMUNICATION FLOWS

### The Complete 7-Layer Stack

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         AI/HUMAN ENTRY POINTS                            │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│   │ Copilot Agent│  │Claude Desktop│  │Nautobot/GitLab UI              │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                 │
│          │ MCP Protocol    │ MCP Protocol    │ REST API                 │
│          └────────────────┼────────────────┘                             │
│                           ▼                                              │
│                   ┌──────────────────┐                                   │
│                   │  MCP Server      │  ◄─── LAYER 1                    │
│                   │  (Thin Tools)    │       (JSON-RPC 2.0)            │
│                   └────────┬─────────┘                                   │
│                            │ REST API                                    │
│                            ▼                                              │
│                   ┌──────────────────────┐                               │
│                   │  NAUTOBOT (SoT)      │  ◄─── LAYER 2                │
│                   │ • Tenants/VRFs/BDs   │       (REST + Bearer Token)   │
│                   │ • Change Log         │                              │
│                   └────────┬─────────────┘                               │
│                            │ Webhook POST                                │
│                            ▼                                              │
│                   ┌──────────────────────┐                               │
│                   │  GITLAB CI           │  ◄─── LAYER 3                │
│                   │  (Orchestrator)      │       (Webhook + Query Param) │
│                   │  7-stage pipeline    │                              │
│                   └────────┬─────────────┘                               │
│                            │                                              │
│            ┌───────────────┼───────────────┐                             │
│            ▼               ▼               ▼                             │
│    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                   │
│    │ Generator    │ │OPA Policy    │ │Terraform     │  ◄─── LAYER 4    │
│    │              │ │Evaluation    │ │Planner       │       (Vault)    │
│    └──────────────┘ └──────────────┘ └──────────────┘                   │
│            │                               │                             │
│            │ Commits YAML [skip ci]        │ Approved?                   │
│            └───────────┬──────────────────┘                              │
│                        ▼                                                 │
│        ┌────────────────────────────────────┐                            │
│        │ Manual Approval Gate               │  ◄─── LAYER 5             │
│        │ (Protected Environment)            │       (Human Gate)         │
│        └────────────┬───────────────────────┘                            │
│                     ▼                                                    │
│        ┌────────────────────────────────────┐                            │
│        │ Terraform APPLY                    │  ◄─── LAYER 5 (cont.)     │
│        │ Modifies APIC Fabric               │       (Vault + REST API)  │
│        └────────────┬───────────────────────┘                            │
│                     ▼                                                    │
│        ┌────────────────────────────────────┐                            │
│        │ Ansible Day-2 Playbooks            │  ◄─── LAYER 5 (cont.)     │
│        │ Post-execution config              │       (SSH + Vault)       │
│        └────────────┬───────────────────────┘                            │
│                     ▼                                                    │
│        ┌────────────────────────────────────┐                            │
│        │ PyATS Independent Verification     │  ◄─── LAYER 6             │
│        │ Reads desired + actual state       │       (PATCH feedback)    │
│        └────────────┬───────────────────────┘                            │
│                     │ Writes custom_fields                               │
│                     ▼                                                    │
│        ┌────────────────────────────────────┐                            │
│        │ Knowledge Capture (MinIO)          │  ◄─── LAYER 7             │
│        │ JSONL append-only record           │       (S3 API SigV4)      │
│        └────────────────────────────────────┘                            │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  SECRETS MANAGEMENT (Vault) — All layers depend on this        │   │
│  │  • APIC credentials        • GitLab tokens                       │   │
│  │  • Device credentials      • MinIO credentials                  │   │
│  │  • API tokens              • TLS certificates                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## WHAT COMMUNICATES WITH WHAT — QUICK REFERENCE

| Source | Destination | Channel | Auth | Status |
|--------|-------------|---------|------|--------|
| **MCP Agent** | MCP Server | JSON-RPC HTTP | None (lab) | ✅ Ready |
| **MCP Server** | Nautobot | REST API | `NAUTOBOT_TOKEN` | ✅ Ready |
| **Nautobot** | GitLab | Webhook | `TRIGGER_TOKEN` | ❌ Config needed |
| **GitLab** | OPA | Docker IPC | None | ⚠️ OPA not in lab |
| **GitLab** | Vault | HTTPS REST | `VAULT_TOKEN` | ❌ Vault not deployed |
| **Terraform** | APIC | REST API | APIC creds (Vault) | ⚠️ Credentials missing |
| **Ansible** | Devices | SSH | Device creds (Vault) | ⚠️ Credentials missing |
| **PyATS** | APIC | REST API | APIC creds (Vault) | ⚠️ Credentials missing |
| **PyATS** | Nautobot | REST API PATCH | `PIPELINE_STATUS_TOKEN` | ❌ Token missing |
| **GitLab** | MinIO | S3 API | `MINIO_CREDS` | ⚠️ Placeholder only |

---

## COMPONENT RESPONSIBILITY MATRIX (WHAT EACH CAN/CANNOT DO)

### ✅ CAN DO

| Component | Responsibility | Notes |
|-----------|-----------------|-------|
| **Nautobot** | Own network inventory (Tenants, VRFs, BDs, etc.) | Single source of truth per ADR-001 |
| **Nautobot** | Record change history | Native Change Log captures all writes |
| **Nautobot** | Trigger external pipelines | Webhook on entity create/update |
| **Nautobot** | Store custom fields | Status fields for validation results, pipeline ID |
| **GitLab** | Orchestrate 7-stage execution | Policy → Approval → Execution → Verification → Capture |
| **GitLab** | Enforce approval gates | Protected environments native feature |
| **GitLab** | Serialize execution | `resource_group:` prevents race conditions |
| **GitLab** | Retrieve secrets at runtime | Vault integration via Terraform provider |
| **Terraform** | Apply idempotent infrastructure changes | Only reads YAML, never Nautobot directly |
| **Terraform** | Maintain state file | Stored as artifact, never version-controlled |
| **Ansible** | Execute Day-2 operations | Config, compliance, health checks (post-Terraform) |
| **Ansible** | Read Nautobot dynamically | Discovers inventory for agentless execution |
| **PyATS** | Independently verify deployment | Reads desired state (Nautobot) + actual state (APIC) |
| **PyATS** | Report verification results | Writes back to Nautobot custom fields |
| **OPA** | Evaluate Rego policies | Fail-closed on any error (no bypass) |
| **MCP Server** | Accept tool calls from AI | Thin per-tool schemas, no generic intent |
| **MCP Server** | Write Nautobot objects | Direct REST API calls (same as UI) |
| **MCP Server** | Report pipeline status | Query GitLab API, return to AI |
| **Vault** | Store all secrets encrypted | At-rest encryption, audit logging |

### ❌ CANNOT DO

| Component | Prohibited | Why |
|-----------|-----------|-----|
| **Nautobot** | Execute infrastructure changes | Source of Truth only (no orchestration) |
| **Nautobot** | Own non-network domains | Per ADR-019, narrowed to network inventory only |
| **Nautobot** | Store business intent (Why?) | Truth #1 deferred; today only Desired State (Truth #2) |
| **Nautobot** | Call MCP Server | One-way: MCP → Nautobot only |
| **GitLab** | Write infrastructure directly | Must use Terraform (single provisioning tool) |
| **GitLab** | Write Nautobot | Only pyATS feedback loop writes back |
| **GitLab** | Store secrets | Must use Vault (no .gitlab-ci.yml hardcoding) |
| **Terraform** | Read Nautobot directly | Reads only generated YAML from Git |
| **Terraform** | Run in parallel | Serialized by `resource_group:` per domain+env |
| **Terraform** | Bypass approval gate | Manual approval mandatory (ADR-014) |
| **Terraform** | Recreate ACI system tenants | common/infra/mgmt protected (hardcoded skip) |
| **Ansible** | Provision infrastructure | Day-2 only (post-Terraform) |
| **Ansible** | Modify desired state | Witness only; no intent writes |
| **Ansible** | Block infrastructure changes | Failures are informational (non-blocking) |
| **PyATS** | Fix infrastructure | Read-only verification (no auto-remediation) |
| **PyATS** | Block pipeline | Verification failures are informational (currently) |
| **OPA** | Be optional | Fail-closed if unreachable (never open access) |
| **OPA** | Store state | Stateless policy engine (no persistence) |
| **MCP Server** | Orchestrate multi-step workflows | Pass-through tools only (GitLab does orchestration) |
| **MCP Server** | Expose secrets to AI | Thin response only (status/confirmation) |
| **MCP Server** | Bypass GitLab execution | All changes flow through pipeline (no direct access) |
| **Vault** | Execute jobs | Storage only (no execution capability) |
| **Vault** | Survive container destruction | State persisted in Docker volume (manual backup needed) |

---

## FEEDBACK LOOPS (HOW STATUS RETURNS TO SOURCE OF TRUTH)

```
┌─────────────────────────────────────────────────────────────────┐
│  FEEDBACK LOOP #1: Verification Results → Nautobot (Immediate) │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PyATS verifies deployment:                                    │
│  ┌──────────────────┐                                           │
│  │ • Expected state │ ← Read from Nautobot                     │
│  │   (Nautobot)     │                                           │
│  │                  │                                           │
│  │ • Actual state   │ ← Queried from APIC                      │
│  │   (APIC/Device)  │                                           │
│  │                  │                                           │
│  │ • MATCH?         │ → YES: validation_status="passed"        │
│  │                  │ → NO: validation_status="failed"         │
│  └──────────────────┘                                           │
│         │                                                       │
│         │ PATCH                                                 │
│         ▼                                                       │
│  Nautobot Custom Fields Updated:                               │
│  • validation_status (passed/failed)                           │
│  • last_pipeline_id (12345)                                    │
│  • last_pipeline_url (GitLab link)                            │
│  • last_validated_at (timestamp)                               │
│                                                                 │
│  Nautobot Change Log records the update.                        │
│                                                                 │
│  AI agents can now query Nautobot for status.                   │
│  (Example: "show_status" MCP tool queries custom fields)       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FEEDBACK LOOP #2: All Events → MinIO Knowledge Store (Final)  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  GitLab pipeline completion triggers Knowledge Capture job:    │
│                                                                 │
│  Aggregates:                                                    │
│  ✓ Pipeline history (job logs, status, duration)              │
│  ✓ Nautobot changes (change log for this pipeline)             │
│  ✓ Verification results (pyATS report)                         │
│  ✓ Terraform changes (resource diff)                           │
│  ✓ Ansible execution results                                   │
│  ✓ Policy decision (OPA allow/deny)                            │
│  ✓ Approval info (who, when)                                   │
│                                                                 │
│  Writes to:                                                     │
│  s3://knowledge-capture/aci/deployments.jsonl (APPEND)        │
│  One JSON line per pipeline (immutable record)                 │
│                                                                 │
│  Persistence:                                                   │
│  • Durable (S3-compatible, replicated)                         │
│  • Queryable (standard JSONL format)                           │
│  • AI-accessible (future LangGraph retrieval)                  │
│  • Audit trail (every action recorded)                         │
│                                                                 │
│  Example Query:                                                 │
│  cat deployments.jsonl | jq '.[] | select(.tenant_name=="X")' │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FEEDBACK LOOP #3: Change Log → AI Reasoning (Future)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Future LangGraph reasoning layer (not built yet, per ADR-019) │
│  will:                                                          │
│                                                                 │
│  1. Query MinIO for past deployments (similar scenarios)       │
│  2. Read Nautobot Change Log (historical state transitions)    │
│  3. Analyze success/failure patterns                           │
│  4. Inform current decision-making                             │
│                                                                 │
│  This closes the loop: Execution → Knowledge → Reasoning       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## CREDENTIAL INVENTORY: WHAT'S MISSING

### ❌ MISSING (Must Create)

| Credential | Purpose | Scope | Type | Storage | Action |
|-----------|---------|-------|------|---------|--------|
| `VAULT_TOKEN` | Auth to Vault | Root (full) | UUID | GitLab CI var (masked) | Create after Vault init |
| `APIC_USERNAME` / `APIC_PASSWORD` | Terraform/Ansible/pyATS auth | Full ACI read/write | User/pass | Vault `secret/cisco_aci/apic` | Create from simulator defaults |
| `GIT_PUSH_TOKEN` | Commit generated YAML | `read_repo` + `write_repo` | GitLab PAT | Vault `secret/gitlab/git_push_token` | Create in GitLab Project Settings |
| `PIPELINE_STATUS_TOKEN` | Write back verification results | `read_api` | GitLab PAT | Vault `secret/gitlab/pipeline_status_token` | Create in GitLab Project Settings |
| `mcp-server-status-reader` | MCP Server queries pipeline | `read_api` | GitLab PAT | MCP Server env var | Create in GitLab Project Settings |
| `WEBHOOK_TRIGGER_TOKEN` | Nautobot → GitLab trigger | Specific trigger | GitLab trigger | Nautobot webhook config | Create in GitLab Project Settings |

### ⚠️ PLACEHOLDER (Needs Update)

| Credential | Current Value | Issue | Action |
|-----------|--------------|-------|--------|
| `MINIO_ROOT_USER` | `minioadmin` | Default, not secure | Change to lab-specific username |
| `MINIO_ROOT_PASSWORD` | (from incident recovery) | Doesn't match CI variables | Verify in GitLab and update MinIO |

### ✅ EXISTING (Ready)

| Credential | Value | Scope | Status |
|-----------|-------|-------|--------|
| `NAUTOBOT_TOKEN` | `0123456789abcdef...` | Full DCIM/IPAM API | ✅ Configured |

---

## RESTRICTIONS & CRITICAL CONSTRAINTS

### Design Principles (Enforced by Architecture)

1. **"AI Reasons, Platform Executes"** (ADR-010)
   - MCP Server = AI input device (no execution capability)
   - GitLab = Execution engine (no AI reasoning)
   - No direct feedback from execution to AI (async only)

2. **One Authoritative Intent Artifact** (ADR-018)
   - NetAsCode YAML = authoritative (Git-committed, deterministic)
   - NOT a shared Pydantic schema
   - Each domain has its own YAML format

3. **Nautobot is SoT for Network Only** (ADR-019 / ADR-001)
   - Network inventory + topology (Tenants, VRFs, Prefixes, Devices, Contracts)
   - NOT business intent (why changes exist)
   - NOT non-network domains (future Fortinet, Azure)

4. **Fail-Closed Security** (ADR-014)
   - If OPA unreachable → deny (never allow)
   - If policy engine fails → no persistence
   - If Vault down → jobs cannot retrieve secrets (fail immediately)

5. **Idempotency is Mandatory** (ADR-017/018)
   - Terraform: same input → same output (always safe to re-apply)
   - Ansible: playbooks must be idempotent (safe to re-run)
   - Serialization (GitLab `resource_group:`) ensures no race conditions

6. **No Hardcoded Secrets** (ADR-012)
   - All credentials come from Vault
   - CI variables can only reference Vault paths
   - Secrets never appear in logs (GitLab masking)

7. **Serialized Execution Per Domain** (ADR-017)
   - Only one `terraform_apply` per domain at a time (GitLab `resource_group:`)
   - Prevents race conditions, maintains state consistency
   - Critical for multi-tenant ACI where state ordering matters

### Critical Restrictions

| Restriction | Impact | Why |
|-----------|--------|-----|
| **No parallel Terraform runs per domain** | Slow for large deployments | Prevents state conflicts, race conditions |
| **No Terraform direct Nautobot reads** | Generator must run first | Forces deterministic YAML generation (provable) |
| **No Ansible provisioning (Day-2 only)** | Terraform must run first | Single provisioning tool (Terraform = SoT for creation) |
| **No direct AI → Infrastructure access** | AI must write Nautobot first | "Platform executes" principle (no AI execution bypass) |
| **No OPA bypass** | Fail-closed if policy denies | Governance mandatory, never optional |
| **No Nautobot SoT for non-network domains** | Must create domain-specific SoT | Per-domain models scale (proven by EVPN, ADR-021) |
| **No secret storage in Git** | All in Vault | Audit trail, rotation, revocation possible |
| **No Terraform state version-controlled** | Artifact-based only | State mutates (not human-readable), hard to review |
| **No pyATS auto-remediation** | Verification is informational (currently) | Read-only validation; humans make repair decisions |
| **No knowledge capture on pipeline failure** | Records still written (all stages) | All context captured even if job fails |

---

## INTEGRATION CHECKLIST (AWAITING YOUR APPROVAL)

### Phase 0: Architecture Review (CURRENT)
- [ ] User reviews this document
- [ ] User provides feedback on any corrections needed
- [ ] User confirms all 7 layers are accurate

### Phase 1: Vault Deployment (PENDING USER APPROVAL)
- [ ] Deploy Vault container (docker/vault/docker-compose.yml)
- [ ] Initialize Vault (generate root token, unseal)
- [ ] Create secret paths:
  - [ ] `secret/data/cisco_aci/apic` (username, password, url)
  - [ ] `secret/data/gitlab/git_push_token` (GIT_PUSH_TOKEN)
  - [ ] `secret/data/gitlab/pipeline_status_token` (PIPELINE_STATUS_TOKEN)
  - [ ] `secret/data/minio/root` (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD)
  - [ ] `secret/data/gitlab/mcp_status_reader` (mcp-server-status-reader)

### Phase 2: GitLab Credential Setup (PENDING USER APPROVAL)
- [ ] Create `GIT_PUSH_TOKEN` (Project Access Token)
- [ ] Create `PIPELINE_STATUS_TOKEN` (Project Access Token)
- [ ] Create `mcp-server-status-reader` (Project Access Token)
- [ ] Create `WEBHOOK_TRIGGER_TOKEN` (Pipeline Trigger)
- [ ] Store all tokens in Vault (Phase 1 paths)
- [ ] Store VAULT_TOKEN in GitLab CI variables (masked)

### Phase 3: Component Wiring (PENDING USER APPROVAL)
- [ ] Configure Nautobot webhook → GitLab trigger
- [ ] Configure MCP Server environment variables (VAULT_ADDR, NAUTOBOT_URL, etc.)
- [ ] Update `.gitlab-ci.yml` to retrieve secrets from Vault
- [ ] Verify Terraform can authenticate to APIC (plan stage)
- [ ] Verify Ansible can authenticate to devices (dynamic inventory)
- [ ] Verify pyATS can read Nautobot + query devices

### Phase 4: End-to-End Test (PENDING USER APPROVAL)
- [ ] MCP tool call: "create a test tenant"
- [ ] Confirm Nautobot write succeeds
- [ ] Confirm webhook triggers GitLab pipeline
- [ ] Confirm GitLab pipeline completes all 7 stages
- [ ] Confirm Terraform created APIC objects
- [ ] Confirm pyATS verified fabric state
- [ ] Confirm knowledge record written to MinIO
- [ ] Confirm Nautobot custom fields updated

---

## QUICK REFERENCE: WHO TALKS TO WHOM

```
AI Agent
   └──MCP Protocol──► MCP Server
                         │
                    REST API
                         │
                      Nautobot (SoT)
                         │
                      Webhook
                         │
                    GitLab CI (Orchestrator)
                         │
     ┌───────────────────┼───────────────────┐
     │                   │                   │
  OPA Policy        Vault (Secrets)    Terraform
  (Validate)        (Credentials)      (Provision)
     │                   │                   │
     └───────────────────┼───────────────────┘
                         │
                    [APIC/Devices]
                         │
                  Ansible + PyATS
                         │
                    [Verify fabric]
                         │
                  Write back to Nautobot
                         │
                  Knowledge Capture (MinIO)
                         │
                   [Audit Trail JSONL]
```

---

## 🚦 NEXT STEP: YOUR FEEDBACK

**Please review and confirm:**

1. ✅ **Does the 7-layer architecture match your understanding?**
2. ✅ **Are all communication flows and protocols correctly documented?**
3. ✅ **Do the component responsibilities make sense?**
4. ✅ **Is the credential inventory complete?**
5. ✅ **Should I proceed with Vault deployment + credential setup?**

**Once approved, I will:**
- Deploy Vault and initialize with all missing credentials
- Wire components in dependency order with verification
- Execute end-to-end test (MCP → Nautobot → Pipeline → Fabric → MinIO)
- Provide operational runbook for troubleshooting

**Ready to proceed? Please provide your feedback.** ✋
