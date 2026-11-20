from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import Throttled

from ai_assistant.client import AiAssistantClient
from ai_assistant.exceptions import InvalidModelResponse, ModelTimeout, ModelUnavailable, PdfTranslationFailed, PdfTranslationPending
from ai_assistant.models import PdfTextTranslation
from ai_assistant.offline_translation import OfflineTranslationClient
from ai_assistant.pdf_translation import ensure_sources, load_pdf_translations, own_sources, pdf_sources, source
from ai_assistant.tasks import backfill_pdf_translations, translate_pending_pdf_texts
from article.models import Article
from client.models import Client
from company.models import Company
from devi.models import Devi, DeviLine
from parameter.models import Unite, ModePaiement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def background_settings(settings):
    cache.clear()
    settings.AI_PDF_TRANSLATION_ENABLED = True
    settings.AI_ASSISTANT_TIMEOUT_SECONDS = 185
    settings.CELERY_TASK_ALWAYS_EAGER = False
    with patch("ai_assistant.pdf_translation.dispatch_pending") as dispatch, patch.object(translate_pending_pdf_texts, "apply_async") as followup:
        yield dispatch, followup


@pytest.fixture
def company():
    return Company.objects.create(raison_sociale="CASA DI LUSSO QA", ICE="PDF-CACHE-QA")


@pytest.fixture
def document(company):
    client = Client.objects.create(company=company, code_client="PDF-QA", client_type="PM", raison_sociale="Client QA")
    return Devi.objects.create(company=company, client=client, numero_devis="D-QA", date_devis=date.today(), remarque="Livrer avant midi")


def ready_rows(language="nl"):
    for row in PdfTextTranslation.objects.filter(language=language):
        row.status = "ready"
        row.translated_text = "NL " + row.source_text
        row.save()


def test_save_prepares_all_languages_without_model_calls(company, django_capture_on_commit_callbacks, background_settings):
    with patch.object(AiAssistantClient, "translate_many") as model, django_capture_on_commit_callbacks(execute=True):
        article = Article.objects.create(company=company, reference="A-123", designation="Chaise en bois")
    assert set(PdfTextTranslation.objects.values_list("language", flat=True)) == {"fr", "en", "nl"}
    assert PdfTextTranslation.objects.filter(status="pending").count() == 3
    model.assert_not_called()
    background_settings[0].assert_called_once()
    assert article.designation == "Chaise en bois"


def test_price_change_does_not_invalidate_or_queue_translation(company, django_capture_on_commit_callbacks, background_settings):
    article = Article.objects.create(company=company, reference="A-123", designation="Chaise en bois")
    background_settings[0].reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        article.prix_vente = 123
        article.save(update_fields=["prix_vente"])
    background_settings[0].assert_not_called()
    assert PdfTextTranslation.objects.count() == 3


def test_changed_text_never_reuses_old_translation(company, document):
    ready_rows()
    assert load_pdf_translations(document, company, "nl")[document.remarque] == "NL Livrer avant midi"
    document.remarque = "Livrer après midi"
    document.save(update_fields=["remarque"])
    with pytest.raises(PdfTranslationPending):
        load_pdf_translations(document, company, "nl")
    assert PdfTextTranslation.objects.filter(source_text="Livrer avant midi", status="ready").count() == 1
    ready_rows()
    assert load_pdf_translations(document, company, "nl") == {"Livrer après midi": "NL Livrer après midi"}


def test_sources_deduplicate_articles_but_protect_names_and_references(company):
    a = Article.objects.create(company=company, reference="A-123", designation="Chaise en bois")
    b = Article.objects.create(company=company, reference="B-456", designation="Chaise en bois")
    assert own_sources(a, company) == own_sources(b, company)
    assert PdfTextTranslation.objects.count() == 3
    spec = source("Livraison Client QA REF-123", ["Client QA", "REF-123", "Irrelevant"])
    assert set(spec.protected_terms) == {"Client QA", "REF-123"}
    assert spec.fingerprint != source(spec.text).fingerprint


def test_pdf_reads_persisted_text_without_ai_and_preserves_original(company, document):
    unit = Unite.objects.create(company=company, nom="Pièce")
    article = Article.objects.create(company=company, reference="A-123", designation="Chaise en bois\nFinition naturelle", unite=unit)
    DeviLine.objects.create(devis=document, article=article, quantity=1, prix_vente=100, prix_achat=80)
    ready_rows()
    with patch.object(AiAssistantClient, "translate_many") as model:
        result = load_pdf_translations(document, company, "nl")
    assert result["Pièce"] == "NL Pièce"
    assert result[article.designation] == "NL " + article.designation
    model.assert_not_called()
    article.refresh_from_db()
    assert article.designation == "Chaise en bois\nFinition naturelle"


