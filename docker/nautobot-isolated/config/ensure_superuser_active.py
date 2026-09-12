"""Re-enable the Nautobot superuser account on stack start.

The base image entrypoint already restores the superuser's password from
NAUTOBOT_SUPERUSER_PASSWORD on every container start, but it never touches
is_active/is_staff/is_superuser. A deactivated admin therefore stays locked
out across every restart with no way back in short of manual DB surgery --
verified against this image. This closes only that gap; the password and API
token remain owned solely by the entrypoint.
"""
import os
import sys

import nautobot

nautobot.setup(config_path=os.environ.get("NAUTOBOT_CONFIG", "/opt/nautobot/nautobot_config.py"))

from django.contrib.auth import get_user_model  # noqa: E402

if os.environ.get("NAUTOBOT_CREATE_SUPERUSER", "").strip().lower() != "true":
    print("[superuser] NAUTOBOT_CREATE_SUPERUSER is not 'true' -- skipping")
    sys.exit(0)

username = os.environ.get("NAUTOBOT_SUPERUSER_NAME", "").strip()
if not username:
    print("[superuser] NAUTOBOT_SUPERUSER_NAME is unset -- skipping", file=sys.stderr)
    sys.exit(0)

user = get_user_model().objects.filter(username=username).first()
if user is None:
    print(f"[superuser] '{username}' does not exist yet -- entrypoint will create it")
    sys.exit(0)

restored = [f for f in ("is_active", "is_staff", "is_superuser") if not getattr(user, f)]
if restored:
    for field in restored:
        setattr(user, field, True)
    user.save(update_fields=restored)
    print(f"[superuser] '{username}': restored {', '.join(restored)}")
else:
    print(f"[superuser] '{username}': account flags already correct")
