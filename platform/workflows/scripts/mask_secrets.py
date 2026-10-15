"""Run a command and mask secret values in everything it prints.

Usage:
    mask_secrets.py --env TF_VAR_snmp_community_strings [--env ...] -- terraform apply tfplan

Why (2026-10-13): an SNMP community string is part of the APIC object's DN,
and the provider uses that DN as the Terraform resource ID. Terraform prints
resource IDs on every refresh, create and destroy
("Creation complete after 1s [id=uni/fabric/snmppol-default/community-<string>]")
-- `sensitive = true` hides the value in plan diffs but not there. In CI that
line lands in the GitLab job log. Measured against the lab APIC: one
occurrence per apply.

Each --env names an environment variable holding either a JSON object (every
value is a secret) or a plain string. Values shorter than 4 characters are
not masked -- replacing them would garble ordinary output and they are not
credible secrets. The command's exit code is passed through unchanged, so a
failing terraform still fails the job.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

MASK = "****"
MIN_LENGTH = 4


def secrets_from_env(names: list[str], environ=None) -> list[str]:
    # os.environ itself, NOT dict(os.environ): on Windows Python upper-cases
    # every key in os.environ, and only os.environ's own lookup is
    # case-insensitive -- a dict copy silently found nothing and masked nothing
    # (measured 2026-10-13, three community strings printed in clear).
    environ = environ if environ is not None else os.environ
    values: list[str] = []
    for name in names:
        raw = environ.get(name, "")
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if isinstance(parsed, dict):
            values.extend(str(v) for v in parsed.values())
        else:
            values.append(str(parsed))
    # longest first, so a secret containing another is masked whole
    return sorted({v for v in values if len(v) >= MIN_LENGTH}, key=len, reverse=True)


def mask(line: str, secrets: list[str]) -> str:
    for secret in secrets:
        line = line.replace(secret, MASK)
    return line


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("usage: mask_secrets.py --env NAME [--env NAME ...] -- command ...", file=sys.stderr)
        return 2
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]
    names = [options[i + 1] for i, opt in enumerate(options) if opt == "--env" and i + 1 < len(options)]
    if not command:
        print("mask_secrets.py: no command given", file=sys.stderr)
        return 2
    secrets = secrets_from_env(names)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(mask(line, secrets))
        sys.stdout.flush()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