def test_missing_rows_queue_work_but_never_translate_in_pdf(company, document):
    PdfTextTranslation.objects.all().delete()
    with patch.object(AiAssistantClient, "translate_many") as model:
        with pytest.raises(PdfTranslationPending) as failure:
            load_pdf_translations(document, company, "nl")
    assert failure.value.detail["code"] == "pdf_translation_pending"
    assert PdfTextTranslation.objects.filter(status="pending").count() == 1
    model.assert_not_called()


def test_requested_pdf_takes_priority_over_existing_backfill(company, document):
    PdfTextTranslation.objects.update(priority=100)
    with pytest.raises(PdfTranslationPending):
        load_pdf_translations(document, company, "nl")
    assert PdfTextTranslation.objects.get(language="nl").priority == 0
    with patch.object(AiAssistantClient, "translate_many", return_value={document.remarque: "Voor de middag leveren"}) as model:
        translate_pending_pdf_texts()
    assert model.call_args.kwargs["target_language"] == "nl"


def test_failed_translation_is_explicit_and_company_isolated(company, document):
    other = Company.objects.create(raison_sociale="Other", ICE="OTHER-PDF-QA")
    spec = source(document.remarque)
    ensure_sources(other.pk, [spec])
    PdfTextTranslation.objects.filter(company=other).update(status="ready", translated_text="Private other translation")
    PdfTextTranslation.objects.filter(company=company, language="nl").update(status="failed")
    with pytest.raises(PdfTranslationFailed):
        load_pdf_translations(document, company, "nl")


def test_worker_claims_one_company_and_language_and_saves_result(company):
    ensure_sources(company.pk, [source("Chaise en bois"), source("Livrer avant midi")])
    with patch.object(AiAssistantClient, "translate_many", return_value={"Chaise en bois": "Houten stoel", "Livrer avant midi": "Voor de middag leveren"}) as model:
        translate_pending_pdf_texts()
    assert PdfTextTranslation.objects.filter(language="fr", status="ready").count() == 2
    assert PdfTextTranslation.objects.filter(status="pending").count() == 4
    assert model.call_args.kwargs["retry_rate_limit"] is False
    assert model.call_args.kwargs["target_language"] == "fr"


def test_worker_failure_retries_later_without_sleeping(company, caplog):
    ensure_sources(company.pk, [source("Chaise en bois")], ["nl"])
    with (
        patch.object(AiAssistantClient, "translate_many", side_effect=ModelUnavailable),
        patch.object(OfflineTranslationClient, "translate_many", side_effect=ModelUnavailable),
    ):
        translate_pending_pdf_texts()
    row = PdfTextTranslation.objects.get()
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.available_at > timezone.now()
    assert row.last_error == "ai_model_unavailable"
    assert not row.lease_token
    assert f"row_id={row.pk}" in caplog.text
    assert "ai_model_unavailable" in caplog.text
    assert "Chaise en bois" not in caplog.text


def test_worker_terminal_failure_and_expired_lease_recovery(company):
    ensure_sources(company.pk, [source("Chaise en bois")], ["nl"])
    PdfTextTranslation.objects.update(status="processing", lease_until=timezone.now() - timedelta(seconds=1), attempts=5, lease_token=uuid4())
    with (
        patch.object(AiAssistantClient, "translate_many", side_effect=ModelUnavailable),
        patch.object(OfflineTranslationClient, "translate_many", side_effect=ModelUnavailable),
    ):
        translate_pending_pdf_texts()
    assert PdfTextTranslation.objects.get().status == "failed"


def test_worker_does_not_overwrite_a_newer_lease(company):
    ensure_sources(company.pk, [source("Chaise en bois")], ["nl"])
    new_token = uuid4()
    def translate(*args, **kwargs):
        PdfTextTranslation.objects.update(lease_token=new_token)
        return {"Chaise en bois": "Houten stoel"}
    with patch.object(AiAssistantClient, "translate_many", side_effect=translate):
        translate_pending_pdf_texts()
    row = PdfTextTranslation.objects.get()
    assert row.status == "processing"
    assert row.lease_token == new_token
    assert row.translated_text == ""


def test_worker_limits_batches_and_keeps_companies_separate(company):
    other = Company.objects.create(raison_sociale="Other", ICE="OTHER-PDF-QA")
    ensure_sources(company.pk, [source("A" * 3500), source("B" * 3500)], ["nl"])
    ensure_sources(other.pk, [source("Other text")], ["nl"])
    with patch.object(AiAssistantClient, "translate_many", return_value={"A" * 3500: "Dutch A"}) as model:
        translate_pending_pdf_texts()
    assert model.call_args.args[0] == ["A" * 3500]
    assert PdfTextTranslation.objects.filter(status="ready").count() == 1


