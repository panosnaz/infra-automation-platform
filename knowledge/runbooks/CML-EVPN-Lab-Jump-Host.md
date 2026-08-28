---
type: runbook
domain: vxlan_evpn
status: active
tags: [cml, evpn, nexus, terraform, jump-host]
owner: platform-engineering-team
last_updated: 2026-07-30
---

# CML EVPN Lab — Managing Nodes via an In-Lab Jump Host

**Project:** Network Platform Engineering Platform

**Document Type:** Operational Runbook

**Related:** [ADR-021 — VXLAN EVPN Domain Expansion](../adr/ADR-021-VXLAN-EVPN-Domain-Expansion.md) §5–6 (the discovery narrative and evidence this runbook is distilled from), [`Platform-Status-and-Pending-Items.md`](../architecture/Platform-Status-and-Pending-Items.md) §2 (current open items)

---

# Purpose

The real Cisco Modeling Labs instance used for EVPN live verification (`https://172.30.46.250`, CML 2.10.0) has a networking limitation: its `external_connector` node type only works in **NAT mode**, not **Bridge mode** (confirmed, root cause unknown — see ADR-021 §5). NAT mode is outbound-only by CML's own design, so nothing outside CML (this machine, Terraform running locally, etc.) can reach a lab node's management IP directly.

**The workaround: run Terraform (and any other automation) from a lightweight VM *inside* the lab's own network**, on the same Out-of-Band (OOB) management segment as the real Nexus 9000v nodes. This runbook documents that pattern end to end, so it doesn't need to be rediscovered.

---

# Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │              VXLAN-EVPN-MultiSite lab         │
                 │                                                │
  (blocked)      │   DC1-Leaf   DC1-BGW   DC2-Leaf   DC2-BGW      │
  Bridge mode ✗  │      │mgmt0     │mgmt0    │mgmt0     │mgmt0    │
                 │      └────┬─────┴────┬────┴────┬─────┘        │
                 │           │      OOB-switch     │              │
                 │           │   (unmanaged_switch) │              │
                 │           └──────────┬───────────┘             │
                 │                      │                          │
                 │                 jump-host (alpine)               │
                 │                 eth0 ─┘   eth1 ──┐               │
                 │                                   │              │
                 │                          OOB-ext (external_       │
                 │                          connector, NAT mode) ✓  │
                 └──────────────────────────┬────────────────────────┘
                                            │ outbound only
                                      CML's own NAT gateway
                                      (192.168.255.1)
```

- **OOB-switch** (`unmanaged_switch`) — an L2 hub. All lab nodes' `mgmt0` interfaces connect here, plus the jump host's first NIC. This is what gives the jump host direct L2 reachability to every switch's management IP.
- **OOB-ext** (`external_connector`, **NAT mode**) — gives the jump host outbound-only internet/CML-API access via its second NIC. Bridge mode does not work on this instance; don't retry it without a reason to believe the underlying CML host issue has changed.
- **jump-host** (`alpine`) — the actual automation runner. Alpine, not Ubuntu: it needs only 512 MB RAM vs. Ubuntu's 2 GB, and already ships with `ssh`/`scp`/`sftp`/`wget`/`unzip`/`tar` (busybox), which is everything needed here.

---

# Step-by-step: building this from scratch in a lab

All commands assume CML admin credentials are in Vault (`secret/lab/cml`) and `VAULT_TOKEN` is exported. Get a bearer token first:

```bash
CML_URL="https://172.30.46.250"
CML_USER=$(vault kv get -field=username secret/lab/cml)   # or read directly via curl, see below
CML_PASS=$(vault kv get -field=password secret/lab/cml)
TOKEN=$(curl -sk -X POST "$CML_URL/api/v0/authenticate" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$CML_USER\",\"password\":\"$CML_PASS\"}" | tr -d '"')
```

## 1. Create the OOB hub and NAT connector

```bash
LAB=<lab-id>   # GET $CML_URL/api/v0/labs to find it

# Unmanaged switch = the L2 hub
SW=$(curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/nodes" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_definition":"unmanaged_switch","label":"OOB-switch","x":100,"y":300}')
SW_ID=$(echo "$SW" | jq -r .id)

