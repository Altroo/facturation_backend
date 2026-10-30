"""Explicit adoption preserves legacy data and cannot bypass business progress."""
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from client.models import Client
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import ModePaiement
from stock.models import StockMovement, StockReceipt

from logistique.compatibility import can_adopt_supplier_workflow
from logistique.models import LogisticsOrder, LogisticsOrderLine, LogisticsOrderProforma, LogisticsPaymentInstallment
from logistique.tests.helpers import authenticated, proforma_payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy_dossier(purchase_context):
    ctx = purchase_context
    client = Client.objects.create(company=ctx.company, code_client="LEGACY-CLIENT", client_type="PM", raison_sociale="Client d’origine")
    mode = ModePaiement.objects.create(company=ctx.company, nom="Virement")
    proforma = FactureProForma.objects.create(company=ctx.company, client=client, mode_paiement=mode,
        numero_facture="LEGACY-SOURCE", date_facture=timezone.localdate(), statut="Accepté",
        fournisseur="Ancien fournisseur", created_by_user=ctx.creator)
    source = FactureProFormaLine.objects.create(facture_pro_forma=proforma, article=ctx.article,
        quantity="5.000", prix_achat="7.00", prix_vente="12.00")
    order = LogisticsOrder.objects.create(company=ctx.company, numero_commande="LEGACY-001", workflow_version=1,
        responsable=ctx.responsible, created_by_user=ctx.creator, statut="Proforma",
        statut_commande_lancement="Terminée", prochaine_relance_proforma=timezone.localdate() + timedelta(days=3),
        proforma_demandee_le=timezone.now(), proforma_demandee_par=ctx.creator,
        proforma_fournisseur_file="legacy/supplier-proforma.pdf", description="Conserver ce renseignement")
    LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)
    LogisticsOrderLine.objects.create(commande=order, proforma=proforma, source_line=source, client=client,
        article=ctx.article, article_reference=ctx.article.reference, designation=ctx.article.designation,
        quantity=Decimal("5.000"), prix_achat=Decimal("7.00"), prix_vente=Decimal("12.00"), expected_emplacement=ctx.location)
    order.add_event(user=ctx.creator, action="Ancienne action", note="Historique conservé")
    order.save()
    return order


def adopt(ctx, order, client=None, **overrides):
    data = {"action": "adopter_parcours_fournisseur", "fournisseur": "Fournisseur confirmé", "responsable": ctx.responsible.pk}
    data.update(overrides)
    return (client or ctx.api).post(reverse("logistique:logistique-purchase", args=[order.pk]), data, format="json")


