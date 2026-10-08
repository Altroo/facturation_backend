"""Periodic maintenance for assistant-owned data; never invokes inference."""

from celery import shared_task
from django.core.management import call_command


@shared_task(name="chat_ai.purge_history", ignore_result=True)
def purge_history():
    # Retained conversations still expire when the assistant UI is disabled.
    # The command preserves confirmed mutation audits and their actor history.
    call_command("purge_ai_history")
