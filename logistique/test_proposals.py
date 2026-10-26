"""Proposed corrections are reviewed as values and never applied before acceptance."""
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from account.models import CustomUser, Membership, Role
from notification.models import Notification
from .models import LogisticsChangeRequest
from .test_purchase import (  # noqa: F401
    purchase_context, authenticated, create_dossier, validated_dossier, purchase_post,
)

pytestmark = pytest.mark.django_db


def propose(ctx, order, data, step="dossier", client=None):
    return purchase_post(ctx, order, "demander_modification", client=client,
        etape=step, remarque="La valeur saisie doit être corrigée.", modifications=data)


def test_values_stay_unchanged_until_reviewer_accepts_and_approval_cannot_replay(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    original = order.fournisseur_email
    response = propose(ctx, order, {"action": "dossier", "fournisseur_email": "corrected@example.invalid"})
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.fournisseur_email == original
    item = order.change_requests.get()
    assert item.statut == "pending"
    assert item.changes == [{"field": "fournisseur_email", "label": "E-mail du fournisseur",
        "before": original, "after": "corrected@example.invalid"}]
    assert response.data["change_requests"][0]["has_proposal"] is True
    result = purchase_post(ctx, order, "approuver_modification",
        client=authenticated(ctx.responsible), demande_id=item.pk)
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    item.refresh_from_db()
    assert order.fournisseur_email == "corrected@example.invalid"
    assert item.statut == "applied" and item.applied_at and item.decided_at
    assert Notification.objects.filter(user=ctx.creator, title="Modification logistique approuvée").exists()
    assert purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.responsible), demande_id=item.pk).status_code == 400


def test_declining_keeps_original_values(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    original = order.fournisseur
    response = propose(ctx, order, {"action": "dossier", "fournisseur": "Proposition refusée"})
    assert response.status_code == 200, response.data
    item = order.change_requests.get()
    result = purchase_post(ctx, order, "refuser_modification", client=authenticated(ctx.responsible), demande_id=item.pk)
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    item.refresh_from_db()
    assert order.fournisseur == original and item.statut == "rejected" and item.applied_at is None


@pytest.mark.parametrize("data", [
    {"action": "dossier", "fournisseur_email": "invalid"},
    {"action": "titre", "banque": "Bank"},
    {"action": "dossier", "correction_id": 99, "fournisseur": "Changed"},
    {"action": "dossier"},
])
def test_invalid_cross_step_or_empty_proposals_are_not_saved(purchase_context, data):
    ctx = purchase_context
    order = create_dossier(ctx)
    original = order.fournisseur
    response = propose(ctx, order, data)
    assert response.status_code == 400, response.data
    assert not order.change_requests.exists()
    order.refresh_from_db()
    assert order.fournisseur == original


def test_stale_changes_cannot_overwrite_a_later_correction(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    assert propose(ctx, order, {"action": "dossier", "fournisseur_email": "proposed@example.invalid"}).status_code == 200
    item = order.change_requests.get()
    order.fournisseur_email = "changed-after-request@example.invalid"
    order.save()
    result = purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.responsible), demande_id=item.pk)
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    item.refresh_from_db()
    assert order.fournisseur_email == "changed-after-request@example.invalid" and item.statut == "pending"


def test_company_admin_can_review_and_receives_notification(purchase_context):
    ctx = purchase_context
    admin = CustomUser.objects.create_user(email="admin@example.invalid", password="test")
    Membership.objects.create(company=ctx.company, user=admin, role=Role.objects.get_or_create(name="Caissier")[0])
    order = create_dossier(ctx)
    assert propose(ctx, order, {"action": "dossier", "fournisseur_email": "corrected@example.invalid"}).status_code == 200
    item = order.change_requests.get()
    assert Notification.objects.filter(user=admin, title="Modification logistique à approuver").exists()
    assert purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.outsider), demande_id=item.pk).status_code == 403
    result = purchase_post(ctx, order, "approuver_modification", client=authenticated(admin), demande_id=item.pk)
    assert result.status_code == 200, result.data


def test_file_is_staged_separately_then_applied_once_accepted(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="advance100", total="100")
    original = order.proforma_fournisseur_file.name
    data = {"action": "proforma", "decision": "validate", "condition_achat": order.condition_achat,
        "numero_proforma_fournisseur": order.numero_proforma_fournisseur,
        "date_proforma_fournisseur": order.date_proforma_fournisseur.isoformat(),
        "montant_proforma_fournisseur": str(order.montant_proforma_fournisseur),
        "devise_proforma_fournisseur": order.devise_proforma_fournisseur,
        "incoterm": order.incoterm, "delai_proforma_jours": order.delai_proforma_jours}
    response = ctx.api.post(reverse("logistique:logistique-purchase", args=[order.pk]), {
        "action": "demander_modification", "etape": "proforma", "remarque": "Document fournisseur corrigé.",
        "modifications": json.dumps(data),
        "proforma_fournisseur_file": SimpleUploadedFile("corrected.pdf", b"%PDF-1.4 proposed", content_type="application/pdf"),
    }, format="multipart")
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.proforma_fournisseur_file.name == original
    item = order.change_requests.get()
    assert item.files.count() == 1
    assert item.files.get().file.storage.exists(item.files.get().file.name)
    assert any(change.get("file_url") for change in response.data["change_requests"][0]["changes"])
    response = purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.responsible), demande_id=item.pk)
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.proforma_fournisseur_file.name != original
    assert order.proforma_fournisseur_file.read() == b"%PDF-1.4 proposed"


def test_comment_alone_cannot_create_an_authorization(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    result = purchase_post(ctx, order, "demander_modification", etape="dossier", remarque="Veuillez corriger ce dossier.")
    assert result.status_code == 400 and not order.change_requests.exists()


def test_historical_dossier_proposes_values_and_applies_them_only_after_approval(purchase_context):
    from .models import LogisticsOrder
    ctx = purchase_context
    order = LogisticsOrder.objects.create(company=ctx.company, numero_commande="HIST-PROPOSAL", workflow_version=1,
        responsable=ctx.responsible, statut_commande_lancement="Terminée", statut="Proforma", description="Avant")
    response = propose(ctx, order, {"action": "historical", "description": "Après"})
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.description == "Avant"
    item = order.change_requests.get()
    assert any(change["field"] == "description" and change["after"] == "Après" for change in item.changes)
    response = purchase_post(ctx, order, "approuver_modification", client=authenticated(ctx.responsible), demande_id=item.pk)
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.description == "Après" and order.statut == "Proforma"
