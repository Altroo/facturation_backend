"""
Test-specific settings. Inherits from the main settings module and overrides
only what is necessary for the test environment.
"""

from facturation_backend.settings import *  # noqa: F401, F403

# -- Overrides ---------------------------------------------------------------

DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Disable simple_history in tests for speed
INSTALLED_APPS = [
    app for app in INSTALLED_APPS if app != "simple_history"  # noqa: F405
]
MIDDLEWARE = [
    mw for mw in MIDDLEWARE if mw != "simple_history.middleware.HistoryRequestMiddleware"  # noqa: F405
]

# Use in-memory email backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Celery eager mode so tasks run synchronously in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Use in-memory channel layer (no Redis dependency for tests)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Static CORS for tests
CORS_ORIGIN_WHITELIST = ("http://localhost:3000",)

ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http"
