"""Stage navigation, supplier brands and approval-bound corrections."""
import pytest
from django.urls import reverse
from django.utils import timezone

from notification.models import Notification
from parameter.models import Marque
from logistique.models import LogisticsChangeRequest, LogisticsSupplier
from logistique.purchase import purchase_steps
from logistique.tests.helpers import authenticated, create_dossier, validated_dossier, prepare_title, purchase_post

pytestmark = pytest.mark.django_db


def approved_change(ctx, order, step):
    # Authorizations already issued before proposals were introduced remain usable once.
    return LogisticsChangeRequest.objects.create(commande=order, etape=step,
        remarque="Corriger la saisie du document.", demandeur=ctx.creator,
        responsable=ctx.responsible, statut="approved", decided_at=timezone.now())


def test_only_current_stage_is_available_for_writing_and_future_is_hidden(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    steps, current = purchase_steps(order)
    assert current == "proforma"
    assert [step["key"] for step in steps if step["accessible"]] == ["dossier", "proforma"]
    response = purchase_post(ctx, order, "titre", banque="Attijariwafa bank")
    assert response.status_code == 400
    response = purchase_post(ctx, order, "dossier", fournisseur_email="correction@example.invalid")
    assert response.status_code == 403
    order.refresh_from_db()
    assert order.banque == ""
    assert order.fournisseur_email != "correction@example.invalid"


def test_approval_notifies_both_users_and_applies_only_the_proposed_values(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    response = purchase_post(ctx, order, "demander_modification", etape="dossier", remarque="Adresse corrigée",
        modifications={"action": "dossier", "fournisseur_email": "changed@example.invalid"})
    assert response.status_code == 200, response.data
    item = order.change_requests.get()
    assert Notification.objects.filter(user=ctx.responsible, title="Modification logistique à approuver").exists()
    response = purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.responsible), demande_id=item.pk)
    assert response.status_code == 200, response.data
    item.refresh_from_db()
    order.refresh_from_db()
    assert item.statut == "applied" and order.fournisseur_email == "changed@example.invalid"
    assert Notification.objects.filter(user=ctx.creator, title="Modification logistique approuvée").exists()
    response = purchase_post(ctx, order, "dossier", correction_id=item.pk, fournisseur_email="replay@example.invalid")
    assert response.status_code == 403


@pytest.mark.parametrize("actor", ["creator", "outsider", "reader"])
def test_only_responsible_can_approve(purchase_context, actor):
    ctx = purchase_context
    order = create_dossier(ctx)
    assert purchase_post(ctx, order, "demander_modification", etape="dossier", remarque="Correction nécessaire", modifications={"action": "dossier", "fournisseur_email": "changed@example.invalid"}).status_code == 200
    item = order.change_requests.get()
    response = purchase_post(ctx, order, "approuver_modification", client=authenticated(getattr(ctx, actor)), demande_id=item.pk)
    assert response.status_code == 403
    item.refresh_from_db()
    assert item.statut == "pending"


