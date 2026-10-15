#!/usr/bin/env python3
"""Execution Framework -- configuration backup of the APIC before every apply.

`terraform apply` changes the fabric; this takes an APIC configuration
snapshot first, waits for it to complete, and records which snapshot it was,
so a bad apply can be rolled back to the exact state it started from. It
fails closed: no completed snapshot, no apply (same principle as
check_apic_faults.py and policy_check.py, ADR-014).

APIC 6.2 refuses EVERY configuration export -- snapshots included, with or
without secure fields -- until the global AES encryption passphrase is set
("Strong encryption key is mandatory to the export the configuration",
measured 2026-10-17). The passphrase is a secret: it lives in Vault
(`apic_export_passphrase` in secret/lab/platform), never in Git or Nautobot,
and it is needed again to restore the secure fields of any backup.

    apic_backup.py --enable-encryption          one-time; refuses to overwrite a key
    apic_backup.py --create OUT.json [--reason TEXT] [--keep N]
    apic_backup.py --list
    apic_backup.py --restore FILE --confirm FILE [--import-type merge|replace]

Environment: TF_VAR_aci_url / TF_VAR_aci_username / TF_VAR_aci_password (from
platform/terraform/aci/scripts/load-vault-creds.sh), and for
--enable-encryption APIC_EXPORT_PASSPHRASE (same script).
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

POLICY = "platform-pre-apply"
POLICY_DN = f"uni/fabric/configexp-{POLICY}"
IMPORT_POLICY = "platform-restore"
IMPORT_DN = f"uni/fabric/configimp-{IMPORT_POLICY}"
DEFAULT_KEEP = 20
JOB_TIMEOUT = 600
_DONE = {"success", "fail", "failed", "partial-success"}


class ApicError(RuntimeError):
    """APIC unreachable, rejected the request, or a job did not succeed."""


class Apic:
    """Minimal APIC REST session -- stdlib only, so the apply job's slim image
    needs nothing installed."""

    def __init__(self, url: str, username: str, password: str, insecure: bool = True):
        self.url = url.rstrip("/")
        self.ctx = None
        if insecure:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        self._username, self._password = username, password
        self._token = ""
        self.login()

    def login(self) -> None:
        payload = self._send("POST", "/api/aaaLogin.json",
                             {"aaaUser": {"attributes": {"name": self._username, "pwd": self._password}}}, auth=False)
        self._token = payload["imdata"][0]["aaaLogin"]["attributes"]["token"]

    def _send(self, method: str, path: str, body: dict | None = None, auth: bool = True) -> dict:
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Cookie"] = f"APIC-cookie={self._token}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{self.url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60, context=self.ctx) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                text = json.load(exc)["imdata"][0]["error"]["attributes"]["text"]
            except Exception:  # noqa: BLE001 -- the APIC's own message when it gives one
                text = str(exc)
            raise ApicError(f"APIC rejected {method} {path}: {text}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApicError(f"could not reach APIC at {self.url}: {exc}") from exc

    def get(self, path: str) -> list[dict]:
        return self._send("GET", f"/api/{path}")["imdata"]

    def post(self, dn: str, cls: str, attributes: dict) -> None:
        self._send("POST", f"/api/mo/{dn}.json", {cls: {"attributes": {"dn": dn, **attributes}}})

    def attrs(self, dn: str, cls: str) -> dict:
        found = self.get(f"mo/{dn}.json")
        return found[0][cls]["attributes"] if found else {}

    def class_under(self, cls: str, fragment: str) -> list[dict]:
        rows = self.get(f'node/class/{cls}.json?query-target-filter=wcard({cls}.dn,"{fragment}")')
        return [r[cls]["attributes"] for r in rows]


# --- pure helpers (unit-tested) -------------------------------------------------------

def encryption_state(crypt: dict) -> tuple[bool, str]:
    """(usable, reason) for an exportcryptkey's attributes."""
    if crypt.get("keyConfigured") != "yes":
        return False, "no AES encryption passphrase is configured on the APIC -- run --enable-encryption once"
    if crypt.get("strongEncryptionEnabled") != "yes":
        return False, "the AES passphrase is configured but strong encryption is disabled"
    return True, "AES encryption configured and enabled"