def test_backfill_is_scoped_idempotent_and_bounded(company, settings):
    assert backfill_pdf_translations.queue == "celery"
    assert translate_pending_pdf_texts.queue == "pdf_translations"
    settings.AI_PDF_TRANSLATION_ENABLED = False
    for index in range(3):
        Article.objects.create(company=company, reference=f"A-{index}", designation=f"Chaise {index}")
    other = Company.objects.create(raison_sociale="Other", ICE="OTHER-PDF-QA")
    Article.objects.create(company=other, reference="OTHER", designation="Other")
    settings.AI_PDF_TRANSLATION_ENABLED = True
    with patch.object(backfill_pdf_translations, "apply_async") as next_batch:
        result = backfill_pdf_translations(company_id=company.pk, languages=["nl"], batch_size=2)
        backfill_pdf_translations(company_id=company.pk, languages=["nl"], batch_size=2)
    assert result["scanned"] == 2
    assert PdfTextTranslation.objects.count() == 2
    assert not PdfTextTranslation.objects.filter(company=other).exists()
    assert next_batch.call_args.kwargs["kwargs"]["after_pk"] > 0


def test_backfill_command_queues_and_reports_status(company):
    ensure_sources(company.pk, [source("Chaise")])
    with patch.object(backfill_pdf_translations, "delay") as task:
        call_command("translate_pdf_content", company=company.pk, language=["nl"], stdout=StringIO())
    task.assert_called_once_with(company_id=company.pk, languages=["nl"], batch_size=100)
    output = StringIO()
    call_command("translate_pdf_content", status=True, stdout=output)
    assert "nl pending: 1" in output.getvalue()


def test_payment_methods_are_prepared(company):
    ModePaiement.objects.create(company=company, nom="Virement bancaire")
    assert PdfTextTranslation.objects.filter(source_text="Virement bancaire").count() == 3


def test_rolled_back_content_does_not_leave_translations_or_jobs(company, django_capture_on_commit_callbacks, background_settings):
    from django.db import transaction

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ValueError), transaction.atomic():
            Article.objects.create(company=company, reference="ROLLBACK", designation="À annuler")
            raise ValueError("rollback")
    assert not PdfTextTranslation.objects.exists()
    background_settings[0].assert_not_called()


def test_article_save_prepares_existing_units(company, settings):
    settings.AI_PDF_TRANSLATION_ENABLED = False
    unit = Unite.objects.create(company=company, nom="Pièce")
    settings.AI_PDF_TRANSLATION_ENABLED = True
    Article.objects.create(company=company, reference="UNIT-QA", designation="Chaise", unite=unit)
    assert PdfTextTranslation.objects.filter(company=company, source_text="Pièce").count() == 3


def test_name_changes_schedule_dependent_refresh(company, document, django_capture_on_commit_callbacks):
    with patch.object(backfill_pdf_translations, "delay") as task, django_capture_on_commit_callbacks(execute=True):
        document.client.raison_sociale = "Client Nouveau"
        document.client.save(update_fields=["raison_sociale"])
    task.assert_called_once_with(company_id=company.pk)


def test_source_fingerprint_preserves_whitespace_and_limits_irrelevant_terms():
    assert source(" Texte\n").fingerprint != source("Texte").fingerprint
    assert source("Texte", ["Absent"]) == source("Texte")


def test_gateway_rate_limit_is_retried_by_celery_without_sleep():
    from rest_framework.exceptions import Throttled
    with patch.object(AiAssistantClient, "_post", side_effect=Throttled(wait=60)), patch("ai_assistant.client.time.sleep") as sleep:
        with pytest.raises(Throttled):
            AiAssistantClient().translate_many(["Chaise"], target_language="nl", retry_rate_limit=False)
    sleep.assert_not_called()


def test_pdf_polling_does_not_enqueue_duplicate_jobs(company, document, django_capture_on_commit_callbacks, background_settings):
    background_settings[0].reset_mock()
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(3):
            with pytest.raises(PdfTranslationPending):
                load_pdf_translations(document, company, "nl")
    background_settings[0].assert_called_once()


def test_urgent_work_is_not_mixed_with_backfill(company):
    ensure_sources(company.pk, [source("Urgent")], ["en"], priority=0)
    ensure_sources(company.pk, [source("Historique")], ["en"], priority=100)
    with patch.object(AiAssistantClient, "translate_many", return_value={"Urgent":"Urgent translated"}) as translate:
        translate_pending_pdf_texts()
    assert translate.call_args.args[0] == ["Urgent"]
    assert PdfTextTranslation.objects.get(source_text="Historique").status == "pending"


