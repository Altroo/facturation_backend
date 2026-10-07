import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from account.models import CustomUser
from .client import AiAssistantClient
from .exceptions import InvalidModelResponse, AssistantDisabled

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ai_settings(settings):
    settings.AI_ASSISTANT_ENABLED = True
    settings.AI_ASSISTANT_SERVICE_NAME = "facturation"
    settings.AI_ASSISTANT_SERVICE_SECRET = "local-test-secret"
    settings.AI_ASSISTANT_GATEWAY_URL = "http://ai-assistant-gateway:8080"
    settings.AI_ASSISTANT_TIMEOUT_SECONDS = 185


def test_signed_gateway_request_uses_exact_body_and_unique_identifier():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"suggested_text": "Texte corrigé", "detected_language": "fr"}
    ).encode()
    with patch("ai_assistant.client.request.urlopen", return_value=response) as send:
        client = AiAssistantClient()
        result = client.assist(action="fix_grammar", text="Texte corrige")
        first = send.call_args.args[0]
        client.assist(action="fix_grammar", text="Texte corrige")
        second = send.call_args.args[0]
    headers = {key.lower(): value for key, value in first.header_items()}
    canonical = f"{headers['x-ai-timestamp']}\n{headers['x-ai-service']}\n{headers['x-ai-request-id']}\n{hashlib.sha256(first.data).hexdigest()}"
    assert (
        headers["x-ai-signature"]
        == hmac.new(
            b"local-test-secret", canonical.encode(), hashlib.sha256
        ).hexdigest()
    )
    assert first.full_url == "http://ai-assistant-gateway:8080/v1/assist"
    assert headers["x-ai-request-id"] != second.get_header("X-ai-request-id")
    assert result["original_text"] == "Texte corrige"


def test_pdf_translation_deduplicates_and_bounds_batches():
    captured = []

    def translate(endpoint, payload):
        captured.append(payload)
        return {"translations": ["NL " + text for text in payload["texts"]]}

    values = [f"Désignation {i}" for i in range(35)]
    with patch.object(AiAssistantClient, "_post", side_effect=translate):
        translated = AiAssistantClient().translate_many(
            values + values, target_language="nl"
        )
    assert len(translated) == 35
    assert len(captured) == 3
    assert all(len(p["texts"]) <= 15 for p in captured)
    assert all(p["target_language"] == "nl" for p in captured)


def test_long_text_retains_spacing_when_gateway_returns_identical_text():
    value = " " * 6000 + "Description détaillée.\n" * 300
    with patch.object(
        AiAssistantClient,
        "_post",
        side_effect=lambda endpoint, payload: {
            "translations": [t.strip() for t in payload["texts"]]
        },
    ):
        result = AiAssistantClient().translate_many([value], target_language="fr")
    assert result[value] == value


def test_translation_rejects_missing_or_blank_output():
    with patch.object(AiAssistantClient, "_post", return_value={"translations": []}):
        with pytest.raises(InvalidModelResponse):
            AiAssistantClient().translate_many(["Chaise"], target_language="en")


def test_assistant_is_authenticated_validates_action_and_only_returns_a_preview():
    api = APIClient()
    url = reverse("ai_assistant:assist")
    payload = {"action": "fix_grammar", "text": "Texte corrige"}
    assert api.post(url, payload, format="json").status_code in (401, 403)
    user = CustomUser.objects.create_user(
        email="assistant@example.test", password="test-pass"
    )
    api.force_authenticate(user)
    with patch(
        "ai_assistant.views.AiAssistantClient.assist",
        return_value={
            "original_text": "Texte corrige",
            "suggested_text": "Texte corrigé",
        },
    ) as assist:
        response = api.post(url, payload, format="json")
        invalid = api.post(url, {**payload, "action": "change_prices"}, format="json")
    assert response.status_code == 200
    assert response.data["suggested_text"] == "Texte corrigé"
    assert invalid.status_code == 400
    assert assist.call_count == 1


def test_missing_service_key_fails_without_network(settings):
    settings.AI_ASSISTANT_SERVICE_SECRET = ""
    with patch("ai_assistant.client.request.urlopen") as send:
        with pytest.raises(AssistantDisabled):
            AiAssistantClient().assist(action="fix_grammar", text="Texte")
    send.assert_not_called()


