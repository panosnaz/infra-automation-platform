"""mask_secrets.py keeps credentials out of CI job logs (2026-10-13).

An SNMP community string is part of its APIC DN, which Terraform prints as
the resource ID on every refresh/create/destroy -- `sensitive` does not hide
it there. Measured: one occurrence per apply against the lab APIC.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "workflows" / "scripts"))

import mask_secrets  # noqa: E402


def test_values_of_a_json_map_are_all_secrets():
    env = {"TF_VAR_snmp_community_strings": '{"ro": "s3cret-ro", "rw": "s3cret-rw"}'}
    assert set(mask_secrets.secrets_from_env(["TF_VAR_snmp_community_strings"], env)) == {"s3cret-ro", "s3cret-rw"}


def test_a_plain_string_variable_is_a_secret_and_missing_ones_are_ignored():
    env = {"X": "plainsecret"}
    assert mask_secrets.secrets_from_env(["X", "NOT_SET"], env) == ["plainsecret"]


def test_the_terraform_id_line_is_masked():
    line = 'aci_snmp_community.this["ro"]: Creation complete after 1s [id=uni/fabric/snmppol-default/community-s3cret-ro]\n'
    assert mask_secrets.mask(line, ["s3cret-ro"]) == \
        'aci_snmp_community.this["ro"]: Creation complete after 1s [id=uni/fabric/snmppol-default/community-****]\n'


def test_short_values_are_not_masked():
    """Masking 'a' would garble every line; a 1-3 character value is not a credible secret."""
    assert mask_secrets.secrets_from_env(["X"], {"X": '{"k": "abc"}'}) == []


def test_a_secret_containing_another_is_masked_whole():
    secrets = mask_secrets.secrets_from_env(["X"], {"X": '{"a": "public", "b": "public-extra"}'})
    assert mask_secrets.mask("community-public-extra", secrets) == "community-****"


def test_the_exit_code_passes_through(tmp_path, monkeypatch, capsys):
    """A failing terraform must still fail the CI job."""
    monkeypatch.setenv("S", "topsecret")
    script = tmp_path / "p.py"
    script.write_text("print('id=community-topsecret'); raise SystemExit(3)")
    rc = mask_secrets.main(["--env", "S", "--", sys.executable, str(script)])
    assert rc == 3
    out = capsys.readouterr().out
    assert "topsecret" not in out and "community-****" in out


def test_reads_the_process_environment_case_insensitively_where_the_os_does(monkeypatch):
    """Regression (2026-10-13): a dict copy of os.environ has upper-cased keys
    on Windows, so a mixed-case name found nothing and nothing was masked."""
    monkeypatch.setenv("TF_VAR_mask_probe", '{"k": "probe-secret"}')
    assert mask_secrets.secrets_from_env(["TF_VAR_mask_probe"]) == ["probe-secret"]
