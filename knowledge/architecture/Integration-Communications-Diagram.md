# Network Platform Engineering — Complete Communications & Integration Architecture

**Document Status:** Architecture Review & Integration Plan (Ready for User Feedback)  
**Created:** 2026-09-02  
**Scope:** Nautobot ↔ GitLab ↔ Terraform ↔ Ansible ↔ PyATS ↔ ACI (all data flows, restrictions, feedback loops)

---

## PART 1: VISUAL COMMUNICATION ARCHITECTURE

### High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL ENTRY POINTS (AI/HUMAN)                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │  VS Code Copilot │  │ Claude Desktop   │  │ Nautobot Web UI  │              │
│  │  Agent (MCP)     │  │ (MCP client)     │  │ / GitLab UI      │              │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘              │
│           │                     │                      │                         │
│           └─────────────────────┼──────────────────────┘                         │
│                                 │                                                │
│                    MCP Protocol  │  REST API                                    │
│                   (JSON-RPC 2.0) │                                              │
└─────────────────────────────────┼──────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
           ┌─────────────────────┐      ┌─────────────────────┐
           │    MCP Server       │      │     NAUTOBOT        │
           │   (Tool Provider)   │      │  (Source of Truth)  │
           │                     │      │                     │
           │  • create_tenant    │      │  • Tenants          │
           │  • create_vrf       │◄────►│  • VRFs             │
           │  • create_bd        │ REST │  • Bridge Domains   │
           │  • create_epg       │ API  │  • Endpoints        │
           │  • create_contract  │      │  • Contracts        │
           │  • create_l3out     │      │  • Custom Fields    │
           │  • show_status      │      │  • Change Log       │
           │                     │      │  • Event Webhooks   │
           └─────────────────────┘      └──────────┬──────────┘
                                                   │
                                    Nautobot writes trigger
                                    Webhook to GitLab Pipeline
                                                   │
                                                   ▼
                                        ┌─────────────────────┐
                                        │  GitLab Pipeline    │
                                        │  Orchestrator       │
                                        │                     │
                                        │  • Webhook listener │
                                        │  • Job graph        │
                                        │  • Resource locking │
                                        │  • Artifacts        │
                                        │  • Logs/Status      │
                                        └──────────┬──────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    │                              │                              │
                    ▼                              ▼                              ▼
          ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
          │  Generator       │        │   OPA Policy     │        │  Terraform       │
          │ (generate_aci.py)│        │   (Validation)   │        │  Planner         │
          │                  │        │                  │        │                  │
          │ Reads: Nautobot  │        │ Evaluates: YAML  │        │ Reads: YAML      │
          │ Outputs: YAML    │        │ Returns: allow/  │        │ Connects to APIC │
          │ (deterministic)  │        │ deny + reasons   │        │ Shows changes    │
          │                  │        │                  │        │                  │
          └────────┬─────────┘        └────────┬─────────┘        └────────┬─────────┘
                   │                            │                          │
                   │ Commits YAML to Git        │ Fail-closed             │
                   │ [skip ci]                  │ Blocks pipeline if deny │
                   │                            │                         │
                   └────────────────┬───────────┴─────────────────────────┘
                                    │
                                    │ (All stages serialize via GitLab resource_group)
                                    ▼
                        ┌──────────────────────────┐
                        │ MANUAL APPROVAL GATE     │
                        │ (Protected Environment)  │
                        │ Requires GitLab UI click │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Terraform APPLY          │
                        │ (Execution)              │
                        │                          │
                        │ Reads: YAML              │
                        │ Retrieves: APIC creds    │
                        │ Modifies: Live fabric    │
                        │ Persists: state file     │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Ansible Day-2            │
                        │ (Post-Execution)         │
                        │                          │
                        │ Reads: Nautobot inventory│
                        │ Retrieves: device creds  │
                        │ Configures: devices     │
                        │ Reports: success/failure │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ PyATS Verification       │
                        │ (Independent Validation) │
                        │                          │
                        │ Reads: Desired state     │
                        │         (Nautobot)       │
                        │ Reads: Actual state      │
                        │         (APIC devices)   │
                        │ Compares & tests         │
                        │ Writes: results back to  │
                        │         Nautobot fields  │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Knowledge Capture        │
                        │ (Final Stage)            │
                        │                          │
                        │ Aggregates:              │
                        │  • Pipeline history      │
                        │  • Nautobot changes      │
                        │  • Verification results  │
                        │ Writes: JSONL to MinIO   │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Feedback Loop            │
                        │                          │
                        │ Status updates flow:     │
                        │ Verification ──→ Custom  │
                        │                 Fields   │
                        │ Pipeline logs ──→ MinIO  │
                        │ Change history → GitLab  │
                        │ All queryable by AI      │
                        └──────────────────────────┘