def test_remark_required_duplicate_and_wrong_stage_rejected(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    assert purchase_post(ctx, order, "demander_modification", etape="dossier", remarque=" ").status_code == 400
    assert purchase_post(ctx, order, "demander_modification", etape="titre", remarque="Correction").status_code == 400
    item = approved_change(ctx, order, "dossier")
    assert purchase_post(ctx, order, "demander_modification", etape="dossier", remarque="Autre correction").status_code == 400
    assert purchase_post(ctx, order, "titre", correction_id=item.pk, banque="BMCI").status_code == 400


def test_accountant_validation_and_forwarded_proof_gate_next_stage(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="advance100", total="100", with_title=False)
    assert purchase_steps(order)[1] == "titre"
    prepare_title(order)
    assert purchase_steps(order)[1] == "paiement"
    item = order.echeances_paiement.get()
    item.demandee_le = timezone.now()
    item.save()
    response = purchase_post(ctx, order, "progression", etape="production", confirmer_production=True, date_expedition_prevue=timezone.localdate().isoformat())
    assert response.status_code == 400
    item.paiement_valide_le = timezone.now()
    item.save()
    assert purchase_steps(order)[1] == "paiement"
    item.preuve_envoyee_fournisseur_le = timezone.now()
    item.save()
    assert purchase_steps(order)[1] == "production"
    response = purchase_post(ctx, order, "progression", etape="production", confirmer_production=True, date_expedition_prevue=timezone.localdate().isoformat())
    assert response.status_code == 200, response.data
    assert response.data["workflow"]["etape_courante"] == "expedition"


@pytest.mark.parametrize("condition", ["documentary100", "receipt100", "shipment100"])
def test_deferred_payment_follows_its_event_without_deadlock(purchase_context, condition):
    order = validated_dossier(purchase_context, condition=condition)
    prepare_title(order)
    steps, current = purchase_steps(order)
    keys = [step["key"] for step in steps]
    event = {"documentary100": "transit", "receipt100": "reception", "shipment100": "expedition"}[condition]
    assert current == "production"
    assert keys.index("solde") > keys.index(event)


def test_supplier_brands_filtered_and_cross_company_rejected(purchase_context):
    ctx = purchase_context
    other_brand = Marque.objects.create(company=ctx.company, nom="Autre marque")
    foreign_brand = Marque.objects.create(company=ctx.foreign, nom="Privée")
    url = f"/api/logistique/fournisseurs/?company_id={ctx.company.pk}"
    response = ctx.api.post(url, {"nom": "Multimarques", "marques": [ctx.brand.pk, other_brand.pk]}, format="json")
    assert response.status_code == 201, response.data
    assert set(response.data["marques"]) == {ctx.brand.pk, other_brand.pk}
    supplier_id = response.data["id"]
    response = ctx.api.post(url, {"nom": "Interdit", "marques": [foreign_brand.pk]}, format="json")
    assert response.status_code == 400
    unlinked = Marque.objects.create(company=ctx.company, nom="Non liée")
    response = ctx.api.post(reverse("logistique:logistique-list-create"), {"company_id": ctx.company.pk, "fournisseur_record": supplier_id, "marque": unlinked.pk}, format="json")
    assert response.status_code == 400
    order = create_dossier(ctx, fournisseur_record=supplier_id, fournisseur="Multimarques", marque=other_brand.pk)
    assert order.marque_id == other_brand.pk


def test_new_dossier_uses_eur_without_touching_existing_currencies(purchase_context):
    order = create_dossier(purchase_context)
    assert order.devise_proforma_fournisseur == order.devise_titre_importation == "EUR"


def test_approved_payment_correction_preserves_accounting_amounts(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="advance100", total="100")
    installment = order.echeances_paiement.get()
    installment.paiement_valide_le = timezone.now()
    installment.preuve_envoyee_fournisseur_le = timezone.now()
    installment.montant_paye = installment.montant_prevu
    installment.reference_bancaire = "OLD"
    installment.save()
    approval = approved_change(ctx, order, "paiement")
    rejected = purchase_post(ctx, order, "corriger_paiement", etape="paiement", correction_id=approval.pk,
        echeance_id=installment.pk, montant_paye="999", reference_paiement="NEW")
    assert rejected.status_code == 400
    response = purchase_post(ctx, order, "corriger_paiement", etape="paiement", correction_id=approval.pk,
        echeance_id=installment.pk, reference_paiement="NEW", commentaire_paiement="Référence corrigée")
    assert response.status_code == 200, response.data
    installment.refresh_from_db()
    assert installment.reference_bancaire == "NEW"
    assert installment.montant_paye == installment.montant_prevu
    approval.refresh_from_db()
    assert approval.statut == "applied"


def test_approved_receipt_correction_preserves_stock_and_quantities(purchase_context):
    from logistique.tests.helpers import ready_for_shipping, record_shipment, partial_receipt
    from stock.models import StockReceipt, StockMovement
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    first = partial_receipt(ctx, order, "FIRST", "Première réception").data["receptions"][0]
    partial_receipt(ctx, order, "SECOND", "Deuxième réception")
    response = ctx.api.patch(reverse("logistique:logistique-statut-update", args=[order.pk]), {"statut": "Livraison client"}, format="json")
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    approval = approved_change(ctx, order, "reception")
    ctx.balance.refresh_from_db()
    quantity = ctx.balance.physical_quantity
    movement_count = StockMovement.objects.count()
    response = purchase_post(ctx, order, "corriger_reception", etape="reception", correction_id=approval.pk,
        reception_id=first["id"], reference="CORRECTED", note="Numéro du bon corrigé")
    assert response.status_code == 200, response.data
    receipt = StockReceipt.objects.get(pk=first["id"])
    assert receipt.reference == "CORRECTED"
    ctx.balance.refresh_from_db()
    assert ctx.balance.physical_quantity == quantity
    assert StockMovement.objects.count() == movement_count
    assert order.stock_receipts.filter(reference="SECOND").exists()


def test_historical_steps_and_approved_edit_are_scoped(purchase_context):
    from logistique.models import LogisticsOrder
    from logistique.historical import historical_steps
    ctx = purchase_context
    order = LogisticsOrder.objects.create(company=ctx.company, numero_commande="HIST-STEPS", workflow_version=1,
        responsable=ctx.responsible, statut_commande_lancement="Terminée", statut_proforma_conformite="Validée", statut="Validation",
        proforma_fournisseur_file="test/proforma.pdf", proforma_validee_le=timezone.now())
    assert historical_steps(order)[1] == "paiement"
    detail = reverse("logistique:logistique-detail", args=[order.pk])
    response = ctx.api.put(detail, {"etape": "dossier", "description": "Correction"}, format="json")
    assert response.status_code == 403
    approval = approved_change(ctx, order, "dossier")
    wrong_stage = ctx.api.put(detail, {"etape": "dossier", "correction_id": approval.pk, "transport": "Air"}, format="json")
    assert wrong_stage.status_code == 400
    response = ctx.api.put(detail, {"etape": "dossier", "correction_id": approval.pk, "description": "Correction"}, format="json")
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.description == "Correction" and order.statut == "Validation"
    replay = ctx.api.put(detail, {"etape": "dossier", "correction_id": approval.pk, "description": "Encore"}, format="json")
    assert replay.status_code == 403
    fake = ctx.api.put(detail, {"etape": "paiement", "correction_id": 999999, "banque": "Fake"}, format="json")
    assert fake.status_code == 403


def test_supplier_brand_backfill_includes_historical_multi_brand_dossiers(purchase_context):
    from importlib import import_module
    from django.apps import apps
    from django.db import connection
    from logistique.models import LogisticsOrder
    ctx = purchase_context
    supplier = LogisticsSupplier.objects.create(company=ctx.company, nom="Historical supplier")
    extra = Marque.objects.create(company=ctx.company, nom="Second historical brand")
    foreign = Marque.objects.create(company=ctx.foreign, nom="Foreign brand")
    order = LogisticsOrder.objects.create(company=ctx.company, numero_commande="BRAND-BACKFILL", fournisseur_record=supplier, marque=ctx.brand)
    order.marques.set([extra, foreign])
    migration = import_module("logistique.migrations.0021_supplier_brands_and_step_corrections")
    with connection.schema_editor() as editor:
        migration.backfill_supplier_brands(apps, editor)
        migration.backfill_supplier_brands(apps, editor)
    assert set(supplier.marques.values_list("pk", flat=True)) == {ctx.brand.pk, extra.pk}


def test_free_text_supplier_change_links_its_selected_brand(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    brand = Marque.objects.create(company=ctx.company, nom="New supplier brand")
    approval = approved_change(ctx, order, "dossier")
    result = purchase_post(ctx, order, "dossier", correction_id=approval.pk,
        fournisseur="New independent supplier", fournisseur_record=None, marque=brand.pk)
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.fournisseur_record.nom == "New independent supplier"
    assert order.fournisseur_record.marques.filter(pk=brand.pk).exists()
