"""Configuration for the isolated laptop Nautobot instance."""
import os
import sys

from nautobot.core.settings import *  # noqa: F403
from nautobot.core.settings_funcs import is_truthy


def _env(key, default=""):
    return os.getenv(key, default)


SECRET_KEY = _env("NAUTOBOT_SECRET_KEY")
ALLOWED_HOSTS = _env("NAUTOBOT_ALLOWED_HOSTS", "localhost 127.0.0.1").split()
DEBUG = is_truthy(_env("NAUTOBOT_DEBUG", "False"))
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

DATABASES = {
    "default": {
        "HOST": _env("NAUTOBOT_DB_HOST", "isolated-postgres"),
        "PORT": _env("NAUTOBOT_DB_PORT", "5432"),
        "NAME": _env("NAUTOBOT_DB_NAME", "nautobot_isolated"),
        "USER": _env("NAUTOBOT_DB_USER", "nautobot"),
        "PASSWORD": _env("NAUTOBOT_DB_PASSWORD"),
        "CONN_MAX_AGE": int(_env("NAUTOBOT_DB_TIMEOUT", "60")),
        "ENGINE": _env("NAUTOBOT_DB_ENGINE", "django.db.backends.postgresql"),
    }
}

_redis_host = _env("NAUTOBOT_REDIS_HOST", "isolated-redis")
_redis_port = _env("NAUTOBOT_REDIS_PORT", "6379")
_redis_pass = _env("NAUTOBOT_REDIS_PASSWORD")
_redis_url = f"redis://:{_redis_pass}@{_redis_host}:{_redis_port}"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{_redis_url}/1",
        "TIMEOUT": 300,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
CELERY_BROKER_URL = f"{_redis_url}/0"
CELERY_RESULT_BACKEND = f"{_redis_url}/0"

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "nautobot": {"handlers": ["console"], "level": LOG_LEVEL},
    },
}

PLUGINS = ["nautobot_ssot"]
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_aci": True,
        "aci_tag": "ACI",
        "aci_tag_color": "0047AB",
        "aci_tag_up": "UP",
        "aci_tag_up_color": "008000",
        "aci_tag_down": "DOWN",
        "aci_tag_down_color": "FF3333",
        "aci_manufacturer_name": "Cisco",
        "aci_ignore_tenants": ["common", "mgmt", "infra"],
        "aci_comments": "Created by ACI SSoT Integration",
        "aci_apics": {key: value for key, value in os.environ.items() if "APIC" in key},
    }
}

METRICS_ENABLED = False
