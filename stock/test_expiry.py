from datetime import timedelta
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from company.models import Company
from company.serializers import CompanySerializer
from logistique.models import LogisticsOrder, LogisticsOrderProforma
from logistique.serializers import LogisticsOrderBaseSerializer
from notification.models import Notification
from .expiry import process_reservation_deadline, scan_reservation_deadlines
from .models import InventorySession, StockBalance, StockReservation
from .services import sync_proforma_reservations
from .tests import stock_context  # noqa: F401

pytestmark = pytest.mark.django_db


def accept(context):
    proforma = context["proforma"]
    sync_proforma_reservations(proforma, proforma.statut, "Accepté")
    proforma.statut = "Accepté"
    proforma.save(update_fields=["statut"])
    return StockReservation.objects.get(proforma_line=context["proforma_line"])


def member_client(context, role_name="Caissier"):
    role, _ = Role.objects.get_or_create(name=role_name)
    Membership.objects.create(
        company=context["company"], user=context["user"], role=role
    )
    client = APIClient()
    client.force_authenticate(context["user"])
    return client


def test_deadline_is_seven_days_from_acceptance_and_reacceptance(stock_context):
    before = timezone.now()
    reservation = accept(stock_context)
    assert (
        before + timedelta(days=7)
        <= reservation.expires_at
        <= timezone.now() + timedelta(days=7)
    )
    old_deadline = reservation.expires_at
    reservation.expiry_reminded_at = before
    reservation.save()
    sync_proforma_reservations(stock_context["proforma"], "Accepté", "Expiré")
    sync_proforma_reservations(stock_context["proforma"], "Expiré", "Accepté")
    reservation.refresh_from_db()
    assert reservation.expires_at > old_deadline
    assert reservation.expiry_reminded_at is None
    assert reservation.released_quantity == 0


def test_warning_once_at_24_hours_and_only_to_company_members(stock_context):
    member_client(stock_context, "Commercial")
    other_company = Company.objects.create(raison_sociale="Other", ICE="OTHER")
    other_user = CustomUser.objects.create_user(
        email="other-expiry@example.test", password="pass"
    )
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(company=other_company, user=other_user, role=role)
    reservation = accept(stock_context)
    proforma = stock_context["proforma"]
    Notification.objects.all().delete()
    assert (
        process_reservation_deadline(
            proforma.pk, now=reservation.expires_at - timedelta(hours=24, seconds=1)
        )
        == "unchanged"
    )
    assert (
        process_reservation_deadline(
            proforma.pk, now=reservation.expires_at - timedelta(hours=24)
        )
        == "reminded"
    )
    assert (
        process_reservation_deadline(
            proforma.pk, now=reservation.expires_at - timedelta(hours=23)
        )
        == "unchanged"
    )
    notification = Notification.objects.get()
    assert notification.user_id == stock_context["user"].pk
    assert proforma.numero_facture in notification.message
    assert f"facture-pro-forma/{proforma.pk}" in notification.target_url
    proforma.refresh_from_db()
    assert proforma.statut == "Accepté"


def test_expiry_releases_once_preserves_physical_stock_and_logistics(stock_context):
    reservation = accept(stock_context)
    proforma = stock_context["proforma"]
    order = LogisticsOrder.objects.create(
        company=stock_context["company"],
        numero_commande="LOG-EXPIRY",
        statut="Transit",
        statut_global="En cours",
    )
    LogisticsOrderProforma.objects.create(commande=order, proforma=proforma)
    assert (
        process_reservation_deadline(proforma.pk, now=reservation.expires_at)
        == "expired"
    )
    assert (
        process_reservation_deadline(proforma.pk, now=reservation.expires_at)
        == "unchanged"
    )
    reservation.refresh_from_db()
    proforma.refresh_from_db()
    order.refresh_from_db()
    balance = StockBalance.objects.get(pk=stock_context["balance"].pk)
    assert proforma.statut == "Expiré"
    assert balance.reserved_quantity == 0
    assert balance.physical_quantity == 4
    assert reservation.released_quantity == 6
    assert reservation.status == "released"
    assert order.statut == "Transit"
    assert order.statut_global == "En cours"
    assert len(LogisticsOrderBaseSerializer.get_alerts(order)) == 1
    assert proforma.numero_facture in LogisticsOrderBaseSerializer.get_alerts(order)[0]
    assert (
        order.events.filter(action="Expiration de la réservation de stock").count() == 1
    )


