"""Local synthetic-data profile with credentials independent of production."""

import os
from getpass import getuser

from django.core.exceptions import ImproperlyConfigured

from .settings_test import *  # noqa: F401, F403

_ai_test_host = os.environ.get("CHAT_AI_TEST_DB_HOST", "localhost")
if _ai_test_host not in {"localhost", "127.0.0.1", "::1", ""} and not os.path.isabs(
    _ai_test_host
):
    raise ImproperlyConfigured(
        "CHAT_AI_TEST_DB_HOST must use a local host or Unix socket."
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        # These names are also checked by the synthetic-data seeding command.
        "NAME": "chat_ai_facturation_dev",
        "USER": os.environ.get("CHAT_AI_TEST_DB_USER", getuser()),
        "PASSWORD": os.environ.get("CHAT_AI_TEST_DB_PASSWORD", ""),
        "HOST": _ai_test_host,
        "PORT": os.environ.get("CHAT_AI_TEST_DB_PORT", "5432"),
        "TEST": {"NAME": "test_chat_ai_facturation"},
    }
}
CHAT_AI_ASSISTANT_ENABLED = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
