from __future__ import absolute_import, unicode_literals

from os import environ

from celery import Celery
from django.conf import settings

# cmd line to run in terminal
# celery --app=facturation_backend.celery_conf worker --loglevel=debug --concurrency=4 -E -P gevent
environ.setdefault("DJANGO_SETTINGS_MODULE", "facturation_backend.settings")

app = Celery("ai_workx_backend", broker=settings.CELERY_BROKER_URL)
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.timezone = settings.TIME_ZONE
app.conf.setdefault("worker_cancel_long_running_tasks_on_connection_loss", True)
app.conf.task_serializer = "pickle"
app.conf.result_serializer = "pickle"
app.conf.accept_content = ["application/json", "application/x-python-serialize"]
app.autodiscover_tasks(
    packages=[
        "account.tasks",
    ]
)
