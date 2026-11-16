"""Prepare durable work on save; no model requests run in a web transaction."""

from django.db import transaction
from django.db.models.signals import pre_save, post_save

from .pdf_translation import (
    SOURCE_MODELS,
    DEPENDENCY_MODELS,
    prepare_instance,
    source_model,
    translation_enabled,
)


def remember_changes(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or not translation_enabled():
        return
    fields = {**SOURCE_MODELS, **DEPENDENCY_MODELS}[sender._meta.label]
    field_names = {field.removesuffix("_id") for field in fields} | set(fields)
    if update_fields is not None and not set(update_fields).intersection(field_names):
        instance._pdf_text_changed = False
        return
    previous = (
        sender.objects.filter(pk=instance.pk).values(*fields).first()
        if instance.pk else None
    )
    instance._pdf_text_changed = previous is None or any(
        previous[field] != getattr(instance, field) for field in fields
    )


def prepare_changes(sender, instance, raw=False, created=False, **kwargs):
    if not raw and translation_enabled() and getattr(instance, "_pdf_text_changed", False):
        if sender._meta.label in SOURCE_MODELS:
            prepare_instance(instance)
        elif not created:
            from .tasks import backfill_pdf_translations
            from .pdf_translation import logger

            company_id = (
                instance.pk
                if sender._meta.label == "company.Company"
                else instance.company_id
            )
            if company_id:
                def enqueue():
                    try:
                        backfill_pdf_translations.delay(company_id=company_id)
                    except Exception:
                        logger.exception("Could not dispatch dependent PDF translation backfill")

                transaction.on_commit(enqueue, robust=True)


def connect():
    for label in {**SOURCE_MODELS, **DEPENDENCY_MODELS}:
        model = source_model(label)
        pre_save.connect(
            remember_changes, sender=model, dispatch_uid=f"pdf_translation_pre_{label}"
        )
        post_save.connect(
            prepare_changes, sender=model, dispatch_uid=f"pdf_translation_post_{label}"
        )
