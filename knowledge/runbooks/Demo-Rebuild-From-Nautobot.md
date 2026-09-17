---
title: "Demo Runbook — Rebuild the ACI Fabric from Nautobot"
description: "Wipe the APIC, rebuild everything from Nautobot as the source of truth, and show the evidence. Written to be followed live in front of an audience."
type: runbook
domain: cisco_aci
status: active
tags: [demo, runbook, rebuild, evidence]
owner: platform-engineering-team
last_updated: 2026-09-17
---

# Demo Runbook — Rebuild the ACI Fabric from Nautobot

**What this demonstrates.** Nautobot holds the intent. The APIC holds nothing that cannot be rebuilt from it. Erase the fabric, run the pipeline, and the fabric comes back.

**What it does not demonstrate.** That every scenario deploys cleanly. One does not, by design — see [§5](#5-the-one-scenario-that-will-not-come-back-clean). Read that before you stand in front of anyone.

---

## 0. Before the audience arrives

Run these once. Each takes seconds and each has caught a real problem before.

```bash
export NAUTOBOT_URL=http://localhost:8080
export NAUTOBOT_TOKEN=<token>          # NOT the one in CLAUDE.md -- see note below
export TF_VAR_aci_url=https://172.30.46.103
export TF_VAR_aci_username=admin
export TF_VAR_aci_password=<password>  # or: source platform/terraform/aci/scripts/load-vault-creds.sh

# 1. Nautobot schema complete? (32 Custom Fields + the Location)
python platform/workflows/scripts/bootstrap_nautobot.py --verify --location "Isolated Lab Site"

# 2. Intent regenerates deterministically?
python platform/python/generate_aci.py
python platform/python/generate_aci.py       # run twice; output must be identical

# 3. Terraform agrees with reality?
cd platform/terraform/aci && terraform plan
```

Step 1 must print `OK: schema complete`. **If it does not, stop.** Writes to an undeclared Custom Field return HTTP 200 and are silently discarded — the tools will report success and build nothing, which is a far worse thing to discover live.

> **Nautobot token.** `CLAUDE.md` documents `0123456789abcdef...`, which does not exist on the isolated instance and returns 403. Get the real one:
> ```bash
> echo 'from nautobot.users.models import Token; print([str(t.key) for t in Token.objects.all()])' \
>   | docker exec -i infra-automation-nautobot-isolated-isolated-nautobot-1 nautobot-server nbshell
> ```

---

## 1. Capture the "before" state

Show the audience what exists, so the wipe is visibly real.

```bash
# object counts and the fault baseline
python platform/workflows/scripts/check_apic_faults.py --snapshot /tmp/before-wipe.json
cd platform/terraform/aci && terraform state list | wc -l     # ~116 resources
```

Worth saying out loud: **Terraform's state file believes all ~116 objects exist.** You are about to delete them behind its back. That it recovers is part of the point.

---

## 2. Wipe the APIC

Delete the managed tenant and the fabric-wide objects. **Do not touch `common`, `infra` or `mgmt`** — ACI system tenants, which this platform never manages.

Via the APIC GUI, or:

```bash
# tenant
curl -sk -X POST "$TF_VAR_aci_url/api/mo/uni/tn-sales.json" -H "Cookie: APIC-cookie=$TOK" \
  -d '{"fvTenant":{"attributes":{"name":"sales","status":"deleted"}}}'
```

Then confirm in the GUI that `sales` is gone. Let the audience see the empty fabric.

---

## 3. Re-snapshot faults **after** the wipe

```bash
python platform/workflows/scripts/check_apic_faults.py --snapshot /tmp/before-rebuild.json
```

**This step is easy to skip and ruins the evidence if you do.** Comparing against the pre-wipe baseline makes every rebuilt object look like a brand-new fault. The snapshot must be taken against the *empty* fabric.

---

## 4. Rebuild

Nautobot was never touched, so the intent is still there.

```bash
python platform/python/generate_aci.py
cd platform/terraform/aci
terraform plan          # will show ~116 to add -- Terraform detected the wipe
terraform apply
```

**Why the stale state does not matter.** Terraform refreshes against the live APIC before planning. It finds the objects gone and plans to recreate them. Rehearsed 2026-09-17 on a throwaway tenant: `apply (6 added)` → wipe → `plan (6 to add)` → `apply (6 added)` → `plan (No changes)`.

Then verify:

```bash
python platform/workflows/scripts/check_apic_faults.py --compare /tmp/before-rebuild.json \
    platform/netascode/aci/tenants.yaml
terraform plan          # expect: 0 to add, 0 to destroy
```

---

## 5. The one scenario that will not come back clean

**The L4-L7 / PBR service graph will return with 10 faults.** Expected, measured, and not a regression.

An ACI service graph needs a *concrete device* — the actual firewall. For a VIRTUAL device, APIC resolves it through vCenter's inventory to find the VM and its vNICs. This lab has no vCenter, so there is nothing to resolve, and the logical device is flagged `vnsConfIssue-missing-cdev`.

Measured A/B on a throwaway tenant: adding a concrete device does **not** help — the count stays at 10 and simply trades those faults for `F1778`/`F0765` (cannot reach the controller). **10 is the floor without a vCenter.**

Two honest ways to handle it in front of your team:

- **Exclude it** from the green narrative and present it as a known environmental limit with a measured number.
- **Show it deliberately** as evidence the *verification* works: Terraform reported success, and the fault check caught that APIC considered the config invalid anyway. That is a stronger story than a clean run — it shows the platform does not take "apply succeeded" as proof.

Everything else — tenants, VRFs, bridge domains, EPGs, contracts, L3Outs, route maps, interface policies, access policies — returns clean.

Two other faults are also expected and unrelated to your work: `F0699 Node Not Leaf For Infra Policies` and `F0721` on a VLAN pool. Both are consequences of a fabric with **no switches**; they appear for pre-existing objects too.

---

## 6. What to say when someone asks "would this work on our fabric?"

Honest answers, with the evidence behind them:

| Question | Answer |
|---|---|
| Does it need this exact lab? | No. `bootstrap_nautobot.py` declares the full schema on any Nautobot; `--verify` checks one without changing it. |
| Where do APIC credentials come from? | HashiCorp Vault via `load-vault-creds.sh`. Nothing is committed; `terraform.tfvars` is gitignored. |
| Does it require disabling TLS validation? | No. `aci_insecure` defaults to `false`; it is set `true` only for this simulator's self-signed certificate. |
| Does it assume one site? | The Location resolves at call time. One Location is used automatically; several must be named explicitly, and it refuses to guess. |
| What is *not* proven? | Anything needing real switches. This fabric has none, so physical paths sit `state: unformed` and no traffic has ever been forwarded. Per-item status is in [`Evidence-Matrix.md`](../architecture/Evidence-Matrix.md). |

---

## 7. If something goes wrong live

| Symptom | Cause | Fix |
|---|---|---|
| Tools report success, YAML nearly empty | A Custom Field is not declared | `bootstrap_nautobot.py` then regenerate |
| `Location 'X' not found` | Location name differs from this lab's | Omit `location` — it auto-resolves — or pass the real name |
| `403` from Nautobot | Stale token from `CLAUDE.md` | Get the real token (§0) |
| `Duplicate object key` in Terraform | Two intent entries share a name | Remove the duplicate in Nautobot; several `create_*` tools used to append rather than dedupe |
| Plan shows changes right after an apply | Known cosmetic drift | `aci_function_node` and `ospf ctrl` never converge — see Platform-Status |
| APIC unreachable | Docker subnet collision, not an outage | `docker network ls` — a recurring bug class in this lab |

---

## 8. Rehearse it once

The full sequence takes minutes. Run it end to end the day before, against the real APIC, and write down the numbers you get — object count, fault count, plan output. Then you are reading from your own notes on the day rather than interpreting output live.