def test_one_bad_field_does_not_fail_valid_batch_fields(company):
    ensure_sources(company.pk, [source("Bad"), source("Good")], ["en"])
    with patch.object(AiAssistantClient, "translate_many", side_effect=[InvalidModelResponse(), InvalidModelResponse(), {"Good":"Translated good"}]):
        translate_pending_pdf_texts()
    assert PdfTextTranslation.objects.get(source_text="Bad").status == "pending"
    good = PdfTextTranslation.objects.get(source_text="Good")
    assert good.status == "ready"
    assert good.attempts == 0


@pytest.mark.parametrize("kind", ["quote", "invoice", "proforma"])
@pytest.mark.parametrize("language", ["fr", "en", "nl"])
@pytest.mark.parametrize("pdf_type", ["avec_remise", "sans_remise", "avec_unite_sans_remise", "avec_unite_avec_remise"])
def test_all_document_variants_render_from_saved_translations(company, document, kind, language, pdf_type):
    from decimal import Decimal
    from facture_client.models import FactureClient
    from facture_client.views import FactureClientPDFGenerator
    from facture_proforma.models import FactureProForma
    from facture_proforma.views import FactureProFormaPDFGenerator
    from devi.views import DeviPDFGenerator

    if kind == "quote":
        generator_class, parent_field = DeviPDFGenerator, "devis"
    else:
        model, generator_class = (FactureClient, FactureClientPDFGenerator) if kind == "invoice" else (FactureProForma, FactureProFormaPDFGenerator)
        document = model.objects.create(company=company, client=document.client, numero_facture=f"{kind}-QA", date_facture=date.today(), remarque="Livrer avant midi", termes_paiement="Acompte à la commande")
        parent_field = "facture_client" if kind == "invoice" else "facture_pro_forma"
    line_model = document.lignes.model
    unit = Unite.objects.create(company=company, nom="Pièce")
    article = Article.objects.create(company=company, reference="A-123", designation="Chaise en bois\nFinition naturelle", unite=unit, tva=20)
    line_model.objects.create(**{parent_field: document}, article=article, quantity=Decimal("2"), prix_vente=Decimal("100"), prix_achat=Decimal("80"))
    document.refresh_from_db()
    ensure_sources(company.pk, pdf_sources(document, company))
    if language != "fr":
        ready_rows(language)
    with patch.object(AiAssistantClient, "translate_many") as model:
        generator = generator_class(document, company, pdf_type=pdf_type, language=language)
        response = generator.generate_pdf()
    assert response.content.startswith(b"%PDF")
    assert response["Content-Type"] == "application/pdf"
    text = "Chaise en bois\nFinition naturelle"
    assert generator._text(text) == (text if language == "fr" else f"NL {text}")
    model.assert_not_called()


def test_old_engine_ready_rows_are_requeued_before_pdf_use(company, document):
    ready_rows()
    PdfTextTranslation.objects.filter(language="nl").update(engine_revision=1)
    with pytest.raises(PdfTranslationPending):
        load_pdf_translations(document, company, "nl")
    row = PdfTextTranslation.objects.get(language="nl")
    assert row.engine_revision == 2 and row.status == "pending" and row.priority == 0


def test_quota_uses_offline_translation_and_keeps_foreground_allowance(company):
    from ai_assistant.tasks import quota_key
    ensure_sources(company.pk, [source("Chaise en bois")], ["en"], dispatch=False, priority=100)
    with (
        patch.object(AiAssistantClient, "translate_many", side_effect=Throttled(wait=25_000)) as client,
        patch.object(OfflineTranslationClient, "translate_many", side_effect=[
            {"Chaise en bois": "Wooden chair"},
            {"Table en bois": "Wooden table"},
        ]) as offline,
    ):
        translate_pending_pdf_texts()
        deadline = cache.get(quota_key(100))
        ensure_sources(company.pk, [source("Table en bois")], ["en"], dispatch=False, priority=100)
        translate_pending_pdf_texts()
    assert client.call_count == 1
    assert offline.call_count == 2
    assert PdfTextTranslation.objects.filter(status="ready", attempts=0).count() == 2
    assert cache.get(quota_key(100)) == deadline
    assert not cache.get(quota_key(0))
    ensure_sources(company.pk, [source("Lampe en bois")], ["en"], dispatch=False, priority=0)
    with patch.object(AiAssistantClient, "translate_many", return_value={"Lampe en bois": "Wooden lamp"}) as client:
        translate_pending_pdf_texts()
    client.assert_called_once()
    assert PdfTextTranslation.objects.get(source_text="Lampe en bois").status == "ready"


