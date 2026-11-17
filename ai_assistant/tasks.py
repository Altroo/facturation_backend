"""Bounded background translation, durable retries, and resumable backfilling."""

from datetime import timedelta
import math
from uuid import uuid4

from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from facturation_backend.celery_conf import app
from .client import AiAssistantClient
from rest_framework.exceptions import Throttled
from .exceptions import InvalidModelResponse
from .models import PdfTextTranslation
from .pdf_translation import (
    LANGUAGES,
    ENGINE_REVISION,
    validate_saved_translation,
    SOURCE_MODELS,
    company_for,
    ensure_sources,
    own_sources,
    source_model,
    translation_enabled,
)

logger = get_task_logger(__name__)


@app.task(
    name="ai_assistant.translate_pending_pdf_texts",
    ignore_result=True,
    queue="pdf_translations",
)
def translate_pending_pdf_texts():
    if not translation_enabled():
        return
    now = timezone.now()
    eligible = eligible_work(now)
    token = uuid4()
    with transaction.atomic():
        first = (
            PdfTextTranslation.objects.filter(eligible)
            .order_by("priority", "pk")
            .values("language", "company_id", "priority")
            .first()
        )
        if first is None:
            return
        candidates = list(
            PdfTextTranslation.objects.select_for_update(skip_locked=True)
            .filter(
                eligible,
                language=first["language"],
                company_id=first["company_id"],
                priority=first["priority"],
            )
            .order_by("priority", "pk")[:15]
        )
        rows = []
        size = 0
        for row in candidates:
            if rows and size + len(row.source_text) > 6000:
                break
            rows.append(row)
            size += len(row.source_text)
        if not rows:
            return
        ids = [row.pk for row in rows]
        lease_seconds = max(
            600,
            math.ceil(size / 4000) * (settings.AI_ASSISTANT_TIMEOUT_SECONDS + 5) + 60,
        )
        PdfTextTranslation.objects.filter(pk__in=ids).update(
            status="processing",
            lease_until=now + timedelta(seconds=lease_seconds),
            lease_token=token,
        )
    try:
        translations = AiAssistantClient().translate_many(
            [row.source_text for row in rows],
            target_language=first["language"],
            protected_terms=list(
                dict.fromkeys(term for row in rows for term in row.protected_terms)
            ),
            context="invoice_pdf",
            retry_rate_limit=False,
            background=first["priority"] >= 100,
        )
        for row in rows:
            text = translations.get(row.source_text)
            validate_saved_translation(row, text)
        with transaction.atomic():
            for row in rows:
                PdfTextTranslation.objects.filter(pk=row.pk, lease_token=token).update(
                    status="ready",
                    engine_revision=ENGINE_REVISION,
                    translated_text=translations[row.source_text],
                    lease_until=None,
                    lease_token=None,
                    last_error="",
                    updated_at=timezone.now(),
                )
    except Exception as exc:
        if isinstance(exc, InvalidModelResponse) and len(rows) > 1:
            # A bad legacy field must not fail otherwise valid fields in its batch.
            for row in rows:
                try:
                    translated = (
                        AiAssistantClient()
                        .translate_many(
                            [row.source_text],
                            target_language=row.language,
                            protected_terms=row.protected_terms,
                            context="invoice_pdf",
                            retry_rate_limit=False,
                            background=row.priority >= 100,
                        )
                        .get(row.source_text)
                    )
                    validate_saved_translation(row, translated)
                    PdfTextTranslation.objects.filter(
                        pk=row.pk, lease_token=token
                    ).update(
                        status="ready",
                        engine_revision=ENGINE_REVISION,
                        translated_text=translated,
                        lease_until=None,
                        lease_token=None,
                        last_error="",
                        updated_at=timezone.now(),
                    )
                except Exception as single_error:
                    record_failure(row, token, single_error)
        else:
            for row in rows:
                record_failure(row, token, exc)
    # Beat recovers pending/expired work even if this follow-up cannot be sent.
    if PdfTextTranslation.objects.filter(eligible_work(timezone.now())).exists():
        translate_pending_pdf_texts.apply_async(countdown=1)