# External connector — MUST be NAT, not Bridge (Bridge silently never leaves DEFINED_ON_CORE on this instance)
EXT=$(curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/nodes" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_definition":"external_connector","label":"OOB-ext","x":100,"y":400,"configuration":"NAT"}')
EXT_ID=$(echo "$EXT" | jq -r .id)
```

Interfaces are **not** auto-created — add one per link you intend to make:

```bash
curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/interfaces" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"node\":\"$SW_ID\"}"   # repeat once per switch you'll wire + once for the jump host
curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/interfaces" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"node\":\"$EXT_ID\"}"
```

**Gotcha:** adding an interface to a node that is already `STARTED` fails with `400 "Physical configuration of node is locked"`. Stop the node, **poll until it actually reports `STOPPED`** (not just accept the 204 from the stop call), add the interface, then restart.

## 2. Wire mgmt0 on each real node to the OOB-switch

```bash
# Find each node's mgmt0 interface id
curl -sk "$CML_URL/api/v0/labs/$LAB/nodes/$NODE_ID/interfaces?data=true" -H "Authorization: Bearer $TOKEN"

# Link it to a free OOB-switch port
curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/links" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d "{\"src_int\":\"$SW_PORT_ID\",\"dst_int\":\"$NODE_MGMT0_ID\"}"
```

**Gotcha:** a newly-created link on an *already-running* peer node does not come up automatically. Start the interface explicitly:

```bash
curl -sk -X PUT "$CML_URL/api/v0/labs/$LAB/interfaces/$NODE_MGMT0_ID/state/start" -H "Authorization: Bearer $TOKEN"
```

## 3. Create the jump host

```bash
JH=$(curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/nodes" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_definition":"alpine","label":"jump-host","x":200,"y":450}')
JH_ID=$(echo "$JH" | jq -r .id)

# Two interfaces: one to OOB-switch (reach the real nodes), one to OOB-ext (outbound)
curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/interfaces" -H "Authorization: Bearer $TOKEN" -d "{\"node\":\"$JH_ID\"}"
curl -sk -X POST "$CML_URL/api/v0/labs/$LAB/interfaces" -H "Authorization: Bearer $TOKEN" -d "{\"node\":\"$JH_ID\"}"
# ...link eth0 -> a free OOB-switch port, eth1 -> OOB-ext's port, same POST /links pattern as above

curl -sk -X PUT "$CML_URL/api/v0/labs/$LAB/nodes/$JH_ID/state/start" -H "Authorization: Bearer $TOKEN"
```

**Memory requirement, learned the hard way:** each real Nexus 9000v node needs **12 GB RAM** (check any node's `node_definition.sim.linux_native.ram`, don't assume). A 4-node EVPN lab alone needs 48 GB. If the jump host node stays stuck `QUEUED`/`boot_progress:"Not running"` forever with no error from the REST API (`start` returns `204` every time), check `journalctl -u virl2-controller` via Cockpit (`https://<cml-host>:9090`, `sysadmin` login) for `core_controller:...Failed to choose a suitable compute host: ... Not enough memory`. The REST API does **not** surface this error back to the caller — a silently-stuck `QUEUED` node is not necessarily a bug, it may just be a resource problem. Use `alpine` (512 MB) over `ubuntu` (2 GB) to minimize this risk.

## 4. Console into the jump host and configure networking

```bash
ssh -tt admin@172.30.46.250 "open /<lab-name>/jump-host/0"
# login: cisco / cisco (confirmed from the alpine node_definition's day-0 config, not guessed)
```

Inside:

```sh
sudo ip addr add 172.30.46.224/24 dev eth0     # static, same subnet as the real nodes' mgmt0
sudo ip link set eth1 up
sudo udhcpc -i eth1                             # picks up CML's NAT address, e.g. 192.168.255.163/24
```

Verify both paths:

```sh
ping -c2 172.30.46.220        # a real switch's mgmt0 — should succeed once it's finished booting (NX-OS boot takes several minutes)
ping -c2 192.168.255.1        # CML's own NAT gateway — should always succeed
```

## 5. Enable NX-API on each real node (once, via console, not via the jump host)

```
configure terminal
interface mgmt0
  ip address <ip>/24
  no shutdown
  exit
feature nxapi
nxapi https port 443
end
copy running-config startup-config
```

Verify NX-API is actually listening (not just that the port is open) from the jump host:

```sh
AUTH=$(printf 'admin:cisco' | base64)
wget --no-check-certificate -O- --header="Authorization: Basic $AUTH" https://<node-ip>/ins
# 401 Unauthorized (without a real POST body) is the CORRECT answer — it proves NX-API is up and answering
```

**Gotcha:** busybox `wget` (the one on alpine) has no `--user`/`--password` flags — always build the `Authorization: Basic` header manually.

## 6. Get Terraform + the `nxos` provider onto the jump host

The jump host's NAT path can reach `releases.hashicorp.com` fine (the Terraform CLI binary downloads normally), but **`registry.terraform.io` and `github.com` are both blocked from this lab's network egress** (confirmed: Terraform's own TLS client fails trust verification against the registry; `wget` gets a `403` from GitHub with or without a browser User-Agent — two distinct, real failures, not a fluke or a simple bot-detection issue).

```sh
cd /tmp && wget --no-check-certificate -O terraform.zip \
  https://releases.hashicorp.com/terraform/1.9.5/terraform_1.9.5_linux_amd64.zip
unzip -o terraform.zip && mv terraform /usr/local/bin/
```

For the provider plugin, use **CML's own SCP/SFTP dropfolder** instead of the open internet:

```bash
# On a machine WITH normal internet access (not the jump host):
cd platform/terraform/evpn
terraform providers mirror /tmp/nxos-mirror   # only ~9 MB compressed for CiscoDevNet/nxos 0.13.1
sftp admin@172.30.46.250   # same CML admin creds
sftp> put /tmp/nxos-mirror/registry.terraform.io/ciscodevnet/nxos/terraform-provider-nxos_0.13.1_linux_amd64.zip
```

Then, **from the jump host**, pull it back down — and this is the key trick: **the same dropfolder is reachable from inside the lab**, via CML's internal NAT gateway address, not just the external one:

```sh
sftp admin@192.168.255.1   # NOT 172.30.46.250 — this is the internal path, reachable from eth1
sftp> get terraform-provider-nxos_0.13.1_linux_amd64.zip
```

**Gotcha:** plain `scp -O <file> admin@192.168.255.1:` fails with `Exit status 1` (the legacy scp/exec-channel protocol isn't accepted on this internal path). Use interactive `sftp`, or `scp` without `-O`, instead.

Point Terraform at the local copy instead of the network:

```sh
mkdir -p /tmp/tf-mirror/registry.terraform.io/ciscodevnet/nxos
cp terraform-provider-nxos_0.13.1_linux_amd64.zip /tmp/tf-mirror/registry.terraform.io/ciscodevnet/nxos/

cat > ~/.terraformrc <<'EOF'
provider_installation {
  filesystem_mirror {
    path = "/tmp/tf-mirror"
  }
  direct {
    exclude = ["registry.terraform.io/*/*"]
  }
}
EOF
```

**Gotcha:** the filesystem mirror expects the zip filename exactly as `<mirror-path>/registry.terraform.io/<namespace>/<type>/<type>_<version>_<os>_<arch>.zip` — don't nest it under an extra version/platform subdirectory, `terraform init` will report `"was not found in any of the search locations"` if the layout is wrong.

`terraform init` in your module directory should now succeed fully offline.

## 7. Run Terraform against the real switch

Point the provider block at the real management IP and run the normal `plan` → `apply` → `plan` (confirm 0 drift) → `destroy` cycle exactly as you would against any other target.

**Verify results independently of Terraform's own output** — query the device directly (via NX-API, as in step 5, or console) both after `apply` and after `destroy`. This caught a real bug: `terraform destroy` on `nxos_feature` used to report success without actually reverting the device's feature state -- **fixed** with a destroy-time provisioner that issues the real NX-API revert commands directly, live-verified end-to-end against `DC1-Leaf` (ADR-021 §15/§16). Never assume a reported-successful destroy actually happened without independent verification -- that discipline is still worth keeping even though this specific bug is closed.

---

# Known limitations of this pattern

- **Bridge-mode external connectivity remains unexplained.** This runbook's whole existence is a workaround for it, not a fix. If a future CML upgrade or System Administration Cockpit configuration change resolves it, this jump-host pattern becomes unnecessary and direct external Terraform execution (no jump host) would be simpler — revisit if that ever changes.
- **NX-OS console pagination can get stuck** on long, unfiltered `show` commands (observed: a `--More--` prompt that never responds to `q`/space as "quit", only ever advancing one line per keystroke, and this state persists across SSH reconnects since it's the same live serial console). Prefer NX-API JSON queries over console `show` commands for anything that isn't a quick, filtered check.
- **This pattern is now wired into a real CI pipeline.** The manual, interactive discovery process documented above (steps 1-7) was later automated as a set of reusable relay scripts (`pipelines/scripts/cml-jump-relay.sh`, `cml-terraform-run.sh`, `cml-ansible-run.sh`, `cml-verify-fabric-run.sh` -- see ADR-021 §17-§23) that GitLab CI jobs in `pipelines/evpn.gitlab-ci.yml` call directly, which is itself included from the root `.gitlab-ci.yml` alongside ACI's. Every job (`terraform_plan`/`terraform_apply`/`ansible_configure`/`pyats_verify`) runs through this relay automatically today -- nothing in the day-to-day pipeline is manual console/API work anymore. This runbook remains accurate as the *original discovery record* and for one-time lab topology changes (adding a node, rewiring OOB), not as the current operational procedure.