```

---

### Detailed Protocol & Authentication Matrix

#### **Layer 1: External Clients → MCP Server**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: AI Agent (VS Code Copilot, Claude Desktop)             │
│ SERVER: MCP Server (localhost:8071)                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Protocol:        HTTP/WebSocket (JSON-RPC 2.0 over HTTP)     │
│  Endpoint:        http://localhost:8071/mcp (streamable-http) │
│  Authentication:  None (lab); MCP_API_KEY header (production) │
│  TLS:             No (lab); Required (production)             │
│  Latency:         Sub-second                                  │
│  Payload:         JSON tool call + arguments                  │
│                                                                │
│  Tool Call Schema (EXAMPLE):                                  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ POST http://localhost:8071/mcp                           │ │
│  │ {                                                        │ │
│  │   "method": "tools/call",                               │ │
│  │   "jsonrpc": "2.0",                                      │ │
│  │   "id": "uuid-1",                                        │ │
│  │   "params": {                                            │ │
│  │     "name": "create_tenant",                             │ │
│  │     "arguments": {                                       │ │
│  │       "name": "mytenant",                                │ │
│  │       "description": "Demo tenant from AI"               │ │
│  │     }                                                    │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Success Response:                                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ {                                                        │ │
│  │   "jsonrpc": "2.0",                                      │ │
│  │   "id": "uuid-1",                                        │ │
│  │   "result": {                                            │ │
│  │     "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", │ │
│  │     "status": "pending_pipeline_execution",              │ │
│  │     "pipeline_id": "12345",                              │ │
│  │     "nautobot_url": "http://localhost:8081/api/dcim/...  │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Restrictions:                                                 │
│  ✓ Tool arguments are validated per tool's Pydantic schema   │
│  ✓ No generic "intent" payload — each tool owns its schema   │
│  ✓ Tool return payload intentionally thin (status only)      │
│  ✓ AI gets confirmation of successful Nautobot write only    │
│  ✗ AI never receives execution-stage details or secrets      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 2: MCP Server → Nautobot**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: MCP Server                                             │
│ SERVER: Nautobot REST API (localhost:8081/api/)               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Protocol:        HTTPS REST (HTTP in lab, HTTPS production)  │
│  Endpoint:        http://localhost:8081/api/dcim/tenants/     │
│  Authentication:  Bearer Token (NAUTOBOT_TOKEN header)        │
│  Method:          POST (create), PATCH (update), GET (read)   │
│  Content-Type:    application/json                            │
│  Latency:         100-500ms (depends on Nautobot load)        │
│  Payload:         JSON (Tenant, VRF, Prefix, etc. objects)    │
│                                                                │
│  Example: create_tenant                                        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ POST http://localhost:8081/api/dcim/tenants/             │ │
│  │ Authorization: Bearer 0123456789abcdef0123456789abcde... │ │
│  │ Content-Type: application/json                           │ │
│  │                                                          │ │
│  │ {                                                        │ │
│  │   "name": "mytenant",                                    │ │
│  │   "description": "Demo tenant from AI",                  │ │
│  │   "comments": "Created via MCP Server"                   │ │
│  │ }                                                        │ │
│  │                                                          │ │
│  │ Response (201 Created):                                  │ │
│  │ {                                                        │ │
│  │   "id": "12345678-1234-5678-1234-567812345678",         │ │
│  │   "url": "http://localhost:8081/api/dcim/tenants/12345/ │ │
│  │   "display": "mytenant",                                 │ │
│  │   "name": "mytenant",                                    │ │
│  │   "custom_fields": {                                     │ │
│  │     "aci_tenant_name": "mytenant"                        │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Restrictions:                                                 │
│  ✓ MCP Server is ONLY writer (no read-back validation)       │
│  ✓ Assumes Nautobot exists and is reachable                  │
│  ✗ MCP Server NEVER queries Nautobot (only writes)           │
│  ✗ MCP Server does NOT trigger pipeline directly (webhook    │
│    response trigger does that)                                │
│  ✓ Write must complete before returning to client             │
│  ✓ Failures are propagated (400/422 → MCP returns error)     │
│                                                                │
│  Credentials:                                                  │
│  • NAUTOBOT_TOKEN: UUID format, 36 chars, read+write scope   │
│  • Storage: MCP Server env var (NAUTOBOT_TOKEN)              │
│  • Rotation: Manual; no expiry tracking                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 3: Nautobot → GitLab Pipeline Trigger (Webhook)**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: Nautobot (webhook sender)                              │
│ SERVER: GitLab Pipeline Trigger API                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Trigger Type:    HTTP POST webhook (Nautobot Webhook plugin) │
│  Event:           Entity create/update (Tenant, VRF, etc.)    │
│  Endpoint:        http://localhost:8929/api/v4/projects/      │
│                   1/trigger/pipeline                          │
│  Authentication:  token=<TRIGGER_TOKEN> (query param)         │
│  Content-Type:    application/json                            │
│  Latency:         1-5s (network + GitLab processing)          │
│  Retry:           Configurable (default 3 attempts)           │
│                                                                │
│  Example Webhook Payload (from Nautobot):                      │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ POST http://localhost:8929/api/v4/projects/1/            │ │
│  │       trigger/pipeline?token=<TRIGGER_TOKEN>             │ │
│  │                                                          │ │
│  │ {                                                        │ │
│  │   "ref": "main",                                         │ │
│  │   "variables": {                                         │ │
│  │     "TRIGGER_SOURCE": "nautobot_webhook",               │ │
│  │     "EVENT_TYPE": "tenant_created",                      │ │
│  │     "ENTITY_ID": "12345678-1234-5678-1234-567812345678", │ │
│  │     "ENTITY_NAME": "mytenant"                            │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  │                                                          │ │
│  │ GitLab Response (201 Created):                           │ │
│  │ {                                                        │ │
│  │   "id": 12345,                                           │ │
│  │   "iid": 1,                                              │ │
│  │   "ref": "main",                                         │ │
│  │   "sha": "abcd1234efgh5678ijkl9012mnop3456qrst5678",    │ │
│  │   "status": "pending",                                   │ │
│  │   "created_at": "2026-09-02T12:34:56Z"                   │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Restrictions:                                                 │
│  ✓ Only works on protected branches (main) or configured     │
│    branch in webhook settings                                │
│  ✓ Trigger token is immutable once created (can revoke only) │
│  ✗ Webhook sender has no auth context (token identifies      │
│    pipeline, not the sender)                                 │
│  ✓ GitLab receives webhook, starts pipeline, returns         │
│    immediately (async execution)                             │
│  ✓ Webhook can pass variables into pipeline (CI variables)   │
│                                                                │
│  Credentials:                                                  │
│  • TRIGGER_TOKEN: Unique per project, per trigger URL        │
│  • Storage: Nautobot webhook config (Webhook object)         │
│  • Rotation: Regenerate in GitLab project settings           │
│                                                                │
│  Flow diagram:                                                 │
│  Nautobot UI ──→ Tenant created ──→ Webhook fires            │
│       ↓                                    │                  │
│  Change Log                         HTTP POST to GitLab       │
│  recorded                                  │                  │
│       ↑                                    ▼                  │
│       └────────── GitLab CI starts ────────┘                 │
│                   (async, independent)                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 4: GitLab CI → Vault (Secrets Retrieval)**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: GitLab CI Job (Terraform, Ansible, pyATS, etc.)       │
│ SERVER: HashiCorp Vault                                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Protocol:        HTTPS REST (HTTP in lab, HTTPS production) │
│  Endpoint:        http://localhost:8200/v1/secret/data/...   │
│  Authentication:  X-Vault-Token header (VAULT_TOKEN)         │
│  Method:          GET (retrieve secret)                       │
│  Content-Type:    application/json                            │
│  Latency:         100-300ms                                   │
│                                                                │
│  Example: Terraform retrieving APIC credentials               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ GET http://localhost:8200/v1/secret/data/               │ │
│  │     cisco_aci/apic                                       │ │
│  │ X-Vault-Token: s.xxxxxxxxxxxxxxxxxxxxxxxx                │ │
│  │                                                          │ │
│  │ Response (200 OK):                                       │ │
│  │ {                                                        │ │
│  │   "request_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", │ │
│  │   "lease_id": "",                                        │ │
│  │   "renewable": false,                                    │ │
│  │   "lease_duration": 0,                                   │ │
│  │   "data": {                                              │ │
│  │     "data": {                                            │ │
│  │       "username": "admin",                               │ │
│  │       "password": "xxxxxxx",                             │ │
│  │       "url": "https://172.30.46.103"                     │ │
│  │     },                                                   │ │
│  │     "metadata": {                                        │ │
│  │       "created_time": "2026-01-15T12:34:56Z",           │ │
│  │       "deletion_time": "",                               │ │
│  │       "destroyed": false,                                │ │
│  │       "version": 3                                       │ │
│  │     }                                                    │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  CI Job Integration (Terraform provider plugin):               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ In .gitlab-ci.yml:                                       │ │
│  │                                                          │ │
│  │ terraform_apply:                                         │ │
│  │   stage: execution                                       │ │
│  │   variables:                                             │ │
│  │     VAULT_ADDR: "http://localhost:8200"                  │ │
│  │     VAULT_TOKEN: "${VAULT_TOKEN}"  # GitLab CI var      │ │
│  │   script:                                                │ │
│  │     - cd platform/terraform/aci                          │ │
│  │     - terraform init                                     │ │
│  │     - terraform apply -auto-approve                      │ │
│  │                                                          │ │
│  │ In terraform/aci/main.tf:                                │ │
│  │                                                          │ │
│  │ provider "vault" {                                       │ │
│  │   address = var.vault_addr                              │ │
│  │ }                                                        │ │
│  │                                                          │ │
│  │ data "vault_generic_secret" "aci_creds" {               │ │
│  │   path = "secret/data/cisco_aci/apic"                   │ │
│  │ }                                                        │ │
│  │                                                          │ │
│  │ locals {                                                 │ │
│  │   aci_username = data.vault_generic_secret.aci_creds.   │ │
│  │                 data.username                           │ │
│  │   aci_password = data.vault_generic_secret.aci_creds.   │ │
│  │                 data.password                           │ │
│  │   aci_url = data.vault_generic_secret.aci_creds.        │ │
│  │             data.url                                    │ │
│  │ }                                                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Restrictions:                                                 │
│  ✓ CI job must have VAULT_TOKEN in variables                 │
│  ✓ Token is only for read (GET) operations (CI should be    │
│    read-only for secrets)                                    │
│  ✗ Token NEVER appears in logs (GitLab masks masked vars)   │
│  ✓ Each secret path is independent (no wildcard retrieval)  │
│  ✓ Vault rejects requests without valid token               │
│                                                                │
│  Credentials:                                                  │
│  • VAULT_TOKEN: Vault authentication token (UUID format)     │
│  • Storage: GitLab CI masked variable (gitlab-admin only)    │
│  • Rotation: Manual; could be auto-rotated via Vault lease  │
│             policies (not configured in lab)                 │
│                                                                │
│  Secret Paths (standard naming convention):                    │
│  • secret/data/cisco_aci/apic → username, password, url      │
│  • secret/data/cisco_nexus/device_x → IP, username, password │
│  • secret/data/gitlab/git_push_token → token value           │
│  • secret/data/minio/root → access_key, secret_key           │
│  • secret/data/nautobot/api_token → token value              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 5: GitLab CI → Infrastructure Devices (Terraform/Ansible)**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: GitLab CI Job (terraform_apply / ansible_configure)   │
│ SERVER: Cisco ACI APIC / Cisco Nexus Devices                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─ Terraform Path ────────────────────────────────────────┐  │
│  │ Protocol:        HTTPS REST                             │  │
│  │ Endpoint:        https://172.30.46.103/api/aci/...      │  │
│  │ Authentication:  X-IID-COOKIE session (username/password)│  │
│  │ Method:          POST (create), PATCH (update), DELETE  │  │
│  │ Content-Type:    application/json                       │  │
│  │ TLS Verify:      NO in lab (self-signed), YES production│  │
│  │ Latency:         500ms - 2s per object                  │  │
│  │ Concurrency:     Serialized via GitLab resource_group   │  │
│  │                  (only 1 job per domain at a time)      │  │
│  │                                                         │  │
│  │ Example: Terraform creates ACI Tenant                   │  │
│  │ ┌───────────────────────────────────────────────────┐  │  │
│  │ │ POST https://172.30.46.103/api/aci/tenants        │  │  │
│  │ │ Content-Type: application/json                    │  │  │
│  │ │ Cookie: APIC session cookie                       │  │  │
│  │ │                                                   │  │  │
│  │ │ {                                                 │  │  │
│  │ │   "fvTenant": {                                   │  │  │
│  │ │     "attributes": {                               │  │  │
│  │ │       "name": "mytenant",                         │  │  │
│  │ │       "descr": "Demo tenant from Terraform"       │  │  │
│  │ │     }                                             │  │  │
│  │ │   }                                               │  │  │
│  │ │ }                                                 │  │  │
│  │ │                                                   │  │  │
│  │ │ Response (201 Created):                           │  │  │
│  │ │ {                                                 │  │  │
│  │ │   "imdata": [{                                    │  │  │
│  │ │     "fvTenant": {                                 │  │  │
│  │ │       "attributes": {                             │  │  │
│  │ │         "dn": "uni/tn-mytenant",                  │  │  │
│  │ │         "name": "mytenant",                       │  │  │
│  │ │         "status": "created"                       │  │  │
│  │ │       }                                           │  │  │
│  │ │     }                                             │  │  │
│  │ │   }]                                              │  │  │
│  │ │ }                                                 │  │  │
│  │ └───────────────────────────────────────────────────┘  │  │
│  │                                                         │  │
│  │ State Management:                                       │  │
│  │ • terraform apply reads local state (from previous run) │  │
│  │ • Plans changes (terraform plan stage)                  │  │
│  │ • Applies only changes needed (idempotent)              │  │
│  │ • Updates local state file (artifact)                   │  │
│  │ • State is NOT version-controlled (artifact only)       │  │
│  │                                                         │  │
│  │ Restrictions:                                            │  │
│  │ ✓ Terraform is the ONLY writer to ACI (no manual APIC) │  │
│  │   changes once Terraform adopted                       │  │
│  │ ✓ One domain/env at a time (resource_group: aci)      │  │
│  │ ✗ Terraform never reads Nautobot (only reads YAML)    │  │
│  │ ✓ Idempotency guaranteed (same input = same output)   │  │
│  │ ✓ Rollback via terraform destroy (manual gate needed)  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ Ansible Path ──────────────────────────────────────────┐  │
│  │ Protocol:        SSH (for network devices)              │  │
│  │ Endpoint:        Device hostname/IP + port 22           │  │
│  │ Authentication:  SSH key-pair or username/password      │  │
│  │ Method:          Agentless (Ansible SSH -> Python exec) │  │
│  │ Latency:         1-5s per device                        │  │
│  │ Concurrency:     Parallel by default (forks: 10)        │  │
│  │                                                          │  │
│  │ Playbook Example (platform/ansible/aci/verify-tenants) │  │
│  │ ┌───────────────────────────────────────────────────┐  │  │
│  │ │ ---                                               │  │  │
│  │ │ - name: Verify APIC Tenants via API               │  │  │
│  │ │   hosts: apic                                     │  │  │
│  │ │   gather_facts: no                                │  │  │
│  │ │   connection: local                               │  │  │
│  │ │   vars:                                           │  │  │
│  │ │     aci_host: "{{ aci_host }}"                    │  │  │
│  │ │     aci_username: "{{ aci_username }}"            │  │  │
│  │ │     aci_password: "{{ aci_password }}"            │  │  │
│  │ │     aci_validate_certs: no                        │  │  │
│  │ │   tasks:                                          │  │  │
│  │ │     - name: Query existing tenants                │  │  │
│  │ │       aci_tenant:                                 │  │  │
│  │ │         host: "{{ aci_host }}"                    │  │  │
│  │ │         username: "{{ aci_username }}"            │  │  │
│  │ │         password: "{{ aci_password }}"            │  │  │
│  │ │         validate_certs: "{{ aci_validate_certs }}"│  │  │
│  │ │         state: query                              │  │  │
│  │ │       register: existing_tenants                  │  │  │
│  │ │                                                   │  │  │
│  │ │     - name: Report existing tenants               │  │  │
│  │ │       debug:                                      │  │  │
│  │ │         msg: "Found tenants: {{ existing_tenants  │  │  │
│  │ │                               | json_query(...) }}"│  │  │
│  │ └───────────────────────────────────────────────────┘  │  │
│  │                                                          │  │
│  │ Inventory Source (Nautobot dynamic plugin):              │  │
│  │ ┌───────────────────────────────────────────────────┐  │  │
│  │ │ # inventory/nautobot.yml                          │  │  │
│  │ │ plugin: nautobot.dcim.inventory                   │  │  │
│  │ │ api_endpoint: http://localhost:8081               │  │  │
│  │ │ token: "{{ nautobot_token }}"                     │  │  │
│  │ │ query: |                                          │  │  │
│  │ │   query Device($filter: DeviceFilter)             │  │  │
│  │ │   devices(filter: $filter) {                      │  │  │
│  │ │     name                                          │  │  │
│  │ │     primary_ip4                                   │  │  │
│  │ │   }                                               │  │  │
│  │ │ strict: false                                     │  │  │
│  │ └───────────────────────────────────────────────────┘  │  │
│  │                                                          │  │
│  │ Restrictions:                                            │  │
│  │ ✓ Day-2 only (NO initial provisioning via Ansible)     │  │
│  │ ✓ Reads Nautobot inventory (dynamic)                   │  │
│  │ ✓ Idempotent playbooks (safe to re-run)                │  │
│  │ ✗ Does NOT modify desired state (witness only)         │  │
│  │ ✓ Failures are non-blocking (info only)                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  Credentials (both paths):                                     │
│  • ACI Credentials: Retrieved from Vault during job runtime  │
│  • Device SSH Keys: Retrieved from Vault (if SSH auth used)  │
│  • Credentials NEVER hardcoded in Terraform/Ansible code    │
│                                                                │
│  Serialization (Critical Restriction):                         │
│  • GitLab resource_group: aci ensures only 1 terraform_apply  │
│    runs at a time per domain (prevents race conditions)       │
│  • Same for ansible_configure (waits for terraform_apply)    │
│  • Critical for idempotency and state consistency            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 6: PyATS Verification → Nautobot Feedback Loop**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: GitLab CI Job (pyats_verify stage)                    │
│ SERVER #1: Live Infrastructure (APIC, Devices)               │
│ SERVER #2: Nautobot (write-back feedback loop)                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─ Validation Query Phase ────────────────────────────────┐  │
│  │                                                         │  │
│  │ pyATS reads desired state from Nautobot:                │  │
│  │ ┌────────────────────────────────────────────────────┐ │  │
│  │ │ GET http://localhost:8081/api/dcim/                │ │  │
│  │ │     tenants/?name=mytenant                         │ │  │
│  │ │ Authorization: Bearer NAUTOBOT_TOKEN                │ │  │
│  │ │                                                    │ │  │
│  │ │ Response: {"count": 1, "results": [{"name": ...}]}│ │  │
│  │ └────────────────────────────────────────────────────┘ │  │
│  │                                                         │  │
│  │ pyATS reads actual state from APIC:                    │  │
│  │ ┌────────────────────────────────────────────────────┐ │  │
│  │ │ GET https://172.30.46.103/api/class/                │ │  │
│  │ │     fvTenant.json?query-target-filter=               │ │  │
│  │ │     wcard(fvTenant/name,"mytenant")                 │ │  │
│  │ │ Cookie: APIC session                                │ │  │
│  │ │                                                    │ │  │
│  │ │ Response: {"imdata": [{"fvTenant": {"attributes": │ │  │
│  │ │                     {"name": "mytenant", ...}}}]} │ │  │
│  │ └────────────────────────────────────────────────────┘ │  │
│  │                                                         │  │
│  │ Test Logic:                                             │  │
│  │ 1. For each Nautobot tenant → is it in APIC?          │  │
│  │ 2. For each APIC tenant → is it expected (in Nautobot)│  │
│  │ 3. For tenants that exist → compare attribute values  │  │
│  │ 4. Generate test report (pass/fail/warn)              │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ Write-Back Feedback Phase ─────────────────────────────┐  │
│  │                                                         │  │
│  │ After pyATS completes, write_results.py updates         │  │
│  │ Nautobot custom fields:                                 │  │
│  │                                                         │  │
│  │ PATCH http://localhost:8081/api/dcim/tenants/          │  │
│  │      12345/                                             │  │
│  │ Authorization: Bearer PIPELINE_STATUS_TOKEN             │  │
│  │ Content-Type: application/json                          │  │
│  │                                                         │  │
│  │ {                                                       │  │
│  │   "custom_fields": {                                    │  │
│  │     "validation_status": "passed",                      │  │
│  │     "last_pipeline_id": "12345",                        │  │
│  │     "last_pipeline_url": "http://localhost:8929/...    │  │
│  │                          root/nautobot-infra.../pipelines│  │
│  │                          /12345",                       │  │
│  │     "last_validated_at": "2026-09-02T13:45:00Z"        │  │
│  │   }                                                     │  │
│  │ }                                                       │  │
│  │                                                         │  │
│  │ Response (200 OK):                                      │  │
│  │ {                                                       │  │
│  │   "id": "12345678-1234-5678-1234-567812345678",        │  │
│  │   "url": "http://localhost:8081/api/dcim/tenants/...  │  │
│  │   "custom_fields": {                                    │  │
│  │     "validation_status": "passed",                      │  │
│  │     "last_pipeline_id": "12345",                        │  │
│  │     ...                                                 │  │
│  │   }                                                     │  │
│  │ }                                                       │  │
│  │                                                         │  │
│  │ Key Points:                                              │  │
│  │ • PIPELINE_STATUS_TOKEN is read_api scope only          │  │
│  │ • Different token from GIT_PUSH_TOKEN (least privilege)│  │
│  │ • Writes back WITHIN the GitLab CI job context          │  │
│  │ • Closes the feedback loop: Verify → Custom Fields      │  │
│  │ • AI agents can query these custom fields for status    │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ Restrictions & Constraints ────────────────────────────┐  │
│  │ ✓ pyATS is independent of Terraform success marker     │  │
│  │   (queries live devices, not state files)              │  │
│  │ ✓ If Terraform succeeds but fabric is down → pyATS will  │  │
│  │   fail and report validation_status: "failed"          │  │
│  │ ✓ Nautobot change log records the field update         │  │
│  │ ✗ pyATS NEVER changes desired state (read-only)        │  │
│  │ ✓ Validation failures do NOT block next pipeline       │  │
│  │   (currently info-only; could add gate if desired)     │  │
│  │ ✓ If pyATS job fails → Knowledge Capture still runs    │  │
│  │   (all artifacts captured, status recorded)            │  │
│  │                                                         │  │
│  │ Credentials:                                             │  │
│  │ • NAUTOBOT_TOKEN: Read desired state                    │  │
│  │ • PIPELINE_STATUS_TOKEN: Write results back            │  │
│  │ • Device credentials: Query live APIC/devices           │  │
│  │   (all from Vault)                                      │  │
│  │                                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### **Layer 7: Knowledge Capture → MinIO (Final Persistence)**

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT: GitLab CI Job (knowledge_capture stage)               │
│ SERVER: MinIO S3-compatible Object Storage                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Protocol:        HTTPS (HTTP in lab, HTTPS production)       │
│  Endpoint:        http://localhost:9000 (API), :9001 (UI)     │
│  Authentication:  AWS SigV4 (MINIO_ROOT_USER + PASSWORD)      │
│  Method:          PUT (append JSONL to object)                │
│  Content-Type:    application/x-ndjson (JSONL)                │
│  Latency:         200-500ms per record                        │
│  Bucket:          knowledge-capture                           │
│  Object:          aci/deployments.jsonl (append-only)         │
│                                                                │
│  Example: Append one deployment record                         │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ PUT http://localhost:9000/knowledge-capture/aci/         │ │
│  │     deployments.jsonl                                    │ │
│  │ (AWS SigV4 auth header with MINIO_ROOT_USER/PASSWORD)    │ │
│  │                                                          │ │
│  │ Payload (JSONL - one JSON object per line, newline sep): │ │
│  │ {                                                        │ │
│  │   "pipeline_id": "12345",                                │ │
│  │   "pipeline_url": "http://localhost:8929/.../12345",     │ │
│  │   "timestamp": "2026-09-02T13:45:00Z",                   │ │
│  │   "trigger_source": "nautobot_webhook",                  │ │
│  │   "trigger_entity": {                                    │ │
│  │     "type": "tenant",                                    │ │
│  │     "id": "12345678-1234-5678-1234-567812345678",       │ │
│  │     "name": "mytenant"                                   │ │
│  │   },                                                     │ │
│  │   "git_commit": "abcd1234efgh5678ijkl9012mnop3456",      │ │
│  │   "generated_yaml_filename": "platform/netascode/aci/    │ │
│  │                               tenants.yaml",            │ │
│  │   "policy_decision": "allow",                            │ │
│  │   "approval_required": true,                             │ │
│  │   "approved_by": "admin",                                │ │
│  │   "approval_time": "2026-09-02T13:50:00Z",              │ │
│  │   "execution_status": "apply_successful",                │ │
│  │   "terraform_changes": {                                 │ │
│  │     "resources_created": ["aci_tenant.mytenant"],        │ │
│  │     "resources_modified": [],                            │ │
│  │     "resources_destroyed": []                            │ │
│  │   },                                                     │ │
│  │   "ansible_tasks": {                                     │ │
│  │     "total": 5,                                          │ │
│  │     "ok": 5,                                             │ │
│  │     "failed": 0,                                         │ │
│  │     "skipped": 0                                         │ │
│  │   },                                                     │ │
│  │   "validation_results": {                                │ │
│  │     "status": "passed",                                  │ │
│  │     "tests_run": 12,                                     │ │
│  │     "tests_passed": 12,                                  │ │
│  │     "tests_failed": 0                                    │ │
│  │   },                                                     │ │
│  │   "nautobot_updates": {                                  │ │
│  │     "custom_fields": {                                   │ │
│  │       "validation_status": "passed",                     │ │
│  │       "last_pipeline_id": "12345",                       │ │
│  │       "last_validated_at": "2026-09-02T14:00:00Z"        │ │
│  │     }                                                    │ │
│  │   },                                                     │ │
│  │   "pipeline_duration_seconds": 450,                      │ │
│  │   "observability_metrics": {                             │ │
│  │     "terraform_duration": 180,                           │ │
│  │     "ansible_duration": 120,                             │ │
│  │     "validation_duration": 150                           │ │
│  │   }                                                      │ │
│  │ }                                                        │ │
│  │ (newline) ← Each line is independent JSON              │ │
│  │                                                          │ │
│  │ Response (200 OK):                                       │ │
│  │ (MinIO returns empty body on successful append)          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Access Pattern (by AI or human later):                        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ # Download entire deployments.jsonl from MinIO           │ │
│  │ aws s3 cp s3://knowledge-capture/aci/deployments.jsonl   │ │
│  │          . --endpoint-url http://localhost:9000          │ │
│  │                                                          │ │
│  │ # Parse JSONL and query:                                 │ │
│  │ cat deployments.jsonl | jq 'select(.pipeline_id==       │ │
│  │                               "12345")'                  │ │
│  │                                                          │ │
│  │ # LangGraph can use this knowledge retrieval:            │ │
│  │ # (future feature, Milestone 22+)                        │ │
│  │ past_deployments = query_knowledge_base(                 │ │
│  │     query="all deployments of mytenant",                 │ │
│  │     s3_bucket="knowledge-capture",                       │ │
│  │     s3_key="aci/deployments.jsonl",                      │ │
│  │     filter_fn=lambda x: x["trigger_entity"]["name"]      │ │
│  │                        == "mytenant"                      │ │
│  │ )                                                        │ │
│  │                                                          │ │
│  │ # Use past_deployments to inform current decision        │ │
│  │ reasoning                                                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Restrictions:                                                 │
│  ✓ JSONL is append-only (no overwrites of existing records)  │ │
│  ✓ Immutable audit trail (once written, cannot be deleted)   │ │
│  ✓ Each line is independent (one pipeline = one JSONL line) │ │
│  ✓ MinIO is S3-compatible (boto3, AWS SDK work natively)     │ │
│  ✗ Knowledge is written AFTER all pipeline stages complete   │ │
│    (even if validation fails, record is still written)       │ │
│  ✓ Records include all context: triggers, decisions, results │ │
│                                                                │
│  Credentials:                                                  │
│  • MINIO_ROOT_USER: MinIO username (default: minioadmin)     │ │
│  • MINIO_ROOT_PASSWORD: MinIO password                        │ │
│  • Storage: GitLab CI masked variables                       │ │
│  • Rotation: Manual (recreate container or update via API)   │ │
│                                                                │
│  Use Cases (Knowledge Retrieval):                              │
│  1. **Audit Trail**: "Show all changes to tenant X"          │ │
│  2. **Trend Analysis**: "Success rate of deployments"        │ │
│  3. **Incident Investigation**: "Replay all actions"         │ │
│  4. **AI Reasoning Context** (Future): LangGraph retrieves    │ │
│     similar past deployments to inform current decisions     │ │
│  5. **Compliance**: "Prove all changes were approved"        │ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## PART 2: COMPLETE COMMUNICATIONS MATRIX

| **From** | **To** | **Protocol** | **Data Payload** | **Timing** | **Auth** | **Restrictions** | **Credential Name** |
|---|---|---|---|---|---|---|---|
| **AI Agent** | **MCP Server** | HTTP JSON-RPC 2.0 | Tool call + args | On-demand | None (lab) / API key (prod) | Thin schema, no secrets returned | `MCP_API_KEY` (prod only) |
| **MCP Server** | **Nautobot** | REST API (POST) | Tenant/VRF/Prefix JSON | Immediate | Bearer token header | Direct write, no read-back | `NAUTOBOT_TOKEN` |
| **Nautobot** | **GitLab** | HTTP POST webhook | Entity type, change_type | Immediate | Query param token | Async pipeline trigger | `WEBHOOK_TRIGGER_TOKEN` |
| **GitLab CI** | **OPA Policy** | Docker IPC sidecar | NetAsCode YAML JSON | First pipeline stage | None (same network) | Fail-closed if unreachable | None |
| **GitLab CI** | **Vault** | HTTPS REST | Secret path GET | Pre-execution | Token header | Read-only path access | `VAULT_TOKEN` |
| **GitLab CI** | **APIC** | HTTPS REST (Terraform) | HCL manifest | During execution | Username/password | Serialized per domain | APIC credentials (via Vault) |
| **GitLab CI** | **Devices** | SSH (Ansible) | Playbook directives | Post-Terraform | Key-pair or password | Agentless, parallel | Device credentials (via Vault) |
| **GitLab CI** | **APIC** | REST (pyATS) | API queries | Post-Ansible | Session cookie | Read-only verification | APIC credentials (via Vault) |
| **pyATS** | **Nautobot** | REST API (PATCH) | Custom field updates | Post-verification | Bearer token | Feedback loop close | `PIPELINE_STATUS_TOKEN` |
| **GitLab CI** | **MinIO** | S3 API (SigV4) | JSONL record append | Final stage | AWS SigV4 auth | Append-only, immutable | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| **Prometheus** | **Nautobot** | HTTP scrape | `/metrics` endpoint | Periodic (15s) | None | Read-only metrics | None |
| **Prometheus** | **OPA** | HTTP scrape | `/metrics` endpoint | Periodic (15s) | None | Read-only metrics | None |
| **Grafana** | **Prometheus/Loki** | HTTP REST | Query language | Per-dashboard | None | Read-only queries | None |
| **Promtail** | **Docker** | Socket mount | Container logs | Continuous | Socket access | Reads stdout/stderr | None |
| **Promtail** | **Loki** | HTTP POST | Log entries | Continuous | None | Append only | None |

---

## PART 3: CREDENTIAL INVENTORY & REQUIREMENTS

### Missing Credentials (Not Yet Created in Isolated Lab)

| **Credential** | **Purpose** | **Type** | **Scope** | **Current Status** | **Action Required** |
|---|---|---|---|---|---|
| `VAULT_TOKEN` | Authenticate CI jobs to Vault | UUID token | root (full) | ❌ Missing | Create via Vault init |
| `APIC_USERNAME` / `APIC_PASSWORD` | Terraform/Ansible/pyATS authenticate to APIC | Username/password | Full ACI read/write | ❌ Missing | Create in Vault (Cisco simulator defaults) |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | MinIO authentication (Knowledge Capture) | Username/password | Full S3 bucket access | ⚠️ Placeholder (`minioadmin`) | Update to lab-specific creds |
| `GIT_PUSH_TOKEN` | GitLab Project Access Token for committing generated YAML | GitLab PAT | `read_repository`, `write_repository` | ❌ Missing | Create via GitLab Project Settings |
| `PIPELINE_STATUS_TOKEN` | GitLab Project Access Token for reading pipeline/job status | GitLab PAT | `read_api` | ❌ Missing | Create via GitLab Project Settings |
| `mcp-server-status-reader` | GitLab Project Access Token for MCP Server (external to CI) | GitLab PAT | `read_api` | ❌ Missing | Create via GitLab Project Settings |
| `WEBHOOK_TRIGGER_TOKEN` | GitLab Pipeline Trigger Token (used by Nautobot webhook) | GitLab trigger token | Specific trigger only | ❌ Missing | Create via GitLab Project Settings |
| `NAUTOBOT_TOKEN` | Nautobot API authentication (read+write) | UUID token | Full DCIM/IPAM API | ✅ Exists (`0123456789abc...`) | Already configured |

---

### Credential Creation Sequence (Recommended Order)

**Phase 1: Infrastructure Secrets (Vault)**
1. Vault instance deployment
2. Initialize Vault (generate root token, unseal)
3. Create secret paths:
   - `secret/data/cisco_aci/apic` (username, password, url)
   - `secret/data/minio/root` (MINIO_ROOT_USER, MINIO_ROOT_PASSWORD)
   - `secret/data/gitlab/api_tokens` (GIT_PUSH_TOKEN, PIPELINE_STATUS_TOKEN)

**Phase 2: GitLab Integration Tokens**
1. Create `GIT_PUSH_TOKEN` (Project Access Token, `read_repository` + `write_repository`)
2. Create `PIPELINE_STATUS_TOKEN` (Project Access Token, `read_api`)
3. Create `mcp-server-status-reader` (Project Access Token, `read_api`)
4. Create `WEBHOOK_TRIGGER_TOKEN` (Pipeline Trigger, store in Nautobot webhook config)
5. Store all tokens in Vault (Phase 1 locations above)

**Phase 3: GitLab CI Variables (Reference Vault)**
1. Add `VAULT_TOKEN` to GitLab Project CI/CD Variables (masked)
2. Add `VAULT_ADDR` to GitLab Project CI/CD Variables (unmasked: `http://localhost:8200`)
3. Add `MINIO_ROOT_USER` to GitLab CI/CD Variables (masked)
4. Add `MINIO_ROOT_PASSWORD` to GitLab CI/CD Variables (masked)