def check_passphrase(passphrase: str) -> None:
    """APIC accepts 16-32 characters."""
    if not 16 <= len(passphrase) <= 32:
        raise ApicError(f"the passphrase must be 16-32 characters, got {len(passphrase)}")


def newest_job_after(jobs: list[dict], started: str) -> dict | None:
    """The job a trigger produced: the newest by executeTime at or after the
    trigger time (ISO strings compare correctly when in the same format)."""
    later = [j for j in jobs if (j.get("executeTime") or "") >= started]
    return max(later, key=lambda j: j.get("executeTime") or "") if later else None


def to_retire(snapshots: list[dict], keep: int) -> list[dict]:
    """Snapshots beyond the newest `keep`, oldest first."""
    ordered = sorted(snapshots, key=lambda s: s.get("createTime") or "", reverse=True)
    return list(reversed(ordered[keep:]))


# --- operations -------------------------------------------------------------------------

def enable_encryption(apic: Apic, passphrase: str) -> str:
    """Set the AES passphrase -- ONLY if none is configured. Overwriting would
    make the secure fields of every earlier backup unrecoverable, and the
    APIC cannot say whether an existing key matches Vault's."""
    usable, _ = encryption_state(apic.attrs("uni/exportcryptkey", "pkiExportEncryptionKey"))
    if usable:
        return "already configured -- not touched (the APIC cannot confirm it matches Vault; overwriting would orphan earlier backups)"
    check_passphrase(passphrase)
    apic.post("uni/exportcryptkey", "pkiExportEncryptionKey", {"passphrase": passphrase, "strongEncryptionEnabled": "yes"})
    usable, reason = encryption_state(apic.attrs("uni/exportcryptkey", "pkiExportEncryptionKey"))
    if not usable:
        raise ApicError(f"passphrase posted but the APIC reports: {reason}")
    return "configured and enabled"


def _wait(apic: Apic, cls: str, fragment: str, started: str, what: str) -> dict:
    deadline = time.monotonic() + JOB_TIMEOUT
    job = None
    while time.monotonic() < deadline:
        time.sleep(5)
        job = newest_job_after(apic.class_under(cls, fragment), started)
        if job and job.get("operSt") in _DONE:
            break
    if not job:
        raise ApicError(f"no {what} job appeared within {JOB_TIMEOUT}s")
    if job.get("operSt") != "success":
        raise ApicError(f"{what} job ended '{job.get('operSt')}': {job.get('details') or job.get('lastStepDescr')}")
    return job


def _apic_time(apic: Apic) -> str:
    return apic.attrs("info", "topInfo").get("currentTime") or apic.get("class/topSystem.json")[0]["topSystem"]["attributes"]["currentTime"]


def create_backup(apic: Apic, reason: str, keep: int) -> dict:
    usable, why = encryption_state(apic.attrs("uni/exportcryptkey", "pkiExportEncryptionKey"))
    if not usable:
        raise ApicError(f"cannot back up: {why}")
    started = _apic_time(apic)
    apic.post(POLICY_DN, "configExportP", {
        "name": POLICY, "snapshot": "true", "format": "json", "includeSecureFields": "yes",
        "adminSt": "triggered", "descr": reason[:128]})
    job = _wait(apic, "configJob", POLICY, started, "backup")
    snapshots = apic.class_under("configSnapshot", POLICY)
    snapshot = next((s for s in snapshots if s.get("fileName") == job.get("fileName")), None)
    if snapshot is None:
        raise ApicError(f"backup job succeeded but no snapshot named {job.get('fileName')} exists")
    retired = []
    for old in to_retire(snapshots, keep):
        apic.post(old["dn"], "configSnapshot", {"retire": "true"})
        retired.append(old.get("fileName"))
    return {"snapshot_dn": snapshot["dn"], "file_name": snapshot.get("fileName"), "created": snapshot.get("createTime"),
            "policy": POLICY_DN, "reason": reason, "secure_fields_included": True, "job_details": job.get("details"),
            "retired": retired}


