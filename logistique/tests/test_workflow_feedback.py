from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from logistique.models import LogisticsOrder
from logistique.purchase_serializers import PurchaseProgressSerializer
from logistique.realtime import broadcast_logistics_change
from logistique.tasks import _build_accounting_email
from logistique.tests.helpers import (
    create_dossier,
    proforma_payload,
    received_dossier,
    validated_dossier,
    purchase_post,
)
from logistique.utils import get_next_numero_logistique

pytestmark = pytest.mark.django_db


def pdf(name="receipt.pdf", content=b"%PDF-1.4 receipt"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def test_com_number_sequence_is_numeric_and_continues_legacy(purchase_context):
    ctx = purchase_context
    year = timezone.localdate().year % 100
    for reference in [f"LOG999/{year:02d}", f"COM1000/{year:02d}"]:
        LogisticsOrder.objects.create(company=ctx.company, numero_commande=reference)
    assert get_next_numero_logistique(ctx.company.pk) == f"COM1001/{year:02d}"
    assert create_dossier(ctx).numero_commande == f"COM1001/{year:02d}"


def test_proforma_save_validates_without_decision(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    payload = proforma_payload(ctx)
    payload.pop("decision")
    result = ctx.api.post(
        reverse("logistique:logistique-purchase", args=[order.pk]),
        payload,
        format="multipart",
    )
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.is_proforma_step_complete
    assert order.echeances_paiement.count() == 2
    assert result.data["workflow"]["etape_courante"] == "titre"


@pytest.mark.parametrize("end,expected", [("2026-12-31", 200), ("2026-10-31", 400)])
def test_title_validity_range(purchase_context, end, expected):
    ctx = purchase_context
    order = validated_dossier(ctx, with_title=False)
    result = purchase_post(
        ctx,
        order,
        "titre",
        date_validite_titre_du="2026-11-01",
        date_validite_titre_au=end,
    )
    assert result.status_code == expected, result.data
    order.refresh_from_db()
    if expected == 200:
        assert order.date_validite_titre_du.isoformat() == "2026-11-01"
        assert order.date_validite_titre_au.isoformat() == end
    else:
        assert "date_validite_titre_au" in result.data["details"]


def test_mad_costs_separate_cash_and_exclude_supplier_tva(purchase_context):
    order = validated_dossier(purchase_context)
    order.cout_achat_mad = Decimal("1100")
    order.cout_transport = Decimal("50")
    order.frais_transit = Decimal("20")
    order.frais_douane = Decimal("30")
    order.tva = Decimal("999")
    order.autres_frais_virement_actif = True
    order.autres_frais_virement = Decimal("40")
    order.autres_frais_cash_actif = True
    order.autres_frais_cash = Decimal("60")
    order.save()
    order.refresh_from_db()
    assert order.cout_achat == Decimal("100")
    assert order.cout_total == Decimal("1240")
    assert order.cout_total_avec_cash == Decimal("1300")


def test_disabled_optional_charges_cannot_affect_totals(purchase_context):
    order = validated_dossier(purchase_context)
    serializer = PurchaseProgressSerializer(
        data={
            "autres_frais_cash_actif": False,
            "autres_frais_cash": "100",
            "description_frais_cash": "old",
            "autres_frais_virement_actif": False,
            "autres_frais_virement": "200",
        },
        context={"order": order},
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["autres_frais_cash"] == 0
    assert serializer.validated_data["autres_frais_virement"] == 0
    assert serializer.validated_data["description_frais_cash"] == ""


@pytest.mark.parametrize(
    "hours,overdue", [(6, False), (23.99, False), (24, True), (24.01, True)]
)
def test_reminders_wait_a_full_24_hours_across_midnight(
    purchase_context, hours, overdue
):
    order = create_dossier(purchase_context)
    start = timezone.make_aware(datetime(2026, 11, 12, 18, 0))
    order.date_created = start
    order.date_prevue = start.date()
    order.prochaine_relance_proforma = start.date()
    order.proforma_demandee_le = start
    order.statut_proforma_conformite = "En attente"
    with patch(
        "logistique.models.timezone.now", return_value=start + timedelta(hours=hours)
    ):
        assert order.is_delivery_overdue is overdue
        assert order.is_proforma_follow_up_overdue is overdue


def test_accounting_email_attaches_actual_supplier_and_import_documents(
    purchase_context,
):
    order = validated_dossier(purchase_context)
    order.titre_importation_file = pdf("import-title.pdf", b"%PDF-1.4 import title")
    order.save()
    email = _build_accounting_email(order, [purchase_context.accountant.email])
    assert len(email.attachments) == 3
    contents = [item[1] for item in email.attachments]
    assert b"%PDF-1.4 supplier" in contents
    assert b"%PDF-1.4 import title" in contents


def test_reception_document_is_retained_with_filename(purchase_context):
    ctx = purchase_context
    order, _ = received_dossier(ctx)
    # The no-stock reception progression also accepts the optional receipt document.
    ctx.company.stock_management_enabled = False
    ctx.company.save()
    order.company = ctx.company
    order.bon_reception_file = pdf("bon-reception.pdf")
    order.save()
    response = ctx.api.get(reverse("logistique:logistique-detail", args=[order.pk]))
    assert response.status_code == 200, response.data
    document = next(
        item for item in response.data["documents"] if item["etape"] == "reception"
    )
    assert document["nom"] == "bon-reception.pdf"
    assert document["etape_label"] == "Réception des marchandises"


def test_live_event_is_after_commit(
    purchase_context, django_capture_on_commit_callbacks
):
    order = create_dossier(purchase_context)
    with patch("logistique.realtime.broadcast_logistics_change") as broadcast:
        with django_capture_on_commit_callbacks(execute=True):
            order.save(update_fields=["date_updated"])
            broadcast.assert_not_called()
        broadcast.assert_called_once_with(order.pk, order.company_id)


def test_live_event_recipients_are_scoped_to_company(purchase_context):
    ctx = purchase_context
    send = AsyncMock()
    with patch(
        "logistique.realtime.get_channel_layer",
        return_value=SimpleNamespace(group_send=send),
    ):
        broadcast_logistics_change(5, ctx.company.pk)
    recipients = {call.args[0] for call in send.call_args_list}
    assert str(ctx.creator.pk) in recipients
    assert str(ctx.accountant.pk) in recipients
    assert str(ctx.outsider.pk) not in recipients
    assert all(
        call.args[1]["message"]
        == {"type": "LOGISTICS_UPDATED", "id": 5, "company_id": ctx.company.pk}
        for call in send.call_args_list
    )


@pytest.mark.parametrize("brand", [None, "missing"])
def test_article_requires_brand_in_logistics_creation(purchase_context, brand):
    ctx = purchase_context
    order = create_dossier(ctx)
    payload = {
        "reference": "NEW-LOG-ARTICLE",
        "designation": "Article",
        "type_article": "Produit",
        "company": ctx.company.pk,
        "emplacement": ctx.location.pk,
        "logistics_order": order.pk,
    }
    if brand is None:
        payload["marque"] = None
    response = ctx.api.post(
        reverse("article:article-list-create"), payload, format="json"
    )
    assert response.status_code == 400, response.data
    assert "marque" in response.data["details"]


def test_logistics_article_creation_requires_own_active_dossier(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    payload = {
        "reference": "NEW-LOG-ARTICLE",
        "designation": "Article",
        "type_article": "Produit",
        "company": ctx.company.pk,
        "emplacement": ctx.location.pk,
        "marque": ctx.brand.pk,
    }
    assert (
        ctx.api.post(
            reverse("article:article-list-create"), payload, format="json"
        ).status_code
        == 403
    )
    response = ctx.api.post(
        reverse("article:article-list-create"),
        {**payload, "logistics_order": order.pk},
        format="json",
    )
    assert response.status_code == 201, response.data
    payload["reference"] = "FOREIGN-ARTICLE"
    assert (
        ctx.api.post(
            reverse("article:article-list-create"),
            {**payload, "company": ctx.foreign.pk, "logistics_order": order.pk},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.parametrize("hours,overdue", [(6, False), (23.99, False), (24, True)])
def test_payment_deadline_preserves_request_time(purchase_context, hours, overdue):
    order = validated_dossier(purchase_context)
    installment = order.echeances_paiement.get(declencheur="advance")
    start = timezone.make_aware(datetime(2026, 11, 12, 18))
    installment.demandee_le = start
    installment.date_echeance = start.date()
    installment.save()
    with patch(
        "logistique.models.timezone.now", return_value=start + timedelta(hours=hours)
    ):
        assert order.is_payment_overdue is overdue


def test_closed_dossier_keeps_replaced_files_and_both_accounting_proofs(
    purchase_context,
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    original = order.proforma_fournisseur_file.name
    order.proforma_fournisseur_file = pdf("replacement-proforma.pdf")
    order.justificatifs_file = pdf("transit-fees.pdf")
    order.statut = "Transit"
    order.save()
    for item in order.echeances_paiement.all():
        item.justificatif_file = pdf(f"{item.declencheur}-proof.pdf")
        item.save()
    order.bon_reception_file = pdf("reception.pdf")
    order.statut = "Clôture"
    order.save()
    response = ctx.api.get(reverse("logistique:logistique-detail", args=[order.pk]))
    assert response.status_code == 200, response.data
    documents = response.data["documents"]
    assert {
        "supplier.pdf",
        "replacement-proforma.pdf",
        "transit-fees.pdf",
        "advance-proof.pdf",
        "scheduled-proof.pdf",
        "reception.pdf",
    } <= {item["nom"] for item in documents}
    assert {"proforma", "titre", "transit", "paiement", "solde", "reception"} <= {
        item["etape"] for item in documents
    }


def test_receipt_accepts_pdf_and_json_lines_in_one_multipart_request(purchase_context):
    import json
    from logistique.tests.helpers import (
        ready_for_shipping,
        record_shipment,
        complete_transit,
    )

    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    complete_transit(ctx, order)
    line = order.lignes.get()
    response = ctx.api.post(
        reverse("logistique:logistique-purchase", args=[order.pk]),
        {
            "action": "reception",
            "reference": "QA-RECEIPT",
            "bon_reception_file": pdf(),
            "lines": json.dumps(
                [
                    {
                        "logistics_line": line.pk,
                        "article": ctx.article.pk,
                        "quantity": "2",
                        "emplacement": ctx.location.pk,
                    }
                ]
            ),
        },
        format="multipart",
    )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.bon_reception_file.name.endswith("receipt.pdf")
    assert order.lignes.get().received_quantity == Decimal("2")


def test_receipt_file_validation_also_applies_to_generic_updates(purchase_context):
    from logistique.serializers import LogisticsOrderUpdateSerializer

    order = create_dossier(purchase_context)
    serializer = LogisticsOrderUpdateSerializer(
        order,
        data={
            "bon_reception_file": SimpleUploadedFile(
                "danger.exe", b"data", content_type="application/octet-stream"
            )
        },
        partial=True,
    )
    assert not serializer.is_valid()
    assert "bon_reception_file" in serializer.errors


def test_cost_breakdown_uses_mad_purchase_cost_and_excludes_cash_and_vat(
    purchase_context,
):
    from logistique.stats import get_logistics_stats

    order = validated_dossier(purchase_context)
    order.cout_achat_mad = Decimal("440")
    order.autres_frais_virement_actif = True
    order.autres_frais_virement = Decimal("40")
    order.autres_frais_cash_actif = True
    order.autres_frais_cash = Decimal("60")
    order.tva = Decimal("999")
    order.save()
    stats = get_logistics_stats(order.company_id)
    assert stats["couts_detail"]["achat"] == Decimal("440")
    assert stats["couts_detail"]["autres"] == Decimal("40")
    assert stats["couts_detail"]["tva"] == Decimal("0")
    assert stats["couts_detail"]["total"] == Decimal("480")
    response = purchase_context.api.get(reverse("logistique:logistique-list-create"), {"company_id": order.company_id, "pagination": "true"})
    assert response.status_code == 200, response.data
    assert response.data["results"][0]["cout_achat_mad"] == "440.00"


def test_cost_migration_separates_foreign_purchase_and_retains_legacy_totals(
    purchase_context,
):
    from django.apps import apps
    from importlib import import_module

    ctx = purchase_context
    order = validated_dossier(ctx)
    order.cout_achat_mad = Decimal("440")
    order.autres_frais_virement_actif = True
    order.autres_frais_virement = Decimal("40")
    order.autres_frais_cash_actif = True
    order.autres_frais_cash = Decimal("60")
    order.tva = Decimal("999")
    order.save()
    history_count = order.history.count()
    LogisticsOrder.objects.filter(pk=order.pk).update(cout_total=Decimal("9999"))
    legacy = LogisticsOrder.objects.create(
        company=ctx.company, numero_commande="LEGACY-COST", cout_total=Decimal("123")
    )
    import_module(
        "logistique.migrations.0025_dossier_com_references"
    ).normalize_supplier_costs(apps, None)
    order.refresh_from_db()
    legacy.refresh_from_db()
    assert order.cout_total == Decimal("480")
    assert order.cout_total_avec_cash == Decimal("540")
    assert order.cout_achat == Decimal("100")
    assert order.history.count() == history_count
    assert legacy.cout_total == Decimal("123")
