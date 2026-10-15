"""Unit tests for the pre-apply APIC configuration backup -- no live APIC.

The live behaviour (APIC 6.2 refusing every export without an AES
passphrase, a snapshot completing, retention deleting the oldest, a merge
restore bringing back a deleted tenant) is proven against the lab APIC; see
ADR-020. These tests pin the decisions the script makes: fail closed, never
overwrite an encryption key, keep the newest N, refuse an unconfirmed
restore.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "workflows" / "scripts"))

import apic_backup  # noqa: E402
from apic_backup import ApicError  # noqa: E402

CONFIGURED = {"keyConfigured": "yes", "strongEncryptionEnabled": "yes"}


class FakeApic:
    """Just enough of apic_backup.Apic: attrs / post / class_under, recording posts."""

    def __init__(self, crypt=None, jobs=None, snapshots=None, time="2026-10-17T10:00:00.000+00:00"):
        self.crypt = dict(crypt or {})
        self.jobs = list(jobs or [])
        self.snapshots = list(snapshots or [])
        self.time = time
        self.posts: list[tuple[str, str, dict]] = []

    def attrs(self, dn, cls):
        if cls == "pkiExportEncryptionKey":
            return self.crypt
        if cls == "topInfo":
            return {"currentTime": self.time}
        return {}

    def get(self, path):
        return []

    def post(self, dn, cls, attributes):
        self.posts.append((dn, cls, attributes))
        if cls == "pkiExportEncryptionKey":
            self.crypt = {"keyConfigured": "yes", "strongEncryptionEnabled": attributes.get("strongEncryptionEnabled")}

    def class_under(self, cls, fragment):
        return self.jobs if cls == "configJob" else self.snapshots


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(apic_backup.time, "sleep", lambda s: None)


# --- encryption -------------------------------------------------------------------------

@pytest.mark.parametrize("crypt,usable", [
    ({}, False),
    ({"keyConfigured": "no", "strongEncryptionEnabled": "no"}, False),
    ({"keyConfigured": "yes", "strongEncryptionEnabled": "no"}, False),
    (CONFIGURED, True),
])
def test_encryption_state(crypt, usable):
    assert apic_backup.encryption_state(crypt)[0] is usable


def test_enable_encryption_never_overwrites_an_existing_key():
    """The APIC cannot say whether its key matches Vault's, and replacing it
    would orphan the secure fields of every earlier backup."""
    apic = FakeApic(crypt=CONFIGURED)
    assert "not touched" in apic_backup.enable_encryption(apic, "x" * 32)
    assert apic.posts == []


def test_enable_encryption_sets_the_key_when_none_exists():
    apic = FakeApic(crypt={"keyConfigured": "no"})
    assert apic_backup.enable_encryption(apic, "p" * 32) == "configured and enabled"
    assert apic.posts == [("uni/exportcryptkey", "pkiExportEncryptionKey",
                           {"passphrase": "p" * 32, "strongEncryptionEnabled": "yes"})]


@pytest.mark.parametrize("length", [15, 33])
def test_passphrase_length_is_the_apics(length):
    with pytest.raises(ApicError, match="16-32 characters"):
        apic_backup.enable_encryption(FakeApic(), "p" * length)


# --- backup --------------------------------------------------------------------------------

def test_backup_fails_closed_without_encryption():
    """APIC 6.2 refuses every export without the AES key -- say so before
    trying, so the apply does not run with no backup."""
    apic = FakeApic(crypt={"keyConfigured": "no"})
    with pytest.raises(ApicError, match="cannot back up: no AES encryption passphrase"):
        apic_backup.create_backup(apic, "pipeline 1", keep=20)
    assert apic.posts == []


def _job(state, file_name="f-new.tar.gz", at="2026-10-17T10:00:05.000+00:00"):
    return {"operSt": state, "fileName": file_name, "executeTime": at, "details": state}


def test_backup_records_the_snapshot_its_job_produced():
    snaps = [{"dn": "snap-new", "fileName": "f-new.tar.gz", "createTime": "2026-10-17T10:00:06"}]
    apic = FakeApic(crypt=CONFIGURED, jobs=[_job("success", "f-old.tar.gz", "2026-10-16T09:00:00"), _job("success")],
                    snapshots=snaps)
    record = apic_backup.create_backup(apic, "pipeline 7 abc123", keep=20)
    assert record["file_name"] == "f-new.tar.gz" and record["snapshot_dn"] == "snap-new"
    assert record["secure_fields_included"] is True and record["retired"] == []
    dn, cls, attrs = apic.posts[0]
    assert (dn, cls) == (apic_backup.POLICY_DN, "configExportP")
    assert attrs["snapshot"] == "true" and attrs["includeSecureFields"] == "yes" and attrs["adminSt"] == "triggered"


def test_a_failed_job_fails_the_backup():
    apic = FakeApic(crypt=CONFIGURED, jobs=[_job("failed")])
    with pytest.raises(ApicError, match="backup job ended 'failed'"):
        apic_backup.create_backup(apic, "x", keep=20)


def test_a_job_that_names_a_missing_snapshot_fails_the_backup():
    apic = FakeApic(crypt=CONFIGURED, jobs=[_job("success")], snapshots=[])
    with pytest.raises(ApicError, match="no snapshot named f-new.tar.gz"):
        apic_backup.create_backup(apic, "x", keep=20)


def test_newest_job_after_ignores_jobs_from_before_the_trigger():
    jobs = [_job("success", "old", "2026-10-16T00:00:00"), _job("running", "mine", "2026-10-17T10:00:01")]
    assert apic_backup.newest_job_after(jobs, "2026-10-17T10:00:00")["fileName"] == "mine"
    assert apic_backup.newest_job_after(jobs[:1], "2026-10-17T10:00:00") is None


# --- retention ---------------------------------------------------------------------------------

def test_retention_keeps_the_newest_and_retires_the_rest_oldest_first():
    snaps = [{"fileName": f"s{i}", "createTime": f"2026-10-1{i}"} for i in range(1, 6)]
    assert [s["fileName"] for s in apic_backup.to_retire(snaps, keep=2)] == ["s1", "s2", "s3"]
    assert apic_backup.to_retire(snaps, keep=10) == []


def test_backup_retires_beyond_keep():
    snaps = [{"dn": f"d{i}", "fileName": f"s{i}", "createTime": f"2026-10-1{i}"} for i in range(1, 4)]
    snaps.append({"dn": "d-new", "fileName": "f-new.tar.gz", "createTime": "2026-10-17T10:00:06"})
    apic = FakeApic(crypt=CONFIGURED, jobs=[_job("success")], snapshots=snaps)
    record = apic_backup.create_backup(apic, "x", keep=2)
    assert record["retired"] == ["s1", "s2"]
    assert [(dn, a) for dn, cls, a in apic.posts if cls == "configSnapshot"] == [("d1", {"retire": "true"}), ("d2", {"retire": "true"})]


# --- restore ---------------------------------------------------------------------------------------

def test_restore_refuses_an_unknown_snapshot():
    with pytest.raises(ApicError, match="no snapshot named nope"):
        apic_backup.restore_backup(FakeApic(snapshots=[{"fileName": "f1"}]), "nope", "merge")


def test_restore_triggers_an_atomic_import_of_the_snapshot():
    apic = FakeApic(snapshots=[{"fileName": "f1"}], jobs=[_job("success", "f1")])
    assert apic_backup.restore_backup(apic, "f1", "replace")["import_type"] == "replace"
    dn, cls, attrs = apic.posts[0]
    assert (dn, cls) == (apic_backup.IMPORT_DN, "configImportP")
    assert attrs["fileName"] == "f1" and attrs["snapshot"] == "true" and attrs["importMode"] == "atomic"


def test_main_refuses_an_unconfirmed_restore_before_touching_the_apic(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["apic_backup.py", "--restore", "f1"])
    monkeypatch.setattr(apic_backup, "_apic_from_env", lambda: pytest.fail("must not contact the APIC"))
    assert apic_backup.main() == 2
    assert "--confirm" in capsys.readouterr().err


def test_main_fails_closed_when_the_apic_is_unreachable(monkeypatch, capsys, tmp_path):
    def unreachable():
        raise ApicError("could not reach APIC")
    monkeypatch.setattr(sys, "argv", ["apic_backup.py", "--create", str(tmp_path / "b.json")])
    monkeypatch.setattr(apic_backup, "_apic_from_env", unreachable)
    assert apic_backup.main() == 1
    assert "fail-closed" in capsys.readouterr().err