def list_backups(apic: Apic) -> list[dict]:
    snapshots = apic.class_under("configSnapshot", POLICY)
    return sorted(({"file_name": s.get("fileName"), "created": s.get("createTime"), "descr": s.get("descr")}
                   for s in snapshots), key=lambda s: s["created"] or "", reverse=True)


def restore_backup(apic: Apic, file_name: str, import_type: str) -> dict:
    if not any(s.get("fileName") == file_name for s in apic.class_under("configSnapshot", POLICY)):
        raise ApicError(f"no snapshot named {file_name} -- see --list")
    started = _apic_time(apic)
    apic.post(IMPORT_DN, "configImportP", {
        "name": IMPORT_POLICY, "snapshot": "true", "fileName": file_name, "importType": import_type,
        "importMode": "atomic", "adminSt": "triggered", "descr": f"restore {file_name}"})
    job = _wait(apic, "configJob", IMPORT_POLICY, started, "restore")
    return {"restored": file_name, "import_type": import_type, "job_details": job.get("details")}


def _apic_from_env() -> Apic:
    url = os.environ.get("TF_VAR_aci_url", "")
    username = os.environ.get("TF_VAR_aci_username", "")
    password = os.environ.get("TF_VAR_aci_password", "")
    if not all([url, username, password]):
        raise ApicError("TF_VAR_aci_url/username/password must be set -- source "
                        "platform/terraform/aci/scripts/load-vault-creds.sh first")
    return Apic(url, username, password, os.environ.get("TF_VAR_aci_insecure", "true").lower() != "false")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable-encryption", action="store_true", help="Set the AES passphrase from APIC_EXPORT_PASSPHRASE, once.")
    group.add_argument("--create", metavar="OUT", help="Take a snapshot and write its record to OUT (JSON).")
    group.add_argument("--list", action="store_true", help="List this platform's snapshots, newest first.")
    group.add_argument("--restore", metavar="FILE", help="Import a snapshot by file name.")
    parser.add_argument("--reason", default="manual", help="Recorded as the snapshot's description.")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"Snapshots to keep (default {DEFAULT_KEEP}).")
    parser.add_argument("--confirm", help="--restore: the same file name again.")
    parser.add_argument("--import-type", choices=("merge", "replace"), default="merge",
                        help="--restore: merge (default) adds back what is missing; replace makes the fabric match the snapshot.")
    args = parser.parse_args()

    if args.keep < 1:
        print("ERROR: --keep must be at least 1", file=sys.stderr)
        return 2
    if args.restore and args.confirm != args.restore:
        print("ERROR: --restore needs --confirm with the same file name -- a restore rewrites fabric configuration", file=sys.stderr)
        return 2
    try:
        apic = _apic_from_env()
        if args.enable_encryption:
            passphrase = os.environ.get("APIC_EXPORT_PASSPHRASE", "")
            if not passphrase:
                raise ApicError("APIC_EXPORT_PASSPHRASE is not set -- source load-vault-creds.sh")
            print(f"AES export encryption: {enable_encryption(apic, passphrase)}")
        elif args.create:
            record = create_backup(apic, args.reason, args.keep)
            with open(args.create, "w", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2)
            print(f"OK: snapshot {record['file_name']} taken ({record['reason']}); record in {args.create}"
                  + (f"; retired {len(record['retired'])} older" if record["retired"] else ""))
        elif args.list:
            for snap in list_backups(apic):
                print(f"{snap['created']}  {snap['file_name']}  {snap['descr'] or ''}")
        else:
            result = restore_backup(apic, args.restore, args.import_type)
            print(f"OK: {result['import_type']} restore of {result['restored']} completed")
    except ApicError as exc:
        # Fail closed: an apply without a backup is the risk this exists to remove.
        print(f"FAIL (fail-closed): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
