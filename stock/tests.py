from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from client.models import Client
from company.models import Company
from facture_client.models import FactureClient
from facture_proforma.models import FactureProForma, FactureProFormaLine
from logistique.models import LogisticsOrder, LogisticsOrderLine
from notification.models import Notification, NotificationPreference
from parameter.models import Emplacement, Ville
from .models import (
    StockBalance,
    StockMovement,
    StockReceipt,
    StockReceiptLine,
    StockReservation,
)
from .services import (
    activate_incoming,
    balance_snapshot,
    coverage_for_article,
    ensure_company_stock_ready,
    evaluate_low_stock,
    sync_delivery_stock,
    sync_proforma_reservations,
    validate_receipt,
)

pytestmark = pytest.mark.django_db


class StockContext(TypedDict):
    user: CustomUser
    company: Company
    emplacement: Emplacement
    client: Client
    article: Article
    balance: StockBalance
    proforma: FactureProForma
    proforma_line: FactureProFormaLine


@pytest.fixture
def stock_context() -> StockContext:
    user = CustomUser.objects.create_user(email="stock@example.com", password="pass")
    company = Company.objects.create(
        raison_sociale="Stock Company",
        ICE="STOCK-COMPANY",
        stock_management_enabled=True,
    )
    emplacement = Emplacement.objects.create(company=company, nom="Dépôt")
    ville = Ville.objects.create(company=company, nom="Casablanca")
    client = Client.objects.create(
        company=company,
        ville=ville,
        code_client="STOCK-CLIENT",
        client_type="PM",
        raison_sociale="Client stock",
    )
    article = Article.objects.create(
        company=company,
        emplacement=emplacement,
        reference="STOCK-001",
        designation="Produit stocké",
        type_article="Produit",
        stock_minimum=Decimal("2.000"),
    )
    balance = StockBalance.objects.create(
        company=company,
        article=article,
        emplacement=emplacement,
        physical_quantity=Decimal("4.000"),
    )
    proforma = FactureProForma.objects.create(
        company=company,
        client=client,
        numero_facture="PF-STOCK-001",
        date_facture=date(2026, 9, 10),
        statut="Envoyé",
        fournisseur="Fournisseur stock",
        created_by_user=user,
    )
    proforma_line = FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article,
        quantity=Decimal("6.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )
    return {
        "user": user,
        "company": company,
        "emplacement": emplacement,
        "client": client,
        "article": article,
        "balance": balance,
        "proforma": proforma,
        "proforma_line": proforma_line,
    }


def test_proforma_reservation_can_exceed_available_stock(
    stock_context: StockContext,
):
    sync_proforma_reservations(stock_context["proforma"], "Envoyé", "Accepté")

    balance = StockBalance.objects.get(pk=stock_context["balance"].pk)
    assert balance.physical_quantity == Decimal("4.000")
    assert balance.reserved_quantity == Decimal("6.000")
    assert balance.available_quantity == Decimal("-2.000")
    assert balance_snapshot(balance)["stock_state"] == "a_approvisionner"
    assert StockReservation.objects.filter(
        proforma_line=stock_context["proforma_line"], status="active"
    ).exists()


def test_launched_logistics_is_reported_as_incoming_and_partial_receipt_reduces_it(
    stock_context: StockContext,
):
    order = LogisticsOrder.objects.create(
        company=stock_context["company"],
        numero_commande="LOG-STOCK-001",
        fournisseur="Fournisseur stock",
        statut_commande_lancement="Terminée",
    )
    logistics_line = LogisticsOrderLine.objects.create(
        commande=order,
        proforma=stock_context["proforma"],
        source_line=stock_context["proforma_line"],
        client=stock_context["client"],
        article=stock_context["article"],
        quantity=Decimal("6.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )
    activate_incoming(order)
    logistics_line.refresh_from_db()
    assert logistics_line.expected_emplacement == stock_context["emplacement"]
    assert (
        coverage_for_article(stock_context["article"], Decimal("8.000"))["status"]
        == "couvert_par_stock_entrant"
    )

    receipt = StockReceipt.objects.create(
        company=stock_context["company"],
        logistics_order=order,
        created_by=stock_context["user"],
    )
    StockReceiptLine.objects.create(
        receipt=receipt,
        logistics_line=logistics_line,
        article=stock_context["article"],
        emplacement=stock_context["emplacement"],
        quantity=Decimal("2.500"),
    )
    validate_receipt(receipt, stock_context["user"])

    stock_context["balance"].refresh_from_db()
    logistics_line.refresh_from_db()
    assert stock_context["balance"].physical_quantity == Decimal("6.500")
    assert logistics_line.received_quantity == Decimal("2.500")
    assert StockMovement.objects.get(source_type="StockReceipt").quantity == Decimal(
        "2.500"
    )


def test_delivery_rejects_entire_status_change_when_physical_stock_is_short(
    stock_context: StockContext,
):
    delivery = BonDeLivraison.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        numero_bon_livraison="BL-STOCK-001",
        date_bon_livraison=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=delivery,
        article=stock_context["article"],
        quantity=Decimal("5.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    with pytest.raises(ValidationError):
        sync_delivery_stock(delivery, "Envoyé", "Accepté", stock_context["user"])

    stock_context["balance"].refresh_from_db()
    assert stock_context["balance"].physical_quantity == Decimal("4.000")
    assert not StockMovement.objects.filter(source_type="BonDeLivraison").exists()


def test_factured_delivery_posts_stock_once_and_can_be_reversed(
    stock_context: StockContext,
):
    delivery = BonDeLivraison.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        numero_bon_livraison="BL-STOCK-002",
        date_bon_livraison=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=delivery,
        article=stock_context["article"],
        quantity=Decimal("2.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    sync_delivery_stock(delivery, "Envoyé", "Facturé", stock_context["user"])
    sync_delivery_stock(delivery, "Facturé", "Facturé", stock_context["user"])

    stock_context["balance"].refresh_from_db()
    assert stock_context["balance"].physical_quantity == Decimal("2.000")
    assert (
        StockMovement.objects.filter(
            source_type="BonDeLivraison", movement_type="delivery"
        ).count()
        == 1
    )

    sync_delivery_stock(delivery, "Facturé", "Annulé", stock_context["user"])

    stock_context["balance"].refresh_from_db()
    assert stock_context["balance"].physical_quantity == Decimal("4.000")
    assert (
        StockMovement.objects.filter(
            source_type="BonDeLivraison", movement_type="reversal"
        ).count()
        == 1
    )


def test_reposted_delivery_deducts_stock_again_after_reversal(
    stock_context: StockContext,
):
    delivery = BonDeLivraison.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        numero_bon_livraison="BL-STOCK-REPOST",
        date_bon_livraison=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=delivery,
        article=stock_context["article"],
        quantity=Decimal("2.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    sync_delivery_stock(delivery, "Envoyé", "Accepté", stock_context["user"])
    sync_delivery_stock(delivery, "Accepté", "Annulé", stock_context["user"])
    sync_delivery_stock(delivery, "Annulé", "Accepté", stock_context["user"])

    stock_context["balance"].refresh_from_db()
    assert stock_context["balance"].physical_quantity == Decimal("2.000")
    assert (
        StockMovement.objects.filter(
            source_type="BonDeLivraison", movement_type="delivery"
        ).count()
        == 2
    )


def test_delivery_reversal_does_not_restore_cancelled_proforma_reservation(
    stock_context: StockContext,
):
    proforma = stock_context["proforma"]
    proforma.statut = "Accepté"
    proforma.save(update_fields=("statut",))
    sync_proforma_reservations(proforma, "Envoyé", "Accepté")
    facture = FactureClient.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        source_proforma=proforma,
        numero_facture="FC-STOCK-REVERSAL",
        date_facture=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    delivery = BonDeLivraison.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        source_facture_client=facture,
        numero_bon_livraison="BL-STOCK-RESERVATION",
        date_bon_livraison=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=delivery,
        article=stock_context["article"],
        quantity=Decimal("2.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    sync_delivery_stock(delivery, "Envoyé", "Accepté", stock_context["user"])
    proforma.statut = "Annulé"
    proforma.save(update_fields=("statut",))
    sync_proforma_reservations(proforma, "Accepté", "Annulé")
    sync_delivery_stock(delivery, "Accepté", "Annulé", stock_context["user"])

    stock_context["balance"].refresh_from_db()
    reservation = StockReservation.objects.get(
        proforma_line=stock_context["proforma_line"]
    )
    assert stock_context["balance"].reserved_quantity == Decimal("0.000")
    assert reservation.status == StockReservation.STATUS_RELEASED
    assert reservation.consumed_quantity == Decimal("0.000")
    assert reservation.released_quantity == Decimal("6.000")


def test_reaccepting_proforma_reuses_released_reservation_quantity(
    stock_context: StockContext,
):
    proforma = stock_context["proforma"]
    sync_proforma_reservations(proforma, "Envoyé", "Accepté")
    sync_proforma_reservations(proforma, "Accepté", "Annulé")
    sync_proforma_reservations(proforma, "Annulé", "Accepté")

    stock_context["balance"].refresh_from_db()
    reservation = StockReservation.objects.get(
        proforma_line=stock_context["proforma_line"]
    )
    assert stock_context["balance"].reserved_quantity == Decimal("6.000")
    assert reservation.reserved_quantity == Decimal("6.000")
    assert reservation.released_quantity == Decimal("0.000")


def test_closed_logistics_order_is_not_counted_as_incoming(
    stock_context: StockContext,
):
    order = LogisticsOrder.objects.create(
        company=stock_context["company"],
        numero_commande="LOG-STOCK-CLOSED",
        fournisseur="Fournisseur stock",
        statut_commande_lancement="Terminée",
        statut="Clôture",
        statut_global="Clôturé",
    )
    logistics_line = LogisticsOrderLine.objects.create(
        commande=order,
        proforma=stock_context["proforma"],
        source_line=stock_context["proforma_line"],
        client=stock_context["client"],
        article=stock_context["article"],
        expected_emplacement=stock_context["emplacement"],
        quantity=Decimal("6.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    activate_incoming(order)
    logistics_line.refresh_from_db()

    coverage = coverage_for_article(stock_context["article"], Decimal("8.000"))
    assert coverage["incoming_quantity"] == Decimal("0.000")
    assert coverage["status"] == "a_approvisionner"


def test_company_activation_only_initializes_the_selected_company():
    first = Company.objects.create(
        raison_sociale="First", ICE="STOCK-FIRST", stock_management_enabled=True
    )
    second = Company.objects.create(raison_sociale="Second", ICE="STOCK-SECOND")
    first_product = Article.objects.create(
        company=first,
        reference="FIRST-001",
        designation="First product",
        type_article="Produit",
    )
    second_product = Article.objects.create(
        company=second,
        reference="SECOND-001",
        designation="Second product",
        type_article="Produit",
    )

    ensure_company_stock_ready(first)

    first_product.refresh_from_db()
    second_product.refresh_from_db()
    assert first_product.emplacement is not None
    assert StockBalance.objects.filter(article=first_product).exists()
    assert Article.objects.filter(
        pk=second_product.pk, emplacement__isnull=True
    ).exists()
    assert not StockBalance.objects.filter(article=second_product).exists()


def test_company_activation_does_not_reserve_historical_delivered_quantity(
    stock_context: StockContext,
):
    proforma = stock_context["proforma"]
    proforma.statut = "Accepté"
    proforma.save(update_fields=("statut",))
    facture = FactureClient.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        source_proforma=proforma,
        numero_facture="FC-STOCK-HISTORY",
        date_facture=date(2026, 9, 10),
        created_by_user=stock_context["user"],
    )
    delivery = BonDeLivraison.objects.create(
        company=stock_context["company"],
        client=stock_context["client"],
        source_facture_client=facture,
        numero_bon_livraison="BL-STOCK-HISTORY",
        date_bon_livraison=date(2026, 9, 10),
        statut="Accepté",
        created_by_user=stock_context["user"],
    )
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=delivery,
        article=stock_context["article"],
        quantity=Decimal("2.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )

    ensure_company_stock_ready(stock_context["company"])
    ensure_company_stock_ready(stock_context["company"])

    stock_context["balance"].refresh_from_db()
    reservation = StockReservation.objects.get(
        proforma_line=stock_context["proforma_line"]
    )
    assert stock_context["balance"].physical_quantity == Decimal("4.000")
    assert stock_context["balance"].reserved_quantity == Decimal("4.000")
    assert reservation.reserved_quantity == Decimal("6.000")
    assert reservation.consumed_quantity == Decimal("2.000")
    assert reservation.status == StockReservation.STATUS_ACTIVE


def test_stock_api_is_visible_to_members_but_adjustments_require_caissier(
    stock_context: StockContext,
):
    role, _ = Role.objects.get_or_create(name="Commercial")
    membership = Membership.objects.create(
        user=stock_context["user"], company=stock_context["company"], role=role
    )
    client = APIClient()
    client.force_authenticate(stock_context["user"])

    response = client.get(
        "/api/stock/balances/", {"company_id": stock_context["company"].id}
    )
    assert response.status_code == 200

    payload = {
        "company_id": stock_context["company"].id,
        "article": stock_context["article"].id,
        "emplacement": stock_context["emplacement"].id,
        "quantity": "1.000",
        "movement_type": "adjustment",
        "reason": "Comptage de contrôle",
    }
    response = client.post("/api/stock/adjustments/", payload, format="json")
    assert response.status_code == 403

    membership.role, _ = Role.objects.get_or_create(name="Caissier")
    membership.save(update_fields=("role",))
    response = client.post("/api/stock/adjustments/", payload, format="json")
    assert response.status_code == 201


def test_low_stock_notifications_respect_role_and_user_preference(
    stock_context: StockContext,
):
    caissier, _ = Role.objects.get_or_create(name="Caissier")
    logistique, _ = Role.objects.get_or_create(name="Logistique")
    commercial, _ = Role.objects.get_or_create(name="Commercial")
    recipients = []
    for index, role in enumerate((caissier, logistique, commercial), start=1):
        user = CustomUser.objects.create_user(
            email=f"stock-recipient-{index}@example.com", password="pass"
        )
        Membership.objects.create(
            user=user, company=stock_context["company"], role=role
        )
        recipients.append(user)
    NotificationPreference.objects.filter(user=recipients[1]).update(
        notify_low_stock=False
    )
    stock_context["balance"].physical_quantity = Decimal("2.000")
    stock_context["balance"].save(update_fields=("physical_quantity",))

    evaluate_low_stock(stock_context["balance"].id, force=True)

    notifications = Notification.objects.filter(notification_type="low_stock")
    assert list(notifications.values_list("user_id", flat=True)) == [recipients[0].id]


def test_low_stock_repeat_delay_is_applied_per_user(stock_context: StockContext):
    caissier, _ = Role.objects.get_or_create(name="Caissier")
    frequent_user = CustomUser.objects.create_user(
        email="stock-frequent@example.com", password="pass"
    )
    infrequent_user = CustomUser.objects.create_user(
        email="stock-infrequent@example.com", password="pass"
    )
    for user in (frequent_user, infrequent_user):
        Membership.objects.create(
            user=user, company=stock_context["company"], role=caissier
        )
    NotificationPreference.objects.filter(user=frequent_user).update(
        low_stock_repeat_hours=6
    )
    NotificationPreference.objects.filter(user=infrequent_user).update(
        low_stock_repeat_hours=72
    )
    stock_context["balance"].physical_quantity = Decimal("2.000")
    stock_context["balance"].save(update_fields=("physical_quantity",))
    evaluate_low_stock(stock_context["balance"].id, force=True)
    Notification.objects.filter(notification_type="low_stock").update(
        date_created=timezone.now() - timedelta(hours=7)
    )

    evaluate_low_stock(stock_context["balance"].id)

    assert (
        Notification.objects.filter(
            notification_type="low_stock", user=frequent_user
        ).count()
        == 2
    )
    assert (
        Notification.objects.filter(
            notification_type="low_stock", user=infrequent_user
        ).count()
        == 1
    )
