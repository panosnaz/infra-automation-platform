---
title: "ACI — Restore the Fabric from a Pre-Apply Backup"
description: "Every terraform apply first takes an APIC snapshot. How to find the right one and roll the fabric back, and the one-time AES setup that makes backups possible."
type: runbook
domain: cisco_aci
status: active
tags: [runbook, backup, restore, rollback, apic]
owner: platform-engineering-team
last_updated: 2026-10-17
---

# ACI — Restore the Fabric from a Pre-Apply Backup

Every `terraform_apply` job runs `platform/workflows/scripts/apic_backup.py --create` **before** it changes anything:

* It takes an APIC configuration snapshot (`uni/fabric/configexp-platform-pre-apply`), waits for it to complete, and records it in the job artifact `apic-backup.json`.
* No completed snapshot means no apply: the step fails closed.
* The newest 20 snapshots are kept.

## When to use this

An apply succeeded but broke something. The usual first answer is **not** a restore: fix the intent in Nautobot, re-run the pipeline, and let Terraform converge. Restore when you need the fabric back *now*, exactly as it was before a specific apply.

A restore changes the APIC behind Terraform's back. **Afterwards, Nautobot and the Terraform state still describe the post-apply intent**, so the next pipeline run will re-apply it. Fix the intent in Nautobot before the next run, or the restore is undone.

## 1. Load the credentials

```bash
export VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=...      # lab: docker/vault/state/vault-keys.txt (gitignored)
source platform/terraform/aci/scripts/load-vault-creds.sh    # exports TF_VAR_aci_* and APIC_EXPORT_PASSPHRASE
```

## 2. Find the snapshot

The failed pipeline's `terraform_apply` job artifact `apic-backup.json` names it (`file_name`). Artifacts are kept even when the apply fails. Or list them, newest first. Each description carries the pipeline ID and commit:

```bash
python platform/workflows/scripts/apic_backup.py --list
```

## 3. Restore

```bash
# merge (default): adds back what the apply deleted or changed; leaves objects the apply ADDED in place
python platform/workflows/scripts/apic_backup.py --restore <file_name> --confirm <file_name>

# replace: makes the whole fabric configuration match the snapshot, removing what the apply added
python platform/workflows/scripts/apic_backup.py --restore <file_name> --confirm <file_name> --import-type replace
```

The file name must be typed twice. The import is atomic: all or nothing.

| Import type | Proven on the lab | Use when |
|---|---|---|
| `merge` | **Yes** (2026-10-17): a deleted tenant came back with its VRF, BD, AP and EPG | The apply deleted or changed objects |
| `replace` | **Yes** (2026-10-17, approved): a tenant and a fabric VLAN pool added after the snapshot were removed. Tenants, VLAN pools and the 8 fabric singletons were byte-identical afterwards, with no new faults, the AES key intact and login working | The apply added objects that must go, and a merge is not enough. It rewrites the WHOLE fabric configuration, so anything changed by hand since the snapshot is lost too |

## 4. Check

```bash
python platform/workflows/scripts/check_apic_faults.py --snapshot faults-after-restore.json   # look for new faults
```

Then fix the intent in Nautobot (see "When to use this").

## One-time setup: the AES export passphrase

APIC 6.2 **refuses every configuration export**, snapshots included, until a global AES passphrase is configured: "Strong encryption key is mandatory to the export the configuration". A fresh APIC has none, so the first backup fails closed until this is done.

1. Put a 16–32 character passphrase in Vault as `apic_export_passphrase` in `secret/lab/platform`. **Keep it.** Restoring the secure fields (passwords, keys) of any backup needs the same passphrase.
2. Run once:
   ```bash
   source platform/terraform/aci/scripts/load-vault-creds.sh
   python platform/workflows/scripts/apic_backup.py --enable-encryption
   ```

`--enable-encryption` **never overwrites an existing key**. The APIC cannot say whether its key matches Vault's, and replacing it would make the secure fields of every earlier backup unrecoverable. Enabling the key also clears fault F4674 ("Need strong encryption to be enabled").
