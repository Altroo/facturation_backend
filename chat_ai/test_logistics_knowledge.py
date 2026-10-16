"""Current supplier-workflow knowledge: realistic questions, labels and access."""
import pytest

from .knowledge import ChatAIKnowledgeService
from .models import KnowledgeDocument
from .test_knowledge_retrieval import corpus
from .tests import setup

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("query", [
    "Does a supplier purchase dossier require a customer proforma?",
    "Faut-il sélectionner une proforma client pour un achat fournisseur ?",
    "What purchase conditions are available for a logistics dossier?",
    "Quelles conditions d’achat choisir pour un dossier logistique ?",
    "When can documentary collection be paid in the supplier workflow?",
    "Quand payer la remise documentaire du dossier fournisseur ?",
    "What is the difference between planned shipment and dossier completion?",
    "Quelle différence entre la date d’expédition prévue et la fin du dossier ?",
])
def test_supplier_workflow_questions_retrieve_current_guidance(corpus, query):
    hits = ChatAIKnowledgeService().retrieve(query, corpus.a.pk, {"read"})
    assert hits[0]["document_id"] == "logistics-find"
    document = KnowledgeDocument.objects.get(pk="logistics-find")
    assert hits[0]["version"] == document.document_version
    assert hits[0]["localized_content"] == document.localized_content


@pytest.mark.parametrize("locale", ["fr", "en"])
def test_new_dates_use_visible_form_captions_without_internal_field_names(corpus, locale):
    excerpt = KnowledgeDocument.objects.get(pk="logistics-find").localized_content[locale]
    for caption in (
        "Date prévue de fin du dossier", "Date de commande client",
        "Date d’expédition prévue", "Date réelle d’expédition",
        "Date d’arrivée au Maroc", "Documents remis à la banque le",
    ):
        assert caption in excerpt
    for technical_name in (
        "workflow_version", "condition_achat", "date_commande_client",
        "date_expedition_prevue", "date_expedition_reelle", "date_arrivee_maroc",
        "documents_remis_banque_le",
    ):
        assert technical_name not in excerpt


@pytest.mark.parametrize("query", [
    "Supplier purchase documentary collection and shipment",
    "Achat fournisseur remise documentaire et expédition",
])
def test_supplier_guidance_still_requires_existing_read_capability(corpus, query):
    hits = ChatAIKnowledgeService().retrieve(query, corpus.a.pk, set())
    assert "logistics-find" not in {hit["document_id"] for hit in hits}