def test_read_eligibility_does_not_mutate_legacy_data_or_expose_snapshot(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    before = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    history_count, event_count = order.history.count(), order.events.count()
    with patch("logistique.purchase_views.activate_incoming") as incoming:
        response = ctx.api.get(reverse("logistique:logistique-detail", args=[order.pk]))
        listing = ctx.api.get(reverse("logistique:logistique-list-create"), {"company_id": ctx.company.pk})
    assert response.status_code == listing.status_code == 200
    assert response.data["can_adopt_supplier_workflow"] is True
    assert next(row for row in listing.data["results"] if row["id"] == order.pk)["can_adopt_supplier_workflow"] is True
    assert "legacy_source_snapshot" not in response.data
    assert LogisticsOrder.objects.filter(pk=order.pk).values().get() == before
    assert order.history.count() == history_count and order.events.count() == event_count
    incoming.assert_not_called()


def test_explicit_adoption_preserves_sources_documents_rows_and_original_snapshot(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    original = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    original_lines = list(order.lignes.values())
    original_links = list(order.commande_proformas.values())
    original_events = list(order.events.values())
    balances = list(ctx.company.stock_balances.values())
    movement_count = StockMovement.objects.count()
    with patch("logistique.purchase_views.activate_incoming") as incoming:
        response = adopt(ctx, order)
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.workflow_version == 2 and order.statut == "Proforma" and order.statut_commande_lancement == "Terminée"
    assert order.prochaine_relance_proforma is None
    assert order.created_by_user_id == original["created_by_user_id"]
    assert order.date_created == original["date_created"]
    assert order.proforma_fournisseur_file.name == original["proforma_fournisseur_file"]
    assert order.description == original["description"]
    assert list(order.lignes.values()) == original_lines
    assert list(order.commande_proformas.values()) == original_links
    for event in original_events:
        assert order.events.filter(pk=event["id"]).values().get() == event
    snapshot = order.legacy_source_snapshot
    assert snapshot["order"]["workflow_version"] == 1
    assert snapshot["order"]["fournisseur"] == ""
    assert snapshot["order"]["prochaine_relance_proforma"] == str(original["prochaine_relance_proforma"])
    assert snapshot["lines"][0]["id"] == original_lines[0]["id"]
    assert snapshot["lines"][0]["quantity"] == "5.000"
    assert snapshot["lines"][0]["prix_achat"] == "7.00"
    assert snapshot["lines"][0]["source_line_id"] == original_lines[0]["source_line_id"]
    assert snapshot["proforma_links"][0]["proforma_id"] == original_links[0]["proforma_id"]
    assert response.data["can_adopt_supplier_workflow"] is False
    assert "legacy_source_snapshot" not in response.data
    assert StockMovement.objects.count() == movement_count
    assert list(ctx.company.stock_balances.values()) == balances
    incoming.assert_not_called()


@pytest.mark.parametrize("override", [
    {"fournisseur": ""}, {"responsable": -1}, {"responsable": "FOREIGN"},
    {"fournisseur_record": "FOREIGN"},
])
def test_invalid_adoption_is_atomic_and_creates_no_supplier(purchase_context, legacy_dossier, override):
    ctx, order = purchase_context, legacy_dossier
    from logistique.models import LogisticsSupplier
    data = {key: (ctx.outsider.pk if key == "responsable" else 999999) if value == "FOREIGN" else value for key, value in override.items()}
    before = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    event_count, supplier_count = order.events.count(), LogisticsSupplier.objects.count()
    response = adopt(ctx, order, **data)
    assert response.status_code == 400, response.data
    assert LogisticsOrder.objects.filter(pk=order.pk).values().get() == before
    assert order.events.count() == event_count and LogisticsSupplier.objects.count() == supplier_count


@pytest.mark.parametrize("actor", ["reader", "accountant", "outsider"])
def test_readers_unassigned_accountants_and_foreign_users_cannot_adopt(purchase_context, legacy_dossier, actor):
    ctx, order = purchase_context, legacy_dossier
    response = adopt(ctx, order, client=authenticated(getattr(ctx, actor)))
    assert response.status_code == 403, response.data
    order.refresh_from_db()
    assert order.workflow_version == 1 and not order.legacy_source_snapshot


@pytest.mark.parametrize("changes", [
    {"statut": "Production"}, {"statut": "Clôture"}, {"statut_global": "Annulé"},
    {"statut_proforma_conformite": "Validée"}, {"statut_paiement": "En attente"},
    {"statut_banque_paiement": "En validation"}, {"statut_titre_importation": "Titre d'import validé – En attente de paiement"},
    {"demande_paiement_email_statut": "Échec"}, {"demande_paiement_email_tentatives": 1},
    {"demande_paiement_email_task_id": "queued-task"}, {"montant_paiement": Decimal("0.01")},
    {"swift_file": "legacy/payment.pdf"}, {"cout_transport": Decimal("12.00")},
    {"date_validation_titre_importation": "TODAY"}, {"date_reelle": "TODAY"},
    {"date_expedition_reelle": "TODAY"}, {"proforma_validee_le": "NOW"},
    {"production_confirmee_le": "NOW"},
])
def test_progressed_dossiers_cannot_adopt_or_change_snapshot(purchase_context, legacy_dossier, changes):
    ctx, order = purchase_context, legacy_dossier
    changes = {key: timezone.localdate() if value == "TODAY" else timezone.now() if value == "NOW" else value for key, value in changes.items()}
    LogisticsOrder.objects.filter(pk=order.pk).update(**changes)
    order.refresh_from_db()
    assert can_adopt_supplier_workflow(order) is False
    before = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    response = adopt(ctx, order)
    assert response.status_code == 400, response.data
    assert LogisticsOrder.objects.filter(pk=order.pk).values().get() == before


@pytest.mark.parametrize("related", ["payment", "receipt", "received", "movement"])
def test_existing_payment_or_physical_records_prevent_adoption(purchase_context, legacy_dossier, related):
    ctx, order = purchase_context, legacy_dossier
    if related == "payment":
        LogisticsPaymentInstallment.objects.create(commande=order, montant_prevu=1, pourcentage=100, devise="EUR")
    elif related == "receipt":
        StockReceipt.objects.create(company=ctx.company, logistics_order=order, created_by=ctx.creator)
    elif related == "received":
        order.lignes.update(received_quantity=1)
    else:
        StockMovement.objects.create(balance=ctx.balance, movement_type="receipt", quantity=1, balance_after=1,
            source_type="LogisticsOrder", source_id=order.pk)
    assert can_adopt_supplier_workflow(order) is False
    response = adopt(ctx, order)
    assert response.status_code == 400, response.data
    order.refresh_from_db()
    assert order.workflow_version == 1 and not order.legacy_source_snapshot


def test_supplier_control_requires_reentered_supplier_quantities_and_keeps_archive(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    old_line = order.lignes.get()
    assert adopt(ctx, order).status_code == 200
    order.refresh_from_db()
    archive = order.legacy_source_snapshot
    endpoint = reverse("logistique:logistique-purchase", args=[order.pk])
    payload = proforma_payload(ctx)
    payload.pop("lignes")
    response = ctx.api.post(endpoint, payload, format="multipart")
    assert response.status_code == 400 and "lignes" in response.data["details"]
    assert order.lignes.filter(pk=old_line.pk).exists()
    response = ctx.api.post(endpoint, proforma_payload(ctx, lignes=json.dumps([
        {"article": ctx.article.pk, "quantity": "2.000", "prix_achat": "50.00"}
    ])), format="multipart")
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.legacy_source_snapshot == archive
    supplier_line = order.lignes.get()
    assert supplier_line.quantity == 2 and supplier_line.prix_achat == 50
    assert supplier_line.proforma_id is None and supplier_line.client_id is None and supplier_line.source_line_id is None
    assert order.proformas.count() == 1
    assert archive["lines"][0]["id"] == old_line.pk
    assert archive["lines"][0]["quantity"] == "5.000"
    assert archive["lines"][0]["source_line_id"] == old_line.source_line_id
    # Replaying adoption cannot overwrite the original snapshot or create a second event.
    count = order.events.filter(action="Passage au parcours d’achat fournisseur").count()
    response = adopt(ctx, order, legacy_source_snapshot={"changed": True})
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.legacy_source_snapshot == archive
    assert order.events.filter(action="Passage au parcours d’achat fournisseur").count() == count == 1


def test_other_supplier_actions_cannot_implicitly_adopt(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    response = ctx.api.post(reverse("logistique:logistique-purchase", args=[order.pk]),
        {"action": "progression", "statut": "Production"}, format="json")
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.workflow_version == 1 and not order.legacy_source_snapshot


def test_exception_during_adoption_rolls_back_supplier_snapshot_and_events(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    from logistique.models import LogisticsSupplier
    before = LogisticsOrder.objects.filter(pk=order.pk).values().get()
    suppliers, events = LogisticsSupplier.objects.count(), order.events.count()
    with patch.object(LogisticsOrder, "add_event", side_effect=RuntimeError("test rollback")):
        with pytest.raises(RuntimeError, match="test rollback"):
            adopt(ctx, order)
    assert LogisticsOrder.objects.filter(pk=order.pk).values().get() == before
    assert LogisticsSupplier.objects.count() == suppliers and order.events.count() == events


def test_receipt_added_after_adoption_cannot_cause_a_protected_delete_error(purchase_context, legacy_dossier):
    ctx, order = purchase_context, legacy_dossier
    from stock.models import StockReceiptLine
    assert adopt(ctx, order).status_code == 200
    order.refresh_from_db()
    archive = order.legacy_source_snapshot
    original_line = order.lignes.get()
    receipt = StockReceipt.objects.create(company=ctx.company, logistics_order=order, created_by=ctx.creator)
    StockReceiptLine.objects.create(receipt=receipt, logistics_line=original_line, article=ctx.article,
        emplacement=ctx.location, quantity=1)
    response = ctx.api.post(reverse("logistique:logistique-purchase", args=[order.pk]), proforma_payload(ctx), format="multipart")
    assert response.status_code == 400 and "lignes" in response.data["details"]
    order.refresh_from_db()
    assert order.legacy_source_snapshot == archive and order.lignes.filter(pk=original_line.pk).exists()
    assert order.proforma_validee_le is None and not order.echeances_paiement.exists()
