import json
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from article.models import Article
from logistique.models import LogisticsChangeRequest, LogisticsOrder
from stock.models import StockReceipt


def authenticated(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def create_dossier(ctx, **overrides):
    payload = {
        "company_id": ctx.company.pk,
        "fournisseur": "Fournisseur indépendant",
        "marque": ctx.brand.pk,
        "responsable": ctx.responsible.pk,
    }
    payload.update(overrides)
    response = ctx.api.post(
        reverse("logistique:logistique-list-create"), payload, format="json"
    )
    assert response.status_code == 201, response.data
    return LogisticsOrder.objects.get(pk=response.data["orders"][0]["id"])


def purchase_post(ctx, order, action, client=None, **data):
    return (client or ctx.api).post(
        reverse("logistique:logistique-purchase", args=[order.pk]),
        {"action": action, **data},
        format="json",
    )


def proforma_payload(
    ctx,
    condition="advance30_transfer70",
    total="100.01",
    currency="EUR",
    decision="validate",
    **overrides,
):
    payload = {
        "action": "proforma",
        "decision": decision,
        "numero_proforma_fournisseur": "SUP-PF-001",
        "date_proforma_fournisseur": timezone.localdate().isoformat(),
        "montant_proforma_fournisseur": total,
        "devise_proforma_fournisseur": currency,
        "incoterm": "FCA",
        "condition_achat": condition,
        "delai_proforma_jours": "10",
        "lignes": json.dumps(
            [{"article": ctx.article.pk, "quantity": "2.000", "prix_achat": "50.00"}]
        ),
        "proforma_fournisseur_file": SimpleUploadedFile(
            "supplier.pdf", b"%PDF-1.4 supplier", content_type="application/pdf"
        ),
    }
    payload.update(overrides)
    return payload


def save_proforma(ctx, order, **overrides):
    response = ctx.api.post(
        reverse("logistique:logistique-purchase", args=[order.pk]),
        proforma_payload(ctx, **overrides),
        format="multipart",
    )
    order.refresh_from_db()
    return response


def validated_dossier(ctx, *, with_title=True, **overrides):
    order = create_dossier(ctx)
    response = save_proforma(ctx, order, **overrides)
    assert response.status_code == 200, response.data
    if with_title:
        prepare_title(order)
    return order


def approved_edit(ctx, order, step):
    # Tests below exercise validation/history after the separate approval flow succeeds.
    return LogisticsChangeRequest.objects.create(
        commande=order,
        etape=step,
        remarque="Correction test",
        demandeur=ctx.creator,
        responsable=ctx.responsible,
        statut="approved",
        decided_at=timezone.now(),
    ).pk


def complete_transit(ctx, order):
    order.refresh_from_db()
    if not order.date_arrivee_maroc:
        response = purchase_post(
            ctx,
            order,
            "progression",
            etape="transit",
            date_arrivee_maroc=timezone.localdate().isoformat(),
        )
        assert response.status_code == 200, response.data
        order.refresh_from_db()


def prepare_title(order):
    order.numero_domiciliation = "TI-2026-TEST"
    order.banque = "Banque du titre"
    order.montant_titre_importation = order.payment_total
    order.devise_titre_importation = order.devise_proforma_fournisseur
    order.date_titre_importation = timezone.localdate()
    order.titre_importation_file = SimpleUploadedFile(
        "title.pdf", b"%PDF-1.4 title", content_type="application/pdf"
    )
    order.save()


def request_installment(ctx, order, installment, callbacks):
    with patch("logistique.services.queue_accounting_payment_email"):
        with callbacks(execute=True):
            response = authenticated(ctx.responsible).post(
                reverse("logistique:logistique-request-payment", args=[order.pk]),
                {
                    "echeance_id": installment.pk,
                    "date_echeance": timezone.localdate().isoformat(),
                },
                format="json",
            )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    # The accounting transport is mocked, so acknowledge its delivery in the fixture.
    order.demande_paiement_email_statut = "Envoyé"
    order.save(update_fields=["demande_paiement_email_statut"])
    return response


def execute_installment(ctx, order, installment, callbacks):
    accountant = authenticated(ctx.accountant)
    response = accountant.post(
        reverse("logistique:logistique-start-payment", args=[order.pk]),
        {"echeance_id": installment.pk},
        format="json",
    )
    assert response.status_code == 200, response.data
    response = accountant.post(
        reverse("logistique:logistique-record-payment-execution", args=[order.pk]),
        {
            "echeance_id": installment.pk,
            "date_paiement": timezone.localdate().isoformat(),
            "montant_paye": str(installment.montant_prevu),
            "reference_paiement": "BANK-TEST",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    with patch("logistique.tasks.queue_purchase_creator_email") as notify:
        with callbacks(execute=True):
            response = accountant.post(
                reverse("logistique:logistique-validate-payment", args=[order.pk]),
                {
                    "echeance_id": installment.pk,
                    "swift_file": SimpleUploadedFile(
                        "proof.pdf", b"%PDF-1.4 proof", content_type="application/pdf"
                    ),
                },
                format="multipart",
            )
        assert response.status_code == 200, response.data
        notify.assert_called_once_with(installment.pk)
    installment.refresh_from_db()
    order.refresh_from_db()
    return response


def ready_for_shipping(ctx, **overrides):
    order = validated_dossier(ctx, condition="receipt100", **overrides)
    result = purchase_post(
        ctx,
        order,
        "progression",
        confirmer_production=True,
        date_expedition_prevue=(timezone.localdate() + timedelta(days=2)).isoformat(),
    )
    assert result.status_code == 200, result.data
    return order


def record_shipment(ctx, order):
    result = purchase_post(
        ctx,
        order,
        "progression",
        date_expedition_reelle=timezone.localdate().isoformat(),
    )
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.statut == "Expédition"


def service_dossier(ctx):
    service = Article.objects.create(
        company=ctx.company,
        reference="ONLY-SERVICE",
        designation="Prestation fournisseur",
        type_article="service",
        prix_achat=100,
        prix_vente=120,
        tva=0,
    )
    return ready_for_shipping(
        ctx,
        lignes=json.dumps(
            [{"article": service.pk, "quantity": "1", "prix_achat": "100.01"}]
        ),
    )


def closed_paid_dossier(ctx):
    order = validated_dossier(ctx, condition="receipt100")
    item = order.echeances_paiement.get()
    item.montant_paye = item.montant_prevu
    item.paiement_valide_le = timezone.now()
    item.paiement_valide_par = ctx.accountant
    item.statut_traitement = "Paiement validé"
    item.justificatif_file = SimpleUploadedFile(
        "paid-proof.pdf", b"%PDF-1.4 paid", content_type="application/pdf"
    )
    item.save()
    order.production_confirmee_le = timezone.now()
    order.date_expedition_prevue = timezone.localdate()
    order.date_expedition_reelle = timezone.localdate()
    order.date_reelle = timezone.localdate()
    order.lignes.update(received_quantity=2)
    order.statut_paiement = "Validé"
    order.statut = "Clôture"
    order.statut_global = "Clôturé"
    order.save()
    return order, item


def received_dossier(ctx):
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    complete_transit(ctx, order)
    line = order.lignes.get()
    result = purchase_post(
        ctx,
        order,
        "reception",
        lines=[
            {
                "logistics_line": line.pk,
                "article": ctx.article.pk,
                "emplacement": ctx.location.pk,
                "quantity": str(line.quantity),
            }
        ],
    )
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    receipt = StockReceipt.objects.select_related("logistics_order").get(
        logistics_order=order
    )
    return order, receipt


def close_received_dossier(ctx, order):
    item = order.echeances_paiement.get()
    item.montant_paye = item.montant_prevu
    item.paiement_valide_le = timezone.now()
    item.save()
    order.statut_paiement = "Validé"
    order.save(update_fields=["statut_paiement"])
    assert (
        purchase_post(ctx, order, "progression", statut="Livraison client").status_code
        == 200
    )
    result = purchase_post(ctx, order, "progression", statut="Clôture")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.statut == "Clôture"


def partial_receipt(ctx, order, reference, note):
    complete_transit(ctx, order)
    line = order.lignes.get()
    result = purchase_post(
        ctx,
        order,
        "reception",
        reference=reference,
        note=note,
        lines=[
            {
                "logistics_line": line.pk,
                "article": ctx.article.pk,
                "emplacement": ctx.location.pk,
                "quantity": "1.000",
            }
        ],
    )
    assert result.status_code == 200, result.data
    return result