@pytest.mark.parametrize("priority", [0, 100])
def test_requested_pdf_recovers_old_quota_wait_once(company, document, priority, django_capture_on_commit_callbacks, background_settings):
    row = PdfTextTranslation.objects.get(language="en")
    row.priority = priority
    row.available_at = timezone.now() + timedelta(hours=4)
    row.last_error = "ai_rate_limited"
    row.save()
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(2):
            with pytest.raises(PdfTranslationPending):
                load_pdf_translations(document, company, "en")
    row.refresh_from_db()
    assert row.priority == 0 and row.available_at <= timezone.now() and not row.last_error
    background_settings[0].assert_called_once()


@pytest.mark.parametrize("translated", ["One paragraph.", "• Deliver 120x120cm.\n• Marble not included."])
def test_worker_rejects_changed_layout_or_dimensions(company, translated):
    from types import SimpleNamespace
    from ai_assistant.pdf_translation import validate_saved_translation
    row = SimpleNamespace(source_text="• Livrer 120*120cm.\n• Marbre non compris.", protected_terms=[])
    with pytest.raises(InvalidModelResponse):
        validate_saved_translation(row, translated)


def test_historical_refresh_uses_background_quota_and_reuses_authoritative_french(company):
    ensure_sources(company.pk, [source("Chaise en bois")], priority=0, dispatch=False)
    PdfTextTranslation.objects.update(engine_revision=1, status="ready", translated_text="Old output")
    PdfTextTranslation.objects.filter(language="fr").update(translated_text="Chaise en bois")
    with patch.object(backfill_pdf_translations,"delay"):
        call_command("translate_pdf_content",refresh_existing=True,stdout=StringIO())
    assert PdfTextTranslation.objects.get(language="fr").status == "ready"
    for row in PdfTextTranslation.objects.exclude(language="fr"):
        assert (row.status,row.engine_revision,row.priority) == ("pending",2,100)


def test_worker_drains_old_quota_rows_without_waiting_for_pdf_request(company, document):
    from ai_assistant.tasks import quota_key
    PdfTextTranslation.objects.exclude(language="nl").delete()
    row = PdfTextTranslation.objects.get(language="nl")
    row.available_at = timezone.now() + timedelta(hours=4)
    row.last_error = "ai_rate_limited"
    row.save()
    cache.set(quota_key(row.priority), row.available_at.timestamp(), 14_400)
    with (
        patch.object(AiAssistantClient, "translate_many") as gateway,
        patch.object(OfflineTranslationClient, "translate_many", return_value={
            document.remarque: "Voor de middag leveren",
        }),
    ):
        translate_pending_pdf_texts()
    gateway.assert_not_called()
    assert load_pdf_translations(document, company, "nl") == {
        document.remarque: "Voor de middag leveren",
    }


def test_pdf_gateway_http_rate_limit_falls_back_without_sleeping(company, document, settings):
    settings.AI_ASSISTANT_ENABLED = True
    settings.AI_ASSISTANT_SERVICE_SECRET = "test-secret"
    PdfTextTranslation.objects.exclude(language="en").delete()
    failure = HTTPError("http://gateway/v1/translate", 429, "Quota", {"Retry-After": "25000"}, None)
    with (
        patch("ai_assistant.client.request.urlopen", side_effect=failure) as request,
        patch("ai_assistant.client.time.sleep") as sleep,
        patch.object(OfflineTranslationClient, "translate_many", return_value={
            document.remarque: "Deliver before noon",
        }),
    ):
        translate_pending_pdf_texts()
    sleep.assert_not_called()
    assert 0 < request.call_args.kwargs["timeout"] <= 15
    assert load_pdf_translations(document, company, "en")[document.remarque] == "Deliver before noon"


@pytest.mark.parametrize("failure", [ModelTimeout, ModelUnavailable])
def test_pdf_gateway_timeout_or_outage_uses_offline_translation(company, failure):
    original = "• Livrer REF-123 avant midi.\n• Quantité : 12"
    translated = "• Deliver REF-123 before noon.\n• Quantity: 12"
    ensure_sources(company.pk, [source(original, ["REF-123"])], ["en"])
    with (
        patch.object(AiAssistantClient, "translate_many", side_effect=failure),
        patch.object(OfflineTranslationClient, "translate_many", return_value={original: translated}),
    ):
        translate_pending_pdf_texts()
    row = PdfTextTranslation.objects.get()
    assert (row.status, row.translated_text) == ("ready", translated)