@pytest.mark.parametrize("language", ["fr", "en", "nl"])
def test_pdf_translates_text_once_without_changing_saved_article(language, settings):
    from datetime import date
    from decimal import Decimal
    from company.models import Company
    from client.models import Client
    from article.models import Article
    from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
    from bon_de_livraison.views import BonDeLivraisonPDFGenerator
    from django.urls import resolve

    settings.AI_PDF_TRANSLATION_ENABLED = True
    company = Company.objects.create(raison_sociale="CDL & Associés", ICE="PDF-AI-TEST")
    client = Client.objects.create(
        company=company,
        code_client="PDF-AI",
        client_type="PM",
        raison_sociale="Client Demo",
    )
    article = Article.objects.create(
        company=company,
        reference="ABC-123",
        designation="Chaise en bois",
        prix_vente=100,
    )
    document = BonDeLivraison.objects.create(
        company=company,
        client=client,
        numero_bon_livraison="BL-IA",
        date_bon_livraison=date.today(),
        remarque="Livrer avant midi",
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=document,
        article=article,
        quantity=2,
        prix_vente=100,
        prix_achat=80,
    )
    document.refresh_from_db()
    translations = {"fr": "Chaise en bois", "en": "Wooden chair", "nl": "Houten stoel"}
    with patch.object(
        AiAssistantClient,
        "translate_many",
        return_value={
            "Chaise en bois": translations[language],
            "Livrer avant midi": "Translated remark",
        },
    ) as translate:
        generator = BonDeLivraisonPDFGenerator(document, company, language=language)
        response = generator.generate_pdf()
        assert response.content.startswith(b"%PDF")
        translate.assert_called_once()
        assert translate.call_args.kwargs["target_language"] == language
        assert "ABC-123" in translate.call_args.kwargs["protected_terms"]
        table = generator._create_delivery_articles_table()
        assert table._cellvalues[1][0].getPlainText() == "ABC-123"
        assert table._cellvalues[1][1].getPlainText() == translations[language]
        assert len(table._cellvalues[0]) == 4
    article.refresh_from_db()
    document.refresh_from_db()
    assert article.designation == "Chaise en bois"
    assert document.remarque == "Livrer avant midi"
    assert document.lignes.get().quantity == Decimal("2")
    if language == "nl":
        assert table._cellvalues[0][3].getPlainText() == "Opmerking"
        assert (
            generator._build_delivery_signatures()
            ._content[1]
            ._cellvalues[0][0]
            .getPlainText()
            == "Handtekening CDL & Associés"
        )
        assert (
            generator._amount_words(Decimal("123.45"), "EUR")
            == "honderddrieëntwintig euro en vijfenveertig cent"
        )
        for module in (
            "devi",
            "facture_client",
            "facture_proforma",
            "facture_avoir",
            "bon_de_livraison",
            "reglement",
        ):
            names = {
                "devi": "devi-pdf-nl",
                "facture_client": "facture-client-pdf-nl",
                "facture_proforma": "facture-proforma-pdf-nl",
                "facture_avoir": "facture-avoir-pdf-nl",
                "bon_de_livraison": "bon-de-livraison-pdf-nl",
                "reglement": "reglement-pdf-nl",
            }
            assert (
                resolve(
                    reverse(f"{module}:{names[module]}", kwargs={"pk": document.pk})
                ).kwargs["language"]
                == "nl"
            )


def test_pdf_translation_error_does_not_silently_print_mixed_language(settings):
    from types import SimpleNamespace
    from core.pdf_utils import BasePDFGenerator
    from .exceptions import ModelUnavailable

    settings.AI_PDF_TRANSLATION_ENABLED = True
    generator = BasePDFGenerator(
        SimpleNamespace(remarque="Texte français"),
        SimpleNamespace(raison_sociale="CDL"),
        language="en",
    )
    with patch.object(
        AiAssistantClient, "translate_many", side_effect=ModelUnavailable
    ):
        with pytest.raises(ModelUnavailable):
            generator.generate_pdf()


def test_correction_journal_preview_resume_apply_conflict_and_rollback(tmp_path):
    from django.core.management import call_command, CommandError
    from company.models import Company
    from article.models import Article
    from io import StringIO

    company = Company.objects.create(raison_sociale="Correction", ICE="CORR-TEST")
    article = Article.objects.create(
        company=company,
        reference="CODE-123",
        designation="Chaise abimee 123",
        prix_vente=100,
    )
    journal = str(tmp_path / "corrections.jsonl")
    args = {
        "journal": journal,
        "model": ["article.Article"],
        "pause": 0,
        "stdout": StringIO(),
    }
    with patch(
        "ai_assistant.management.commands.ai_correct_texts.correct_text",
        return_value="Chaise abîmée 123",
    ) as correct:
        call_command("ai_correct_texts", **args)
        count = correct.call_count
        call_command("ai_correct_texts", **args)
        assert correct.call_count == count
    article.refresh_from_db()
    assert article.designation == "Chaise abimee 123"
    history_count = article.history.count()
    call_command("ai_correct_texts", apply=True, **args)
    article.refresh_from_db()
    assert article.designation == "Chaise abîmée 123"
    assert article.reference == "CODE-123" and article.prix_vente == 100
    assert article.history.count() == history_count + 1
    call_command("ai_correct_texts", apply=True, **args)
    assert article.history.count() == history_count + 1
    call_command("ai_correct_texts", rollback=True, **args)
    article.refresh_from_db()
    assert article.designation == "Chaise abimee 123"
    Article.objects.filter(pk=article.pk).update(designation="Modification humaine")
    with pytest.raises(CommandError, match="ignorés"):
        call_command("ai_correct_texts", apply=True, **args)
    article.refresh_from_db()
    assert article.designation == "Modification humaine"


def test_pdf_batch_waits_for_existing_rate_limit_before_retrying():
    from rest_framework.exceptions import Throttled

    with patch.object(
        AiAssistantClient,
        "_post",
        side_effect=[Throttled(wait=60), {"translations": ["Chair"]}],
    ) as send, patch("ai_assistant.client.time.sleep") as sleep:
        result = AiAssistantClient().translate_many(["Chaise"], target_language="en")
    assert result == {"Chaise": "Chair"}
    sleep.assert_called_once_with(60.1)
    assert send.call_count == 2