**Phase 4: Component-Specific Setup**
1. Nautobot: Set `NAUTOBOT_TOKEN` in MCP Server env (already exists)
2. MCP Server: Add `mcp-server-status-reader` to MCP Server config
3. Nautobot Webhook: Set `WEBHOOK_TRIGGER_TOKEN` in webhook URL

---

## PART 4: INTEGRATION CONSTRAINTS & RESTRICTIONS

### Component Responsibilities (What Each Can/Cannot Do)

```
┌─ NAUTOBOT ──────────────────────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Own network inventory (Tenants, VRFs, Prefixes, Devices) │
│  • Store desired-state topology (Application Profiles, EPGs) │
│  • Record change history (Change Log)                        │
│  • Trigger external pipelines (Webhook)                      │
│  • Serve GraphQL/REST API queries                            │
│  • Store custom fields (validation_status, pipeline_id)      │
│  • Accept writes from MCP Server, UI, API                    │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Execute infrastructure changes directly                   │
│  • Store non-network-domain objects (future Fortinet, Azure) │
│  • Own business intent (why the change exists)               │
│  • Read Terraform state or apply it                          │
│  • Call MCP Server or external systems directly              │
│  • Be the sole SoT for non-network domains                   │
│                                                              │
│ Dependencies:                                                │
│  • PostgreSQL (data storage)                                │
│  • Redis (caching, webhooks)                                 │
│  • Network access from GitLab, MCP Server, pyATS            │
│                                                              │
│ Trigger Points:                                              │
│  • REST API POST /dcim/tenants/                             │
│  • MCP Server calls create_tenant tool                       │
│  • UI form submission                                        │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ GITLAB CI (ORCHESTRATOR) ───────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Listen to webhooks (Nautobot)                             │
│  • Run job graph (7 stages)                                  │
│  • Serialize execution (resource_group:)                     │
│  • Store artifacts (state files, logs, results)              │
│  • Enforce protected environments (approval gates)           │
│  • Retrieve secrets from Vault                               │
│  • Trigger pipeline via API (from MCP Server)                │
│  • Report pipeline status via REST API                       │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Write infrastructure directly (only via Terraform)        │
│  • Modify Nautobot directly (only via pyATS write_results)  │
│  • Store secrets (must use Vault)                            │
│  • Execute AI reasoning                                      │
│  • Guarantee real-time status (async jobs)                   │
│  • Persist knowledge (only via MinIO)                        │
│                                                              │
│ Dependencies:                                                 │
│  • PostgreSQL (GitLab internal)                              │
│  • Redis (Sidekiq, cache)                                    │
│  • GitLab Runner (job execution)                             │
│  • Git repository (pipeline definitions)                     │
│                                                              │
│ Trigger Points:                                              │
│  • Git push (pipeline.yml file changes)                      │
│  • Webhook from Nautobot                                     │
│  • API trigger call (from MCP Server)                        │
│  • Manual UI click (protected environment approval)          │
│                                                              │
│ Output Gates:                                                 │
│  • Blocks on policy deny (OPA)                               │
│  • Waits for manual approval (protected environment)         │
│  • Serializes execution (resource_group:)                    │
│  • Reports status to Nautobot (custom fields)                │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ TERRAFORM (PROVISIONING ENGINE) ──────────────────────────────┐
│ ✅ CAN:                                                       │
│  • Read NetAsCode YAML (input)                               │
│  • Authenticate to APIC (via Vault creds)                    │
│  • Create/modify/delete ACI infrastructure                   │
│  • Maintain idempotent state                                 │
│  • Generate plan (terraform plan stage)                      │
│  • Store state file (artifacts only, not version-controlled) │
│  • Support rollback (terraform destroy)                       │
│  • Validate HCL syntax                                        │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Read Nautobot directly (only generated YAML)              │
│  • Write Nautobot (no integration)                           │
│  • Make decisions (only executes what YAML specifies)        │
│  • Verify that deployment worked (pyATS does that)           │
│  • Run concurrently (serialized by GitLab resource_group:)   │
│  • Store secrets (must come from Vault)                      │
│  • Read or depend on Terraform state from other domains      │
│                                                              │
│ Dependencies:                                                │
│  • NetAsCode YAML (input)                                    │
│  • Vault credentials (at runtime)                            │
│  • Network access to APIC                                    │
│  • Terraform provider plugin (CiscoDevNet/aci)               │
│                                                              │
│ Restrictions:                                                 │
│  • APIC system tenants (common, infra, mgmt) never recreated │
│  • One domain/environment per job (serialized)               │
│  • Idempotency mandatory (same input = same output)          │
│  • Plan must be reviewed before apply (two-stage)            │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ ANSIBLE (DAY-2 OPERATIONS) ─────────────────────────────────┐
│ ✅ CAN:                                                       │
│  • Read Nautobot inventory dynamically                        │
│  • Authenticate to devices (via Vault creds)                 │
│  • Execute Day-2 playbooks (config, compliance, health)      │
│  • Report results (success/failure/info)                     │
│  • Discover device configuration (read-only)                 │
│  • Test connectivity                                          │
│  • Run agentless (no agent install required)                 │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Provision infrastructure (Terraform's role)               │
│  • Modify desired state (witness only)                       │
│  • Write Nautobot (no integration)                           │
│  • Block infrastructure changes (informational only)         │
│  • Execute in parallel across same device (Ansible forks)   │
│  • Store secrets (must come from Vault)                      │
│                                                              │
│ Dependencies:                                                │
│  • Nautobot (inventory source)                               │
│  • Device credentials (from Vault)                           │
│  • Terraform apply stage must succeed first                  │
│  • Network access to managed devices                         │
│  • SSH/NETCONF connectivity to devices                       │
│                                                              │
│ Trigger:                                                      │
│  • Always after terraform_apply succeeds (GitLab job order) │
│                                                              │
│ Restrictions:                                                 │
│  • Day-2 only (no initial provisioning)                      │
│  • Failures are non-blocking (info stage)                    │
│  • Idempotent playbooks recommended                          │
│  • No state persistence (every run re-discovers devices)     │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ PyATS (VERIFICATION) ──────────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Read desired state from Nautobot                          │
│  • Query live infrastructure independently                   │
│  • Compare desired vs. actual state                          │
│  • Generate test reports (pass/fail/warnings)                │
│  • Write results back to Nautobot (custom_fields)            │
│  • Detect drift/mismatches                                   │
│  • Run verification independently                            │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Modify Nautobot desired state                             │
│  • Fix infrastructure automatically (read-only)              │
│  • Block pipeline (info stage currently)                     │
│  • Store persistent test history (MinIO does that)           │
│  • Depend on Terraform success (independent query)           │
│  • Make decisions (only reports facts)                       │
│                                                              │
│ Dependencies:                                                │
│  • Nautobot (reads desired state)                            │
│  • Device credentials (from Vault)                           │
│  • Network access to live devices                            │
│  • Terraform apply must have completed (device exists)       │
│  • pyATS test definitions (hardcoded in job.py)              │
│                                                              │
│ Trigger:                                                      │
│  • Always after ansible_configure succeeds                   │
│                                                              │
│ Restrictions:                                                 │
│  • Independent (must not depend on Terraform logs)           │
│  • Read-only (never modifies fabric)                         │
│  • Verification failures = info only (currently)             │
│  • Must re-query live devices (no caching)                   │
│                                                              │
│ Feedback Loop:                                                │
│  • Writes custom_fields back to Nautobot via PATCH           │
│  • Closes the loop: Verification → SoT                       │
│  • AI can query custom_fields for status                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ MCP SERVER (AI INTERFACE) ─────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Expose business-operation tools                           │
│  • Accept tool calls from AI agents                          │
│  • Write Nautobot objects (intent)                           │
│  • Trigger GitLab pipeline (via Nautobot webhook response)  │
│  • Query GitLab for pipeline status (read-only)              │
│  • Return status to caller (thin response)                   │
│  • Validate tool arguments (Pydantic schemas)                │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Execute infrastructure directly                           │
│  • Own shared intent schema (per-tool schemas only)          │
│  • Store secrets (pass-through only)                         │
│  • Modify infrastructure (Terraform's role)                  │
│  • Orchestrate multi-step workflows                          │
│  • Read/write Terraform state                                │
│  • Bypass Nautobot write (no alternate path)                 │
│  • Expose execution details or logs                          │
│                                                              │
│ Dependencies:                                                │
│  • Nautobot reachable                                        │
│  • GitLab reachable                                          │
│  • Vault reachable (for credentials)                         │
│  • Network access from AI client                             │
│  • NAUTOBOT_TOKEN env var                                    │
│                                                              │
│ Trigger Points:                                              │
│  • AI agent calls tool via MCP protocol                      │
│  • Human calls tool via CLI (future)                         │
│                                                              │
│ Restrictions:                                                 │
│  • No shared generic schema (each tool owns its shape)       │
│  • Thin per-tool validation only                             │
│  • No re-orchestration of business logic (pass-through)      │
│  • Status polling only (can't stream pipeline events)        │
│  • No direct access to execution engines                     │
│                                                              │
│ "AI Reasons, Platform Executes" Boundary:                    │
│  • MCP Server is ONLY input device                           │
│  • GitLab CI is ONLY execution engine                        │
│  • No feedback from execution to MCP (async only)            │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ OPA POLICY ENGINE ──────────────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Evaluate Rego policies                                    │
│  • Query facts from NetAsCode YAML                           │
│  • Return allow/deny decision with reasoning                 │
│  • Block infrastructure changes (fail-closed)                │
│  • Expose policy evaluation metrics                          │
│  • Operate as stateless sidecar (no storage)                 │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Modify intent (policies are read-only)                    │
│  • Make infrastructure decisions (only governance)           │
│  • Store state (stateless engine)                            │
│  • Communicate outside the policy query/response cycle       │
│  • Provide audit trail (GitLab logs record it)               │
│  • Be optional (fail-closed if unreachable)                  │
│                                                              │
│ Dependencies:                                                │
│  • NetAsCode YAML (policy input)                             │
│  • GitLab CI network access                                  │
│  • Rego policy files (policy definitions)                    │
│                                                              │
│ Trigger:                                                      │
│  • Always in policy stage (3rd pipeline stage)               │
│                                                              │
│ Restrictions:                                                 │
│  • Policies are independent (no cross-policy state)          │
│  • Policies must be deterministic (same input → same output) │
│  • Policies never have side effects                          │
│  • Failure mode: Any error = deny (fail-closed)              │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─ VAULT (SECRETS STORAGE) ───────────────────────────────────┐
│ ✅ CAN:                                                      │
│  • Store secrets at rest (encrypted)                         │
│  • Serve secrets to authenticated clients                    │
│  • Rotate secrets (policy-driven)                            │
│  • Audit all secret access                                   │
│  • Provide different secrets to different clients (RBAC)     │
│  • Seal/unseal (key management)                              │
│  • Expose /health endpoint (liveness check)                  │
│                                                              │
│ ❌ CANNOT:                                                    │
│  • Be optional (all secrets come from here)                  │
│  • Store secrets in logs or pipelines                        │
│  • Execute jobs (storage only)                               │
│  • Modify secrets without audit (write operations logged)    │
│  • Provide secrets without authentication (token required)   │
│  • Survive container destruction (state not persisted)       │
│                                                              │
│ Dependencies:                                                │
│  • Persistent storage (Docker volume)                        │
│  • Key material (root token, unseal keys)                    │
│  • Network access from CI/Terraform/Ansible                  │
│                                                              │
│ Restrictions:                                                 │
│  • Root token should be rotated in production                │
│  • All secrets must be versioned (update history)            │
│  • Audit logging mandatory                                   │
│  • Network reachability assumed (no fallback if down)        │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## PART 5: RECOMMENDED INTEGRATION SEQUENCE

**✋ STOP HERE FOR USER REVIEW & FEEDBACK**

This comprehensive architecture diagram outlines:

1. **All 7 communication layers** (each with protocol, auth, payload details)
2. **Complete component responsibility matrix** (what each can/cannot do)
3. **All credential requirements** (missing vs. existing, organized by phase)
4. **Communication flows & restrictions** (directional, timing, gates)
5. **Feedback loops** (how status flows back from execution to SoT)

### **Next Steps (Awaiting Your Feedback):**

Before I proceed with the integration plan and Vault setup, please review and provide feedback on:

1. **Does this architecture match your understanding of the platform?**
2. **Are there any communication flows you'd like clarified or corrected?**
3. **Do the restrictions on each component align with your design intent?**
4. **Any credentials or secret requirements you'd like to add/modify?**
5. **Should I proceed with creating the Vault instance + credential setup?**

Once you confirm, I'll provide:
- **Detailed step-by-step integration checklist** (which components to wire in which order)
- **Vault initialization & credential creation** (with all missing passwords generated)
- **End-to-end test scenario** (confirm full pipeline works)
- **Operational runbook** (how to troubleshoot if anything breaks)

---

**Please review the diagram and provide your feedback. I'm ready to proceed once you confirm the architecture is correct.**