def test_expiry_after_partial_delivery_releases_only_remaining(stock_context):
    reservation = accept(stock_context)
    reservation.consumed_quantity = Decimal("2")
    reservation.save()
    StockBalance.objects.filter(pk=reservation.balance_id).update(
        physical_quantity=2, reserved_quantity=4
    )
    process_reservation_deadline(
        stock_context["proforma"].pk, now=reservation.expires_at
    )
    reservation.refresh_from_db()
    balance = StockBalance.objects.get(pk=reservation.balance_id)
    assert reservation.consumed_quantity == 2
    assert reservation.released_quantity == 4
    assert balance.physical_quantity == 2
    assert balance.reserved_quantity == 0


def test_consumed_or_cancelled_documents_are_not_expired(stock_context):
    reservation = accept(stock_context)
    reservation.status = "consumed"
    reservation.consumed_quantity = reservation.reserved_quantity
    reservation.save()
    assert (
        process_reservation_deadline(
            stock_context["proforma"].pk, now=reservation.expires_at
        )
        == "unchanged"
    )
    assert scan_reservation_deadlines(now=reservation.expires_at)["expired"] == 0
    stock_context["proforma"].refresh_from_db()
    assert stock_context["proforma"].statut == "Accepté"


def test_stock_default_positive_first_before_pagination_explicit_sort_still_works(
    stock_context,
):
    client = member_client(stock_context)
    article = Article.objects.create(
        company=stock_context["company"],
        emplacement=stock_context["emplacement"],
        reference="AAA-ZERO",
        designation="Zero",
        type_article="Produit",
    )
    StockBalance.objects.create(
        company=article.company,
        article=article,
        emplacement=article.emplacement,
        physical_quantity=0,
    )
    params = {"company_id": article.company_id, "page_size": 1}
    response = client.get("/api/stock/balances/", params)
    assert response.status_code == 200
    assert response.data["results"][0]["article_reference"] == "STOCK-001"
    response = client.get(
        "/api/stock/balances/", {**params, "ordering": "article_reference"}
    )
    assert response.data["results"][0]["article_reference"] == "AAA-ZERO"


def test_inventory_activation_enforced_and_existing_history_readable(stock_context):
    client = member_client(stock_context)
    company = stock_context["company"]
    inventory = InventorySession.objects.create(
        company=company,
        emplacement=stock_context["emplacement"],
        created_by=stock_context["user"],
    )
    company.inventory_management_enabled = False
    company.save(update_fields=["inventory_management_enabled"])
    payload = {
        "company_id": company.pk,
        "emplacement": stock_context["emplacement"].pk,
        "lines": [{"article": stock_context["article"].pk, "counted_quantity": 4}],
    }
    assert (
        client.post("/api/stock/inventories/", payload, format="json").status_code
        == 400
    )
    assert (
        client.post(
            f"/api/stock/inventories/{inventory.pk}/validate/",
            {"company_id": company.pk},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/api/stock/inventories/{inventory.pk}/", {"company_id": company.pk}
        ).status_code
        == 200
    )
    company.inventory_management_enabled = True
    company.save(update_fields=["inventory_management_enabled"])
    response = client.post("/api/stock/inventories/", payload, format="json")
    assert response.status_code == 201, response.data


def test_inventory_requires_stock_activation(stock_context):
    serializer = CompanySerializer(
        stock_context["company"],
        data={"inventory_management_enabled": True, "stock_management_enabled": False},
        partial=True,
    )
    assert not serializer.is_valid()
    assert "inventory_management_enabled" in serializer.errors


def test_missing_logistics_role_migration_is_idempotent():
    migration = import_module("account.migrations.0020_ensure_logistics_role")
    with connection.schema_editor() as editor:
        migration.ensure_logistics_role(apps, editor)
        migration.ensure_logistics_role(apps, editor)
    assert Role.objects.filter(name="Logistique").count() == 1


def test_company_default_employee_range_can_be_saved():
    company = Company.objects.create(
        raison_sociale="Default range", ICE="DEFAULT-RANGE"
    )
    serializer = CompanySerializer(
        company, data={"nbr_employe": company.nbr_employe}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