def eligible_work(now):
    eligible = Q(status="pending", available_at__lte=now) | Q(
        status="processing", lease_until__lt=now
    )
    # Skip the whole tier without rewriting the deadline for every queued batch.
    # Retrying locally must never extend a gateway-imposed wait.
    if cache.get(quota_key(100), 0) > now.timestamp():
        eligible &= ~Q(priority__gte=100)
    if cache.get(quota_key(0), 0) > now.timestamp():
        eligible &= ~Q(priority__lt=100)
    return eligible


def quota_key(priority):
    return "pdf-translation-quota:" + (
        "background" if priority >= 100 else "foreground"
    )


def record_failure(row, token, exc):
    # Retry asynchronously. A slow/unavailable engine never delays a save or PDF.
    if isinstance(exc, Throttled):
        wait = max(1, float(exc.wait or 60))
        cache.set(
            quota_key(row.priority),
            timezone.now().timestamp() + wait,
            math.ceil(wait) + 1,
        )
        PdfTextTranslation.objects.filter(pk=row.pk, lease_token=token).update(
            status="pending",
            available_at=timezone.now()
            + timedelta(seconds=max(1, float(exc.wait or 60))),
            lease_until=None,
            lease_token=None,
            last_error="ai_rate_limited",
            updated_at=timezone.now(),
        )
        return
    error_code = str(getattr(exc, "default_code", type(exc).__name__))[:80]
    attempts = row.attempts + 1
    delay = max(
        float(getattr(exc, "wait", 0) or 0),
        min(3600, 30 * 2 ** min(attempts - 1, 7)),
    )
    changed = PdfTextTranslation.objects.filter(pk=row.pk, lease_token=token).update(
        status="failed" if attempts >= 6 else "pending",
        attempts=attempts,
        available_at=timezone.now() + timedelta(seconds=delay),
        lease_until=None,
        lease_token=None,
        last_error=error_code,
        updated_at=timezone.now(),
    )
    if changed:
        logger.warning(
            "PDF translation failed: row_id=%s language=%s attempt=%s code=%s",
            row.pk,
            row.language,
            attempts,
            error_code,
        )


@app.task(
    name="ai_assistant.backfill_pdf_translations",
    queue="celery",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def backfill_pdf_translations(
    company_id=None, languages=None, model_index=0, after_pk=0, batch_size=100
):
    """Each invocation scans at most one chunk; repeating a run reuses ready rows."""
    if not translation_enabled():
        return {"disabled": True}
    languages = tuple(languages or LANGUAGES)
    if not set(languages).issubset(LANGUAGES) or not 1 <= batch_size <= 500:
        raise ValueError("Invalid PDF backfill options")
    labels = list(SOURCE_MODELS)
    if model_index >= len(labels):
        return {"complete": True}
    model = source_model(labels[model_index])
    queryset = model.objects.filter(pk__gt=after_pk).order_by("pk")
    if labels[model_index] == "article.Article":
        queryset = queryset.select_related("company", "marque", "unite")
    elif labels[model_index] == "reglement.Reglement":
        queryset = queryset.select_related(
            "facture_client__company", "facture_client__client", "mode_reglement"
        )
    elif labels[model_index].startswith("parameter."):
        queryset = queryset.select_related("company")
    else:
        queryset = queryset.select_related("company", "client")
    if company_id:
        company_field = (
            "facture_client__company_id"
            if labels[model_index] == "reglement.Reglement"
            else "company_id"
        )
        queryset = queryset.filter(**{company_field: company_id})
    instances = list(queryset[:batch_size])
    for instance in instances:
        company = company_for(instance)
        if company:
            ensure_sources(
                company.pk,
                own_sources(instance, company),
                languages,
                dispatch=False,
                priority=100,
            )
    from .pdf_translation import dispatch_pending

    if instances:
        dispatch_pending()
    next_index, next_pk = (
        (model_index, instances[-1].pk)
        if len(instances) == batch_size
        else (model_index + 1, 0)
    )
    if next_index < len(labels):
        backfill_pdf_translations.apply_async(
            kwargs={
                "company_id": company_id,
                "languages": list(languages),
                "model_index": next_index,
                "after_pk": next_pk,
                "batch_size": batch_size,
            },
            countdown=1,
        )
    return {
        "model": labels[model_index],
        "scanned": len(instances),
        "after_pk": next_pk,
        "next_model_index": next_index,
    }
