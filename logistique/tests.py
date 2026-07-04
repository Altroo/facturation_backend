from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import Marque, ModePaiement, Ville

from .models import LogisticsOrder, LogisticsOrderEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def logistics_company():
    return Company.objects.create(raison_sociale="Logistics Co", ICE="LOGICE")


@pytest.fixture
def logistics_roles():
    return {
        name: Role.objects.get_or_create(name=name)[0]
        for name in ["Caissier", "Comptable", "Logistique"]
    }


@pytest.fixture
def logistics_user(logistics_company, logistics_roles):
    user = CustomUser.objects.create_user(
        email="logistics@example.com",
        password="pass",
        first_name="Log",
        last_name="User",
    )
    Membership.objects.create(
        user=user,
        company=logistics_company,
        role=logistics_roles["Caissier"],
        can_change_document_status=True,
    )
    return user


@pytest.fixture
def comptable_user(logistics_company, logistics_roles):
    user = CustomUser.objects.create_user(
        email="comptable@example.com",
        password="pass",
        first_name="Compte",
        last_name="Able",
    )
    Membership.objects.create(
        user=user,
        company=logistics_company,
        role=logistics_roles["Comptable"],
    )
    return user


@pytest.fixture
def api_client(logistics_user):
    client = APIClient()
    client.force_authenticate(user=logistics_user)
    return client


@pytest.fixture
def logistics_proformas(logistics_company, logistics_user):
    ville = Ville.objects.create(nom="Casablanca", company=logistics_company)
    client = Client.objects.create(
        code_client="LOG001",
        client_type="PM",
        raison_sociale="Client Logistique",
        ville=ville,
        company=logistics_company,
    )
    mode = ModePaiement.objects.create(nom="Virement", company=logistics_company)
    brand_a = Marque.objects.create(nom="Brand A", company=logistics_company)
    brand_b = Marque.objects.create(nom="Brand B", company=logistics_company)
    article_a = Article.objects.create(
        company=logistics_company,
        marque=brand_a,
        reference="A-001",
        designation="Article A",
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        tva=20,
    )
    article_b = Article.objects.create(
        company=logistics_company,
        marque=brand_b,
        reference="B-001",
        designation="Article B",
        prix_achat=Decimal("200.00"),
        prix_vente=Decimal("260.00"),
        tva=20,
    )
    proforma = FactureProForma.objects.create(
        numero_facture="P001/26",
        client=client,
        date_facture="2026-07-01",
        mode_paiement=mode,
        statut="Accepté",
        created_by_user=logistics_user,
    )
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article_a,
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        quantity=2,
    )
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article_b,
        prix_achat=Decimal("200.00"),
        prix_vente=Decimal("260.00"),
        quantity=1,
    )
    return proforma, brand_a, brand_b


def test_create_logistics_orders_splits_proforma_lines_by_brand(
    api_client, logistics_company, logistics_proformas
):
    proforma, brand_a, brand_b = logistics_proformas
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        {
            "company_id": logistics_company.id,
            "proformas": [proforma.id],
            "fournisseur": "Supplier One",
            "transport": "Maritime",
            "methode_paiement": "Virement",
            "cout_transport": "50.00",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["created"] == 2
    orders = LogisticsOrder.objects.order_by("marque__nom")
    assert [order.marque_id for order in orders] == [brand_a.id, brand_b.id]
    assert [order.lignes.count() for order in orders] == [1, 1]
    assert orders[0].fournisseur == "Supplier One"
    assert orders[0].cout_achat == Decimal("200.000")
    assert orders[0].cout_total == Decimal("250.000")
    assert LogisticsOrderEvent.objects.filter(action="Création").count() == 2


def test_logistics_list_returns_dashboard_stats(
    api_client, logistics_company, logistics_proformas
):
    test_create_logistics_orders_splits_proforma_lines_by_brand(
        api_client, logistics_company, logistics_proformas
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.get(
        url,
        {"company_id": logistics_company.id, "pagination": "true"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2
    assert response.data["stats"]["total_commandes"] == 2
    assert response.data["stats"]["commandes_en_cours"] == 2
    assert response.data["stats"]["couts_logistiques"] == Decimal("500.00")


def test_comptable_can_validate_requested_payment(
    api_client, logistics_company, logistics_proformas, comptable_user
):
    test_create_logistics_orders_splits_proforma_lines_by_brand(
        api_client, logistics_company, logistics_proformas
    )
    order = LogisticsOrder.objects.first()

    request_url = reverse("logistique:logistique-request-payment", args=[order.id])
    request_response = api_client.post(request_url, {}, format="json")
    assert request_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut_paiement == "En attente"
    assert order.demande_paiement_envoyee_par is not None

    comptable_client = APIClient()
    comptable_client.force_authenticate(user=comptable_user)
    validate_url = reverse("logistique:logistique-validate-payment", args=[order.id])
    validate_response = comptable_client.post(
        validate_url,
        {
            "date_paiement": "2026-07-04",
            "montant_paiement": "250.00",
            "reference_paiement": "SWIFT-001",
            "methode_paiement": "Virement",
        },
        format="json",
    )

    assert validate_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut == "Paiement effectué"
    assert order.statut_paiement == "Validé"
    assert order.paiement_valide_par == comptable_user
    assert order.reference_paiement == "SWIFT-001"
    assert order.events.filter(action="Validation paiement").exists()
