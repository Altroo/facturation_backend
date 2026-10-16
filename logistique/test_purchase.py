"""Supplier purchase dossiers, payment gates and company isolation contracts."""

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from company.models import Company
from parameter.models import Emplacement, Marque
from stock.models import StockBalance, StockMovement, StockReceipt
from stock.services import incoming_quantity

from .models import LogisticsOrder
from .purchase import payment_blocker, preparation_blocker
from .tasks import deliver_purchase_creator_email

pytestmark = pytest.mark.django_db


def authenticated(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def purchase_context(settings, tmp_path):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MEDIA_ROOT = tmp_path
    company = Company.objects.create(
        raison_sociale="Supplier workflow", ICE="SUP-001", stock_management_enabled=True
    )
    foreign = Company.objects.create(raison_sociale="Other company", ICE="SUP-002")

    def member(email, role, owner=company):
        user = CustomUser.objects.create_user(email=email, password="test-only")
        Membership.objects.create(
            user=user, company=owner, role=Role.objects.get_or_create(name=role)[0]
        )
        return user

    creator = member("creator@example.invalid", "Logistique")
    responsible = member("responsible@example.invalid", "Logistique")
    accountant = member("accountant@example.invalid", "Comptable")
    reader = member("reader@example.invalid", "Lecture")
    outsider = member("outsider@example.invalid", "Logistique", foreign)
    location = Emplacement.objects.create(company=company, nom="Dépôt principal")
    foreign_location = Emplacement.objects.create(
        company=foreign, nom="Other warehouse"
    )
    brand = Marque.objects.create(
        company=company, nom="Supplier brand", email="supplier@example.invalid"
    )
    article = Article.objects.create(
        company=company,
        reference="SUP-ARTICLE",
        designation="Article fournisseur",
        type_article="produit",
        emplacement=location,
        prix_achat="5.00",
        prix_vente="9.00",
        tva=0,
    )
    foreign_article = Article.objects.create(
        company=foreign,
        reference="FOREIGN",
        designation="Private article",
        type_article="produit",
        emplacement=foreign_location,
        prix_achat=1,
        prix_vente=2,
        tva=0,
    )
    balance = StockBalance.objects.create(
        company=company, article=article, emplacement=location
    )
    return SimpleNamespace(
        company=company,
        foreign=foreign,
        creator=creator,
        responsible=responsible,
        accountant=accountant,
        reader=reader,
        outsider=outsider,
        location=location,
        foreign_location=foreign_location,
        brand=brand,
        article=article,
        foreign_article=foreign_article,
        balance=balance,
        api=authenticated(creator),
    )


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


def validated_dossier(ctx, **overrides):
    order = create_dossier(ctx)
    response = save_proforma(ctx, order, **overrides)
    assert response.status_code == 200, response.data
    return order


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


def test_creation_has_no_sales_source_and_date_is_optional(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    assert order.is_supplier_purchase
    assert order.date_prevue is None
    assert order.created_by_user == ctx.creator
    assert order.responsable == ctx.responsible
    assert order.fournisseur_email == ctx.brand.email
    assert not order.proformas.exists()
    assert not order.lignes.exists()
    assert not order.echeances_paiement.exists()
    response = ctx.api.get(reverse("logistique:logistique-detail", args=[order.pk]))
    assert response.status_code == 200
    assert response.data["date_prevue"] is None


@pytest.mark.parametrize("role", ["reader", "outsider"])
def test_creation_and_changes_respect_permissions(purchase_context, role):
    ctx = purchase_context
    order = create_dossier(ctx)
    client = authenticated(getattr(ctx, role))
    created = client.post(
        reverse("logistique:logistique-list-create"),
        {"company_id": ctx.company.pk, "fournisseur": "Forbidden"},
        format="json",
    )
    modified = purchase_post(
        ctx, order, "dossier", client=client, fournisseur="Forbidden"
    )
    assert created.status_code == 403
    assert modified.status_code == 403
    order.refresh_from_db()
    assert order.fournisseur != "Forbidden"
    assert LogisticsOrder.objects.count() == 1
    read = client.get(reverse("logistique:logistique-detail", args=[order.pk]))
    assert read.status_code == (200 if role == "reader" else 403)


@pytest.mark.parametrize("field", ["marque", "responsable"])
def test_creation_rejects_foreign_brand_and_responsible(purchase_context, field):
    ctx = purchase_context
    value = (
        ctx.outsider.pk
        if field == "responsable"
        else Marque.objects.create(company=ctx.foreign, nom="Private supplier").pk
    )
    response = ctx.api.post(
        reverse("logistique:logistique-list-create"),
        {"company_id": ctx.company.pk, "fournisseur": "Supplier", field: value},
        format="json",
    )
    assert response.status_code == 400
    assert not LogisticsOrder.objects.exists()


@pytest.mark.parametrize(
    "condition,parts",
    [
        ("documentary100", [(100, "Remise documentaire", "documentary")]),
        ("advance30_lc70", [(30, "Virement", "advance"), (70, "LC", "scheduled")]),
        (
            "advance30_documentary70",
            [(30, "Virement", "advance"), (70, "Remise documentaire", "documentary")],
        ),
        ("advance100", [(100, "Virement", "advance")]),
        (
            "advance30_transfer70",
            [(30, "Virement", "advance"), (70, "Virement", "scheduled")],
        ),
        ("receipt100", [(100, "Virement", "receipt")]),
        ("shipment100", [(100, "Virement", "shipment")]),
    ],
)
def test_seven_conditions_create_exact_payment_schedule(
    purchase_context, condition, parts
):
    order = validated_dossier(purchase_context, condition=condition)
    installments = list(order.echeances_paiement.order_by("pk"))
    assert [
        (int(item.pourcentage), item.methode_paiement, item.declencheur)
        for item in installments
    ] == parts
    assert sum((item.montant_prevu for item in installments), Decimal("0")) == Decimal(
        "100.01"
    )
    assert all(item.devise == "EUR" for item in installments)
    assert order.payment_total == Decimal("100.01")
    if len(installments) == 2:
        assert [item.montant_prevu for item in installments] == [
            Decimal("30.00"),
            Decimal("70.01"),
        ]


@pytest.mark.parametrize("currency", ["EUR", "USD"])
@pytest.mark.parametrize(
    "total,expected", [("17999.99", 200), ("18000.00", 400), ("18000.01", 400)]
)
def test_advance100_threshold_is_strict_and_in_supplier_currency(
    purchase_context, currency, total, expected
):
    order = create_dossier(purchase_context)
    response = save_proforma(
        purchase_context, order, condition="advance100", total=total, currency=currency
    )
    assert response.status_code == expected, response.data
    if expected == 200:
        item = order.echeances_paiement.get()
        assert item.montant_prevu == Decimal(total)
        assert item.devise == currency
    else:
        assert not order.echeances_paiement.exists()
        assert not order.is_proforma_step_complete


def test_supplier_lines_are_independent_snapshots(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx)
    line = order.lignes.get()
    assert line.quantity == Decimal("2.000")
    assert line.prix_achat == Decimal("50.00")
    assert (
        line.proforma_id is None
        and line.source_line_id is None
        and line.client_id is None
    )
    assert line.expected_emplacement == ctx.location
    ctx.article.refresh_from_db()
    assert ctx.article.prix_achat == Decimal("5.00")
    assert not order.proformas.exists()


@pytest.mark.parametrize("foreign_field", ["article", "expected_emplacement"])
def test_supplier_line_cross_company_rejected_atomically(
    purchase_context, foreign_field
):
    ctx = purchase_context
    order = create_dossier(ctx)
    line = {"article": ctx.article.pk, "quantity": "1", "prix_achat": "100.00"}
    line[foreign_field] = (
        ctx.foreign_article.pk
        if foreign_field == "article"
        else ctx.foreign_location.pk
    )
    response = save_proforma(ctx, order, lignes=json.dumps([line]))
    assert response.status_code == 400, response.data
    assert not order.lignes.exists()
    assert not order.echeances_paiement.exists()


def test_unvalidated_proforma_is_not_incoming_stock(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    response = save_proforma(ctx, order, decision="control")
    assert response.status_code == 200, response.data
    assert incoming_quantity(ctx.balance) == 0
    response = save_proforma(ctx, order)
    assert response.status_code == 200, response.data
    assert incoming_quantity(ctx.balance) == Decimal("2.000")
    assert not StockMovement.objects.exists()


def test_production_requires_validated_and_forwarded_advance_only(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="advance30_lc70")
    data = {
        "confirmer_production": True,
        "date_expedition_prevue": (
            timezone.localdate() + timedelta(days=10)
        ).isoformat(),
    }
    assert purchase_post(ctx, order, "progression", **data).status_code == 400
    advance = order.echeances_paiement.get(declencheur="advance")
    advance.paiement_valide_le = timezone.now()
    advance.save()
    assert purchase_post(ctx, order, "progression", **data).status_code == 400
    advance.preuve_envoyee_fournisseur_le = timezone.now()
    advance.save()
    response = purchase_post(ctx, order, "progression", **data)
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.statut == "Production"
    assert not order.is_payment_step_complete
    assert not order.echeances_paiement.get(declencheur="scheduled").paiement_valide_le


@pytest.mark.parametrize("condition", ["documentary100", "receipt100", "shipment100"])
def test_deferred_conditions_allow_production_without_payment(
    purchase_context, condition
):
    ctx = purchase_context
    order = validated_dossier(ctx, condition=condition)
    response = purchase_post(
        ctx,
        order,
        "progression",
        confirmer_production=True,
        date_expedition_prevue=(timezone.localdate() + timedelta(days=2)).isoformat(),
    )
    assert response.status_code == 200, response.data
    assert preparation_blocker(order) == ""


def test_documentary_payment_requires_arrival_and_bank_documents(purchase_context):
    order = validated_dossier(purchase_context, condition="documentary100")
    item = order.echeances_paiement.get()
    assert payment_blocker(order, item)
    order.date_arrivee_maroc = timezone.localdate()
    assert payment_blocker(order, item)
    order.documents_remis_banque_le = timezone.localdate()
    assert payment_blocker(order, item) == ""


def test_shipment_payment_waits_for_real_shipment(purchase_context):
    order = validated_dossier(purchase_context, condition="shipment100")
    item = order.echeances_paiement.get()
    order.date_expedition_prevue = timezone.localdate()
    assert payment_blocker(order, item)
    order.date_expedition_reelle = timezone.localdate()
    assert payment_blocker(order, item) == ""


def test_receipt_payment_waits_for_full_product_quantities(purchase_context):
    order = validated_dossier(purchase_context, condition="receipt100")
    item = order.echeances_paiement.get()
    order.date_reelle = timezone.localdate()
    line = order.lignes.get()
    line.received_quantity = Decimal("1")
    line.save()
    assert payment_blocker(order, item)
    line.received_quantity = line.quantity
    line.save()
    assert payment_blocker(order, item) == ""


def test_each_payment_notifies_creator_once_and_keeps_logistics_phase(
    purchase_context, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    prepare_title(order)
    order.statut = "Transit"
    order.save(update_fields=["statut"])
    for item in order.echeances_paiement.order_by("pk"):
        request_installment(ctx, order, item, django_capture_on_commit_callbacks)
        assert order.statut == "Transit"
        execute_installment(ctx, order, item, django_capture_on_commit_callbacks)
        assert order.statut == "Transit"
        assert deliver_purchase_creator_email(item.pk) is True
        assert deliver_purchase_creator_email(item.pk) is False
        message = mail.outbox[-1]
        assert message.to == [ctx.creator.email]
        assert ctx.responsible.email not in message.to
        assert len(message.attachments) == 1
    assert len(mail.outbox) == 2
    assert order.solde_restant == 0
    assert order.statut_paiement == "Validé"


def test_only_assigned_accountant_can_execute_and_creator_can_mark_forwarded(
    purchase_context, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    prepare_title(order)
    item = order.echeances_paiement.get(declencheur="advance")
    request_installment(ctx, order, item, django_capture_on_commit_callbacks)
    denied = ctx.api.post(
        reverse("logistique:logistique-start-payment", args=[order.pk]),
        {"echeance_id": item.pk},
        format="json",
    )
    assert denied.status_code == 403
    execute_installment(ctx, order, item, django_capture_on_commit_callbacks)
    url = reverse("logistique:logistique-send-swift", args=[order.pk])
    data = {"echeance_id": item.pk, "email_envoye": True}
    assert (
        authenticated(ctx.responsible).post(url, data, format="json").status_code == 403
    )
    response = ctx.api.post(url, data, format="json")
    assert response.status_code == 200, response.data
    item.refresh_from_db()
    assert item.preuve_envoyee_fournisseur_le


def test_implicit_article_location_cannot_belong_to_another_company(purchase_context):
    ctx = purchase_context
    ctx.article.emplacement = ctx.foreign_location
    ctx.article.save(update_fields=["emplacement"])
    order = create_dossier(ctx)
    response = save_proforma(ctx, order)
    assert response.status_code == 400, response.data
    assert not order.lignes.exists()


def test_schedule_half_cent_rounding_preserves_the_exact_total(purchase_context):
    order = validated_dossier(purchase_context, total="0.05")
    assert list(
        order.echeances_paiement.order_by("pk").values_list("montant_prevu", flat=True)
    ) == [Decimal("0.02"), Decimal("0.03")]


@pytest.mark.parametrize("condition", ["documentary100", "shipment100", "receipt100"])
def test_deferred_payment_request_is_blocked_until_its_event(
    purchase_context, condition
):
    ctx = purchase_context
    order = validated_dossier(ctx, condition=condition)
    prepare_title(order)
    item = order.echeances_paiement.get()
    client = authenticated(ctx.responsible)
    url = reverse("logistique:logistique-request-payment", args=[order.pk])
    data = {"echeance_id": item.pk, "date_echeance": timezone.localdate().isoformat()}
    response = client.post(url, data, format="json")
    assert response.status_code == 400, response.data
    item.refresh_from_db()
    assert item.demandee_le is None
    if condition == "documentary100":
        order.date_arrivee_maroc = timezone.localdate()
        order.documents_remis_banque_le = timezone.localdate()
    elif condition == "shipment100":
        order.date_expedition_reelle = timezone.localdate()
    else:
        order.date_reelle = timezone.localdate()
        order.lignes.update(received_quantity=2)
    order.save()
    response = client.post(url, data, format="json")
    assert response.status_code == 200, response.data


def test_partial_receipts_and_service_lines_preserve_stock_and_completion(
    purchase_context,
):
    ctx = purchase_context
    service = Article.objects.create(
        company=ctx.company,
        reference="SERVICE",
        designation="Transport fournisseur",
        type_article="service",
        prix_achat=0,
        prix_vente=0,
        tva=0,
    )
    lines = [
        {"article": ctx.article.pk, "quantity": "2", "prix_achat": "50.00"},
        {"article": service.pk, "quantity": "1", "prix_achat": "0.00"},
    ]
    order = validated_dossier(ctx, condition="receipt100", lignes=json.dumps(lines))
    result = purchase_post(
        ctx,
        order,
        "progression",
        confirmer_production=True,
        date_expedition_prevue=(timezone.localdate() + timedelta(days=2)).isoformat(),
    )
    assert result.status_code == 200, result.data
    result = purchase_post(
        ctx,
        order,
        "progression",
        statut="Expédition",
        date_expedition_reelle=timezone.localdate().isoformat(),
    )
    assert result.status_code == 200, result.data
    line = order.lignes.get(article=ctx.article)
    for index in (1, 2):
        result = purchase_post(
            ctx,
            order,
            "reception",
            lines=[
                {
                    "logistics_line": line.pk,
                    "article": ctx.article.pk,
                    "emplacement": ctx.location.pk,
                    "quantity": "1",
                }
            ],
        )
        assert result.status_code == 200, result.data
        ctx.balance.refresh_from_db()
        order.refresh_from_db()
        assert ctx.balance.physical_quantity == index
        assert StockMovement.objects.filter(movement_type="receipt").count() == index
        if index == 1:
            assert order.date_reelle is None
            assert payment_blocker(order, order.echeances_paiement.get())
    assert order.date_reelle == timezone.localdate()
    assert order.statut == "Réception locale"
    assert payment_blocker(order, order.echeances_paiement.get()) == ""
    result = purchase_post(
        ctx,
        order,
        "reception",
        lines=[
            {
                "logistics_line": line.pk,
                "article": ctx.article.pk,
                "emplacement": ctx.location.pk,
                "quantity": "1",
            }
        ],
    )
    assert result.status_code == 400, result.data
    assert StockReceipt.objects.count() == 2
    assert StockMovement.objects.count() == 2


def test_postponing_an_overdue_shipment_requires_an_explanation(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="documentary100")
    order.production_confirmee_le = timezone.now()
    order.date_expedition_prevue = timezone.localdate() - timedelta(days=1)
    order.statut = "Production"
    order.save()
    new_date = timezone.localdate() + timedelta(days=3)
    response = purchase_post(
        ctx, order, "progression", date_expedition_prevue=new_date.isoformat()
    )
    assert response.status_code == 400, response.data
    order.refresh_from_db()
    assert order.date_expedition_prevue < timezone.localdate()
    response = purchase_post(
        ctx,
        order,
        "progression",
        date_expedition_prevue=new_date.isoformat(),
        remarque="Production fournisseur retardée de trois jours",
    )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.date_expedition_prevue == new_date
    assert order.process_notes.filter(remarque__contains="retardée").exists()


def test_import_title_extraction_is_a_preview_without_persistence(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    expected = {"fields": {"banque": "Banque lue"}, "warnings": []}
    with patch("logistique.import_title.extract_import_title", return_value=expected):
        response = ctx.api.post(
            reverse("logistique:logistique-extract-title", args=[order.pk]),
            {
                "file": SimpleUploadedFile(
                    "titre.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                )
            },
            format="multipart",
        )
    assert response.status_code == 200, response.data
    assert response.data == expected
    order.refresh_from_db()
    assert order.banque == ""
    assert not order.titre_importation_file


@pytest.mark.parametrize("role", ["reader", "outsider"])
def test_import_title_extraction_respects_dossier_permissions(purchase_context, role):
    ctx = purchase_context
    order = create_dossier(ctx)
    with patch("logistique.import_title.extract_import_title") as extract:
        response = authenticated(getattr(ctx, role)).post(
            reverse("logistique:logistique-extract-title", args=[order.pk]),
            {
                "file": SimpleUploadedFile(
                    "titre.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                )
            },
            format="multipart",
        )
    assert response.status_code == 403
    extract.assert_not_called()


@pytest.mark.parametrize(
    "condition", ["advance30_lc70", "advance30_documentary70", "advance30_transfer70"]
)
def test_cent_total_never_creates_an_unpayable_zero_advance(
    purchase_context, condition
):
    order = validated_dossier(purchase_context, condition=condition, total="0.01")
    items = list(order.echeances_paiement.all())
    assert items
    assert all(item.montant_prevu > 0 for item in items)
    assert sum((item.montant_prevu for item in items), Decimal("0")) == Decimal("0.01")
    assert preparation_blocker(order) == ""


def test_payment_validation_replay_does_not_notify_twice(
    purchase_context, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    prepare_title(order)
    item = order.echeances_paiement.get(declencheur="advance")
    request_installment(ctx, order, item, django_capture_on_commit_callbacks)
    execute_installment(ctx, order, item, django_capture_on_commit_callbacks)
    with patch("logistique.tasks.queue_purchase_creator_email") as notify:
        with django_capture_on_commit_callbacks(execute=True):
            response = authenticated(ctx.accountant).post(
                reverse("logistique:logistique-validate-payment", args=[order.pk]),
                {
                    "echeance_id": item.pk,
                    "swift_file": SimpleUploadedFile(
                        "proof-again.pdf",
                        b"%PDF-1.4 duplicate",
                        content_type="application/pdf",
                    ),
                },
                format="multipart",
            )
    assert response.status_code == 400, response.data
    notify.assert_not_called()


def test_logistics_user_can_create_and_update_supplier_directory(purchase_context):
    ctx = purchase_context
    url = (
        reverse("logistique:logistique-supplier-directory")
        + f"?company_id={ctx.company.pk}"
    )
    response = ctx.api.post(
        url,
        {"nom": "Nouvelle marque fournisseur", "email": "brand@example.invalid"},
        format="json",
    )
    assert response.status_code == 200, response.data
    brand = Marque.objects.get(pk=response.data["id"])
    assert brand.company_id == ctx.company.pk
    assert brand.email == "brand@example.invalid"
    response = ctx.api.post(
        url,
        {
            "id": brand.pk,
            "nom": brand.nom,
            "email": "updated@example.invalid",
            "company": ctx.foreign.pk,
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    brand.refresh_from_db()
    assert brand.email == "updated@example.invalid"
    assert brand.company_id == ctx.company.pk


@pytest.mark.parametrize("actor", ["reader", "outsider"])
def test_supplier_directory_requires_company_and_write_access(purchase_context, actor):
    ctx = purchase_context
    url = (
        reverse("logistique:logistique-supplier-directory")
        + f"?company_id={ctx.company.pk}"
    )
    response = authenticated(getattr(ctx, actor)).post(
        url,
        {"nom": "Forbidden brand", "email": "secret@example.invalid"},
        format="json",
    )
    assert response.status_code == 403
    assert not Marque.objects.filter(nom="Forbidden brand").exists()


def test_supplier_directory_rejects_foreign_brand_identifier(purchase_context):
    ctx = purchase_context
    brand = Marque.objects.create(
        company=ctx.foreign, nom="Private brand", email="private@example.invalid"
    )
    response = ctx.api.post(
        reverse("logistique:logistique-supplier-directory")
        + f"?company_id={ctx.company.pk}",
        {"id": brand.pk, "nom": "Changed", "email": "changed@example.invalid"},
        format="json",
    )
    assert response.status_code == 400, response.data
    brand.refresh_from_db()
    assert brand.nom == "Private brand"
    assert brand.email == "private@example.invalid"


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


@pytest.mark.parametrize("phase", ["Transit", "Dédouanement"])
def test_stock_can_be_received_from_the_transit_or_customs_phase(
    purchase_context, phase
):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    result = purchase_post(ctx, order, "progression", statut=phase)
    assert result.status_code == 200, result.data
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
    ctx.balance.refresh_from_db()
    assert order.statut == "Réception locale"
    assert order.date_reelle == timezone.localdate()
    assert ctx.balance.physical_quantity == line.quantity
    assert StockMovement.objects.count() == 1


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


def test_service_only_receipt_is_confirmed_without_a_stock_movement(purchase_context):
    ctx = purchase_context
    order = service_dossier(ctx)
    record_shipment(ctx, order)
    assert payment_blocker(order, order.echeances_paiement.get())
    result = purchase_post(
        ctx,
        order,
        "progression",
        date_reelle=timezone.localdate().isoformat(),
        statut="Réception locale",
    )
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.date_reelle == timezone.localdate()
    assert payment_blocker(order, order.echeances_paiement.get()) == ""
    assert not StockMovement.objects.exists()
    assert not StockReceipt.objects.exists()


@pytest.mark.parametrize(
    "field",
    [
        "date_expedition_reelle",
        "date_arrivee_maroc",
        "documents_remis_banque_le",
        "date_reelle",
    ],
)
def test_real_logistics_dates_cannot_be_in_the_future(purchase_context, field):
    ctx = purchase_context
    order = service_dossier(ctx)
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    result = purchase_post(ctx, order, "progression", **{field: future})
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert getattr(order, field) is None


@pytest.mark.parametrize("field", ["date_arrivee_maroc", "date_reelle"])
def test_arrival_and_receipt_must_follow_real_shipment(purchase_context, field):
    ctx = purchase_context
    order = service_dossier(ctx)
    result = purchase_post(
        ctx, order, "progression", **{field: timezone.localdate().isoformat()}
    )
    assert result.status_code == 400, result.data
    record_shipment(ctx, order)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    result = purchase_post(ctx, order, "progression", **{field: yesterday})
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert getattr(order, field) is None


def test_recorded_real_shipment_date_and_phase_cannot_move_backwards(purchase_context):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    result = purchase_post(
        ctx,
        order,
        "progression",
        date_expedition_reelle=(timezone.localdate() - timedelta(days=1)).isoformat(),
    )
    assert result.status_code == 400, result.data
    result = purchase_post(ctx, order, "progression", statut="Transit")
    assert result.status_code == 200, result.data
    result = purchase_post(ctx, order, "progression", statut="Production")
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert order.statut == "Transit"
    assert order.date_expedition_reelle == timezone.localdate()


def test_saved_delay_explanation_applies_to_its_planned_date(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="documentary100")
    order.production_confirmee_le = timezone.now()
    order.date_expedition_prevue = timezone.localdate() - timedelta(days=1)
    order.statut = "Production"
    order.save()
    result = purchase_post(
        ctx, order, "progression", remarque="Le fournisseur attend une pièce"
    )
    assert result.status_code == 200, result.data
    assert order.process_notes.filter(
        remarque__startswith=f"Retard d’expédition ({order.date_expedition_prevue}) :"
    ).exists()
    result = purchase_post(ctx, order, "progression", cout_transport="50.00")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.cout_transport == Decimal("50.00")


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


def test_creator_can_record_proof_forwarding_after_closure(purchase_context):
    ctx = purchase_context
    order, item = closed_paid_dossier(ctx)
    result = ctx.api.post(
        reverse("logistique:logistique-send-swift", args=[order.pk]),
        {"echeance_id": item.pk, "email_envoye": True},
        format="json",
    )
    assert result.status_code == 200, result.data
    item.refresh_from_db()
    order.refresh_from_db()
    assert item.preuve_envoyee_fournisseur_le
    assert order.statut == "Clôture"
    assert order.solde_restant == 0


def test_manager_can_retry_creator_notification_after_closure(
    purchase_context, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order, item = closed_paid_dossier(ctx)
    with patch("logistique.tasks.queue_purchase_creator_email") as queue:
        with django_capture_on_commit_callbacks(execute=True):
            result = purchase_post(
                ctx, order, "relancer_notification", echeance_id=item.pk
            )
    assert result.status_code == 200, result.data
    queue.assert_called_once_with(item.pk)
    order.refresh_from_db()
    assert order.statut == "Clôture"
    assert order.statut_global == "Clôturé"


@pytest.mark.parametrize("action", ["proof", "retry"])
def test_cancelled_dossier_blocks_payment_communications(
    purchase_context, action, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order, item = closed_paid_dossier(ctx)
    order.statut_global = "Annulé"
    order.save(update_fields=["statut_global"])
    with patch("logistique.tasks.queue_purchase_creator_email") as queue:
        with django_capture_on_commit_callbacks(execute=True):
            if action == "proof":
                result = ctx.api.post(
                    reverse("logistique:logistique-send-swift", args=[order.pk]),
                    {"echeance_id": item.pk, "email_envoye": True},
                    format="json",
                )
            else:
                result = purchase_post(
                    ctx, order, "relancer_notification", echeance_id=item.pk
                )
    assert result.status_code == 400, result.data
    queue.assert_not_called()
    item.refresh_from_db()
    assert item.preuve_envoyee_fournisseur_le is None


@pytest.mark.parametrize(
    "target", ["Commande fournisseur", "Titre d'Importation", "Paiement effectué"]
)
def test_legacy_status_endpoint_rejects_phases_outside_supplier_workflow(
    purchase_context, target
):
    ctx = purchase_context
    order = validated_dossier(ctx, condition="receipt100")
    result = ctx.api.patch(
        reverse("logistique:logistique-statut-update", args=[order.pk]),
        {"statut": target},
        format="json",
    )
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert order.statut == "Proforma"


def test_legacy_status_endpoint_cannot_return_transit_to_proforma(purchase_context):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    result = purchase_post(ctx, order, "progression", statut="Transit")
    assert result.status_code == 200, result.data
    result = ctx.api.patch(
        reverse("logistique:logistique-statut-update", args=[order.pk]),
        {"statut": "Proforma"},
        format="json",
    )
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert order.statut == "Transit"


@pytest.mark.parametrize("closed", [False, True])
def test_generic_update_cannot_bypass_supplier_forms_and_receipt_guards(
    purchase_context, closed
):
    ctx = purchase_context
    order = closed_paid_dossier(ctx)[0] if closed else service_dossier(ctx)
    original_date = order.date_reelle
    original_cost = order.cout_transport
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    result = ctx.api.put(
        reverse("logistique:logistique-detail", args=[order.pk]),
        {"date_reelle": future, "cout_transport": "999.00"},
        format="json",
    )
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    assert order.date_reelle == original_date
    assert order.cout_transport == original_cost
    if not closed:
        assert payment_blocker(order, order.echeances_paiement.get())


def test_responsible_lecture_user_cannot_edit_bank_through_generic_update(
    purchase_context,
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    order.responsable = ctx.reader
    order.save(update_fields=["responsable"])
    result = authenticated(ctx.reader).put(
        reverse("logistique:logistique-detail", args=[order.pk]),
        {"banque": "Unauthorized bank"},
        format="json",
    )
    assert result.status_code == 403, result.data
    order.refresh_from_db()
    assert order.banque != "Unauthorized bank"


def test_lecture_creator_responsible_cannot_request_payment_or_forward_proof(
    purchase_context,
):
    ctx = purchase_context
    order = validated_dossier(ctx)
    prepare_title(order)
    order.created_by_user = ctx.reader
    order.responsable = ctx.reader
    order.save(update_fields=["created_by_user", "responsable"])
    item = order.echeances_paiement.get(declencheur="advance")
    item.montant_paye = item.montant_prevu
    item.paiement_valide_le = timezone.now()
    item.justificatif_file = SimpleUploadedFile(
        "proof.pdf", b"%PDF-1.4 proof", content_type="application/pdf"
    )
    item.save()
    reader = authenticated(ctx.reader)
    balance = order.echeances_paiement.get(declencheur="scheduled")
    result = reader.post(
        reverse("logistique:logistique-request-payment", args=[order.pk]),
        {"echeance_id": balance.pk, "date_echeance": timezone.localdate().isoformat()},
        format="json",
    )
    assert result.status_code == 403, result.data
    result = reader.post(
        reverse("logistique:logistique-send-swift", args=[order.pk]),
        {"echeance_id": item.pk, "email_envoye": True},
        format="json",
    )
    assert result.status_code == 403, result.data
    item.refresh_from_db()
    balance.refresh_from_db()
    assert item.preuve_envoyee_fournisseur_le is None
    assert balance.demandee_le is None


def received_dossier(ctx):
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
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
    result = purchase_post(ctx, order, "progression", statut="Clôture")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.statut == "Clôture"


def test_closed_supplier_receipt_cannot_be_cancelled_through_stock_api(
    purchase_context,
):
    ctx = purchase_context
    order, receipt = received_dossier(ctx)
    close_received_dossier(ctx, order)
    result = ctx.api.post(
        reverse("stock:receipt-action", args=[receipt.pk, "cancel"])
        + f"?company_id={ctx.company.pk}",
        {},
        format="json",
    )
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    receipt.refresh_from_db()
    ctx.balance.refresh_from_db()
    assert order.statut == "Clôture"
    assert order.date_reelle == timezone.localdate()
    assert receipt.status == StockReceipt.STATUS_VALIDATED
    assert ctx.balance.physical_quantity == Decimal("2.000")
    assert order.lignes.get().received_quantity == Decimal("2.000")
    assert StockMovement.objects.count() == 1


def test_receipt_cancellation_rechecks_order_after_cached_object_was_closed(
    purchase_context,
):
    from rest_framework.exceptions import ValidationError
    from stock.services import cancel_receipt

    ctx = purchase_context
    order, stale_receipt = received_dossier(ctx)
    assert stale_receipt.logistics_order.statut == "Réception locale"
    close_received_dossier(ctx, order)
    # The service must check a locked, fresh order instead of this cached relation.
    assert stale_receipt.logistics_order.statut == "Réception locale"
    with pytest.raises(ValidationError):
        cancel_receipt(stale_receipt, ctx.creator)
    ctx.balance.refresh_from_db()
    assert ctx.balance.physical_quantity == Decimal("2.000")
    assert StockMovement.objects.count() == 1


def test_open_supplier_receipt_can_be_cancelled_once(purchase_context):
    ctx = purchase_context
    order, receipt = received_dossier(ctx)
    url = (
        reverse("stock:receipt-action", args=[receipt.pk, "cancel"])
        + f"?company_id={ctx.company.pk}"
    )
    result = ctx.api.post(url, {}, format="json")
    assert result.status_code == 200, result.data
    result = ctx.api.post(url, {}, format="json")
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    receipt.refresh_from_db()
    ctx.balance.refresh_from_db()
    assert order.statut == "Dédouanement"
    assert order.date_reelle is None
    assert receipt.status == StockReceipt.STATUS_CANCELLED
    assert ctx.balance.physical_quantity == 0
    assert order.lignes.get().received_quantity == 0
    assert StockMovement.objects.count() == 2


@pytest.mark.parametrize("actor", ["reader", "accountant"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_supplier_responsible_must_have_a_logistics_write_role(
    purchase_context, actor, operation
):
    ctx = purchase_context
    candidate = getattr(ctx, actor)
    if operation == "create":
        result = ctx.api.post(
            reverse("logistique:logistique-list-create"),
            {
                "company_id": ctx.company.pk,
                "fournisseur": "Supplier",
                "responsable": candidate.pk,
            },
            format="json",
        )
        assert result.status_code == 400, result.data
        assert not LogisticsOrder.objects.exists()
    else:
        order = create_dossier(ctx)
        result = purchase_post(ctx, order, "dossier", responsable=candidate.pk)
        assert result.status_code == 400, result.data
        order.refresh_from_db()
        assert order.responsable == ctx.responsible


@pytest.mark.parametrize("role", ["Caissier", "Commercial", "Logistique"])
def test_active_logistics_write_roles_can_be_responsible(purchase_context, role):
    ctx = purchase_context
    membership = Membership.objects.get(user=ctx.responsible, company=ctx.company)
    membership.role = Role.objects.get_or_create(name=role)[0]
    membership.save(update_fields=["role"])
    order = create_dossier(ctx, responsable=ctx.responsible.pk)
    assert order.responsable == ctx.responsible


def test_inactive_logistics_user_cannot_be_responsible(purchase_context):
    ctx = purchase_context
    ctx.responsible.is_active = False
    ctx.responsible.save(update_fields=["is_active"])
    result = ctx.api.post(
        reverse("logistique:logistique-list-create"),
        {
            "company_id": ctx.company.pk,
            "fournisseur": "Supplier",
            "responsable": ctx.responsible.pk,
        },
        format="json",
    )
    assert result.status_code == 400, result.data
    assert not LogisticsOrder.objects.exists()


def test_assigned_lecture_cannot_add_a_process_remark_or_file(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    # Old assignments or a later role change must not restore write access.
    order.responsable = ctx.reader
    order.save(update_fields=["responsable"])
    original_events = order.events.count()
    result = authenticated(ctx.reader).post(
        reverse("logistique:logistique-process-note-create", args=[order.pk]),
        {
            "remarque": "Forbidden note",
            "fichier": SimpleUploadedFile(
                "note.pdf", b"%PDF-1.4 private", content_type="application/pdf"
            ),
        },
        format="multipart",
    )
    assert result.status_code == 403, result.data
    assert not order.process_notes.exists()
    assert order.events.count() == original_events


def test_assigned_accountant_can_add_remark_with_supporting_file(purchase_context):
    ctx = purchase_context
    order = validated_dossier(ctx)
    order.paiement_assigne_a = ctx.accountant
    order.save(update_fields=["paiement_assigne_a"])
    result = authenticated(ctx.accountant).post(
        reverse("logistique:logistique-process-note-create", args=[order.pk]),
        {
            "remarque": "La banque attend le justificatif complémentaire",
            "fichier": SimpleUploadedFile(
                "bank-note.pdf", b"%PDF-1.4 bank", content_type="application/pdf"
            ),
        },
        format="multipart",
    )
    assert result.status_code == 201, result.data
    note = order.process_notes.get()
    assert note.user == ctx.accountant
    assert note.statut == order.statut
    assert note.fichier
    assert "banque attend" in note.remarque


def test_unassigned_accountant_cannot_add_process_notes(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    result = authenticated(ctx.accountant).post(
        reverse("logistique:logistique-process-note-create", args=[order.pk]),
        {"remarque": "Not my accounting assignment"},
        format="json",
    )
    assert result.status_code == 403, result.data
    assert not order.process_notes.exists()


@pytest.mark.parametrize("actor", ["creator", "accountant"])
def test_closed_supplier_dossier_rejects_new_process_notes(purchase_context, actor):
    ctx = purchase_context
    order, _ = closed_paid_dossier(ctx)
    order.paiement_assigne_a = ctx.accountant
    order.save(update_fields=["paiement_assigne_a"])
    result = authenticated(getattr(ctx, actor)).post(
        reverse("logistique:logistique-process-note-create", args=[order.pk]),
        {"remarque": "Closed dossier note"},
        format="json",
    )
    assert result.status_code == 400, result.data
    assert not order.process_notes.exists()


def test_customer_delivery_prevents_receipt_cancellation_and_preserves_stock(
    purchase_context,
):
    ctx = purchase_context
    order, receipt = received_dossier(ctx)
    result = purchase_post(ctx, order, "progression", statut="Livraison client")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    before_date = order.date_reelle
    result = ctx.api.post(
        reverse("stock:receipt-action", args=[receipt.pk, "cancel"])
        + f"?company_id={ctx.company.pk}",
        {},
        format="json",
    )
    assert result.status_code == 400, result.data
    order.refresh_from_db()
    receipt.refresh_from_db()
    ctx.balance.refresh_from_db()
    assert order.statut == "Livraison client"
    assert order.date_reelle == before_date
    assert order.lignes.get().received_quantity == Decimal("2.000")
    assert receipt.status == StockReceipt.STATUS_VALIDATED
    assert ctx.balance.physical_quantity == Decimal("2.000")
    assert StockMovement.objects.count() == 1


def test_delivered_dossier_with_unpaid_balance_is_not_ready_to_close(purchase_context):
    ctx = purchase_context
    order, _ = received_dossier(ctx)
    result = purchase_post(ctx, order, "progression", statut="Livraison client")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.solde_restant > 0
    assert order.statut_global == "En cours"
    assert order.calculate_global_status() != "À clôturer"
    item = order.echeances_paiement.get()
    item.montant_paye = item.montant_prevu
    item.paiement_valide_le = timezone.now()
    item.save()
    assert order.calculate_global_status() == "À clôturer"


def test_overdue_payment_requires_a_requested_unpaid_installment(purchase_context):
    order = validated_dossier(purchase_context)
    advance = order.echeances_paiement.get(declencheur="advance")
    balance = order.echeances_paiement.get(declencheur="scheduled")
    balance.date_echeance = timezone.localdate() + timedelta(days=30)
    balance.save(update_fields=["date_echeance"])
    advance.date_echeance = timezone.localdate() - timedelta(days=1)
    advance.save(update_fields=["date_echeance"])
    assert not order.is_payment_overdue
    assert order.calculate_global_status() != "En retard"
    advance.demandee_le = timezone.now()
    advance.save(update_fields=["demandee_le"])
    assert order.is_payment_overdue
    assert order.calculate_global_status() == "En retard"
    advance.montant_paye = advance.montant_prevu
    advance.paiement_valide_le = timezone.now()
    advance.save()
    assert not order.is_payment_overdue
    assert order.calculate_global_status() != "En retard"


def test_unrequested_future_balance_does_not_make_a_delivered_dossier_overdue(
    purchase_context,
):
    ctx = purchase_context
    order, _ = received_dossier(ctx)
    item = order.echeances_paiement.get()
    item.date_echeance = timezone.localdate() + timedelta(days=7)
    item.save(update_fields=["date_echeance"])
    result = purchase_post(ctx, order, "progression", statut="Livraison client")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert not order.is_payment_overdue
    assert order.statut_global == "En cours"
    item.date_echeance = timezone.localdate() - timedelta(days=1)
    item.demandee_le = timezone.now()
    item.save(update_fields=["date_echeance", "demandee_le"])
    assert order.is_payment_overdue
    assert order.calculate_global_status() == "En retard"


def test_dossier_deadline_applies_after_delivery_until_actual_closure(purchase_context):
    ctx = purchase_context
    order, _ = received_dossier(ctx)
    yesterday = timezone.localdate() - timedelta(days=1)
    result = purchase_post(ctx, order, "dossier", date_prevue=yesterday.isoformat())
    assert result.status_code == 200, result.data
    result = purchase_post(ctx, order, "progression", statut="Livraison client")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert order.is_delivery_overdue
    assert order.statut_global == "En retard"
    item = order.echeances_paiement.get()
    item.montant_paye = item.montant_prevu
    item.paiement_valide_le = timezone.now()
    item.save()
    assert order.calculate_global_status() == "En retard"
    result = purchase_post(ctx, order, "progression", statut="Clôture")
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert not order.is_delivery_overdue
    assert order.statut_global == "Clôturé"


@pytest.mark.parametrize(
    "field,action,initial,changed,label",
    [
        (
            "fournisseur_email",
            "dossier",
            "supplier@example.invalid",
            "updated@example.invalid",
            "E-mail du fournisseur",
        ),
        ("transport", "progression", "Maritime", "Aérien", "Transport"),
    ],
)
def test_optional_supplier_text_change_and_clear_persist_with_auditable_values(
    purchase_context, field, action, initial, changed, label
):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    setattr(order, field, initial)
    order.save(update_fields=[field])
    result = purchase_post(ctx, order, action, **{field: changed})
    assert result.status_code == 200, result.data
    event = order.events.get(action=f"Modification : {label}")
    assert event.old_value == initial
    assert event.new_value == changed
    assert event.user == ctx.creator
    result = purchase_post(ctx, order, action, **{field: ""})
    assert result.status_code == 200, result.data
    order.refresh_from_db()
    assert getattr(order, field) == ""
    events = list(order.events.filter(action=f"Modification : {label}").order_by("pk"))
    assert [(event.old_value, event.new_value) for event in events] == [
        (initial, changed),
        (changed, ""),
    ]
    detail = authenticated(ctx.creator).get(
        reverse("logistique:logistique-detail", args=[order.pk])
    )
    assert detail.status_code == 200, detail.data
    assert detail.data[field] == ""
    history = [
        event
        for event in detail.data["events"]
        if event["action"] == f"Modification : {label}"
    ]
    assert {(event["old_value"], event["new_value"]) for event in history} == {
        (initial, changed),
        (changed, ""),
    }


def test_long_supplier_line_changes_remain_complete_in_history(purchase_context):
    ctx = purchase_context
    ctx.article.designation = (
        "Luminaire fournisseur avec une désignation complète et détaillée. " * 8
    )
    ctx.article.save(update_fields=["designation"])
    order = create_dossier(ctx)
    result = save_proforma(ctx, order, decision="control")
    assert result.status_code == 200, result.data
    result = save_proforma(
        ctx,
        order,
        decision="control",
        lignes=json.dumps(
            [{"article": ctx.article.pk, "quantity": "3.000", "prix_achat": "50.00"}]
        ),
    )
    assert result.status_code == 200, result.data
    event = (
        order.events.filter(action="Modification : Articles de la proforma fournisseur")
        .order_by("-pk")
        .first()
    )
    assert event is not None
    assert len(event.old_value) <= 255 and len(event.new_value) <= 255
    assert "Ancienne valeur" in event.note and "Nouvelle valeur" in event.note
    assert "quantité 2.000" in event.note
    assert "quantité 3.000" in event.note
    assert ctx.article.designation in event.note
    assert ctx.article.reference in event.note


def partial_receipt(ctx, order, reference, note):
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


def test_receipt_reference_and_note_survive_reopening_and_are_company_scoped(
    purchase_context,
):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    reference = "BL-FOURN-032"
    note = "Carton légèrement abîmé, articles contrôlés et conformes"
    response = partial_receipt(ctx, order, reference, note)
    (receipt,) = response.data["receptions"]
    assert receipt["reference"] == reference
    assert receipt["note"] == note
    assert receipt["status"] == StockReceipt.STATUS_VALIDATED
    assert receipt["date_created"] and receipt["date_validated"]
    assert receipt["created_by_name"] == ctx.creator.email
    assert receipt["validated_by_name"] == ctx.creator.email
    foreign_order = LogisticsOrder.objects.create(
        company=ctx.foreign,
        workflow_version=2,
        numero_commande="PRIVATE-LOG",
        fournisseur="PRIVATE-SUPPLIER",
        created_by_user=ctx.outsider,
    )
    StockReceipt.objects.create(
        company=ctx.foreign,
        logistics_order=foreign_order,
        reference="PRIVATE-RECEIPT",
        note="PRIVATE-FOREIGN-NOTE",
        created_by=ctx.outsider,
    )
    # Inconsistent historical links must not leak a foreign company's receipt.
    StockReceipt.objects.create(
        company=ctx.foreign,
        logistics_order=order,
        reference="PRIVATE-MISLINKED",
        note="PRIVATE-MISLINKED-NOTE",
        created_by=ctx.outsider,
    )
    reopened = authenticated(ctx.reader).get(
        reverse("logistique:logistique-detail", args=[order.pk])
    )
    assert reopened.status_code == 200, reopened.data
    assert reopened.data["receptions"] == [receipt]
    assert b"PRIVATE-" not in reopened.content
    forbidden = ctx.api.get(
        reverse("logistique:logistique-detail", args=[foreign_order.pk])
    )
    assert forbidden.status_code == 403


def test_partial_receipt_history_identifies_reference_article_and_actual_quantities(
    purchase_context,
):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    first = partial_receipt(ctx, order, "REC-PART-1", "Première livraison partielle")
    order.refresh_from_db()
    assert order.date_reelle is None
    event = order.events.get(action="Réception de marchandises")
    assert event.new_value == "REC-PART-1"
    assert "REC-PART-1" in event.note
    assert ctx.article.reference in event.note
    assert "1.000" in event.note
    assert "total reçu 1.000 / 2.000" in event.note
    assert "Première livraison partielle" in event.note
    second = partial_receipt(ctx, order, "REC-PART-2", "Solde reçu et vérifié")
    order.refresh_from_db()
    assert order.date_reelle == timezone.localdate()
    later = (
        order.events.filter(action="Réception de marchandises").order_by("-pk").first()
    )
    assert later.new_value == "REC-PART-2"
    assert "total reçu 2.000 / 2.000" in later.note
    assert "Solde reçu et vérifié" in later.note
    assert {entry["reference"] for entry in second.data["receptions"]} == {
        "REC-PART-1",
        "REC-PART-2",
    }
    assert first.data["receptions"][0]["note"] == "Première livraison partielle"


def test_supplier_field_change_does_not_add_a_redundant_workflow_summary(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    previous_ids = list(order.events.values_list("pk", flat=True))
    response = purchase_post(ctx, order, "dossier", fournisseur="Nouveau fournisseur")
    assert response.status_code == 200, response.data
    events = list(order.events.exclude(pk__in=previous_ids))
    assert len(events) == 1
    assert events[0].action == "Modification : Fournisseur"
    assert events[0].old_value == "Fournisseur indépendant"
    assert events[0].new_value == "Nouveau fournisseur"
    assert events[0].user == ctx.creator


@pytest.mark.parametrize("action", ["dossier", "titre", "progression"])
def test_unchanged_supplier_save_does_not_add_history_noise_or_rewrite_old_events(
    purchase_context, action
):
    ctx = purchase_context
    order = create_dossier(ctx)
    legacy = order.add_event(
        user=ctx.creator,
        action="Mise à jour achat fournisseur : dossier",
        new_value="Proforma",
    )
    before = list(order.events.values("pk", "action", "old_value", "new_value", "note"))
    response = purchase_post(ctx, order, action)
    assert response.status_code == 200, response.data
    assert list(order.events.values("pk", "action", "old_value", "new_value", "note")) == before
    legacy.refresh_from_db()
    assert legacy.action == "Mise à jour achat fournisseur : dossier"
    assert legacy.new_value == "Proforma"


def test_proforma_recheck_without_business_changes_has_a_french_audit_event(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    response = save_proforma(ctx, order, decision="control")
    assert response.status_code == 200, response.data
    previous_ids = list(order.events.values_list("pk", flat=True))
    response = purchase_post(
        ctx, order, "proforma", condition_achat=order.condition_achat, decision="control"
    )
    assert response.status_code == 200, response.data
    events = list(order.events.exclude(pk__in=previous_ids))
    assert len(events) == 1
    assert events[0].action == "Contrôle de la proforma fournisseur enregistré"
    assert events[0].new_value == order.numero_proforma_fournisseur
    assert events[0].user == ctx.creator


def test_progress_remark_history_contains_the_actual_explanation_without_raw_action(purchase_context):
    ctx = purchase_context
    order = create_dossier(ctx)
    previous_ids = list(order.events.values_list("pk", flat=True))
    remark = "Le fournisseur attend notre validation avant de préparer les cartons."
    response = purchase_post(ctx, order, "progression", remarque=remark)
    assert response.status_code == 200, response.data
    events = list(order.events.exclude(pk__in=previous_ids))
    assert len(events) == 1
    assert events[0].action == "Remarque ajoutée au dossier"
    assert events[0].note == remark
    order.refresh_from_db()
    assert order.statut == "Proforma"
    assert order.process_notes.get().remarque == remark


def test_partial_receipt_has_one_meaningful_history_entry_without_workflow_duplicate(purchase_context):
    ctx = purchase_context
    order = ready_for_shipping(ctx)
    record_shipment(ctx, order)
    previous_ids = list(order.events.values_list("pk", flat=True))
    response = partial_receipt(ctx, order, "REC-EXPL-1", "Premier carton contrôlé")
    assert response.status_code == 200, response.data
    events = list(order.events.exclude(pk__in=previous_ids))
    assert len(events) == 1
    assert events[0].action == "Réception de marchandises"
    assert events[0].new_value == "REC-EXPL-1"
    assert "total reçu 1.000 / 2.000" in events[0].note
    assert "Premier carton contrôlé" in events[0].note
    order.refresh_from_db()
    assert order.statut == "Expédition"
    assert order.date_reelle is None


def test_creator_notification_retry_history_describes_the_requested_email(
    purchase_context, django_capture_on_commit_callbacks
):
    ctx = purchase_context
    order, item = closed_paid_dossier(ctx)
    previous_ids = list(order.events.values_list("pk", flat=True))
    with patch("logistique.tasks.queue_purchase_creator_email") as queue:
        with django_capture_on_commit_callbacks(execute=True):
            response = purchase_post(ctx, order, "relancer_notification", echeance_id=item.pk)
    assert response.status_code == 200, response.data
    queue.assert_called_once_with(item.pk)
    events = list(order.events.exclude(pk__in=previous_ids))
    assert len(events) == 1
    assert events[0].action == "Relance de la notification au créateur demandée"
    assert events[0].new_value == f"Paiement de {item.montant_paye:.2f} {item.devise}"
    order.refresh_from_db()
    assert order.statut == "Clôture"


@pytest.mark.parametrize("condition,expected,paid", [
    ("advance30_transfer70", "Avance 30 % : 3 000,00 USD", "1000.00"),
    ("advance100", "Avance 100 % : 10 000,00 USD", "5000.00"),
])
def test_payment_start_history_keeps_original_amount_after_partial_split(
    purchase_context, django_capture_on_commit_callbacks, condition, expected, paid
):
    ctx = purchase_context
    order = validated_dossier(ctx, condition=condition, total="10000.00", currency="USD")
    prepare_title(order)
    item = order.echeances_paiement.get(declencheur="advance")
    request_installment(ctx, order, item, django_capture_on_commit_callbacks)
    accountant = authenticated(ctx.accountant)
    started = accountant.post(reverse("logistique:logistique-start-payment", args=[order.pk]),
        {"echeance_id": item.pk}, format="json")
    assert started.status_code == 200, started.data
    event = order.events.get(action="Démarrage paiement")
    assert event.new_value == expected
    recorded = accountant.post(reverse("logistique:logistique-record-payment-execution", args=[order.pk]),
        {"echeance_id": item.pk, "date_paiement": timezone.localdate().isoformat(), "montant_paye": paid}, format="json")
    assert recorded.status_code == 200, recorded.data
    item.refresh_from_db()
    assert item.montant_prevu == Decimal(paid)
    event.refresh_from_db()
    assert event.new_value == expected
    detail = ctx.api.get(reverse("logistique:logistique-detail", args=[order.pk]))
    assert next(row for row in detail.data["events"] if row["id"] == event.pk)["new_value"] == expected
