from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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


def valid_logistics_payload(logistics_company, logistics_user, proforma, **overrides):
    payload = {
        "company_id": logistics_company.id,
        "proformas": [proforma.id],
        "date_prevue": "2026-07-20",
        "origine_marchandise": "Espagne",
        "nature_marchandise": "Articles de test",
    }
    payload.update(overrides)
    return payload


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
        numero_bon_commande_client="PROJET-LOG-001",
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
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, brand_a, brand_b = logistics_proformas
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        valid_logistics_payload(
            logistics_company,
            logistics_user,
            proforma,
            brand_details=[
                {
                    "marque": brand_a.id,
                    "date_prevue": "2026-07-20",
                    "origine_marchandise": "Espagne",
                    "nature_marchandise": "Articles marque A",
                },
                {
                    "marque": brand_b.id,
                    "date_prevue": "2026-07-22",
                    "origine_marchandise": "France",
                    "nature_marchandise": "Articles marque B",
                },
            ],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["created"] == 2
    orders = LogisticsOrder.objects.order_by("marque__nom")
    assert [order.marque_id for order in orders] == [brand_a.id, brand_b.id]
    assert [order.lignes.count() for order in orders] == [1, 1]
    assert orders[0].fournisseur == ""
    assert orders[0].origine_marchandise == "Espagne"
    assert orders[1].origine_marchandise == "France"
    assert orders[0].cout_achat == Decimal("200.000")
    assert orders[0].cout_total == Decimal("200.000")
    assert orders[0].lignes.first().project_reference == "PROJET-LOG-001"
    assert LogisticsOrderEvent.objects.filter(action="Création").count() == 2


def test_create_logistics_order_rejects_missing_required_fields(
    api_client, logistics_company, logistics_proformas
):
    proforma, _, _ = logistics_proformas
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        {"company_id": logistics_company.id, "proformas": [proforma.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "brand_details" in response.data["details"]
    assert LogisticsOrder.objects.count() == 0


def test_logistics_source_preview_groups_by_brand(
    api_client, logistics_company, logistics_proformas
):
    proforma, brand_a, brand_b = logistics_proformas
    url = reverse("logistique:logistique-source-preview")

    response = api_client.post(
        url,
        {"company_id": logistics_company.id, "proformas": [proforma.id]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert [brand["marque"] for brand in response.data["brands"]] == [
        brand_a.id,
        brand_b.id,
    ]
    assert response.data["brands"][0]["devise"] == "MAD"
    assert response.data["proformas"][0]["numero_facture"] == "P001/26"


def test_create_logistics_order_rejects_mixed_purchase_currencies(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    proforma, brand_a, _ = logistics_proformas
    line = FactureProFormaLine.objects.filter(article__marque=brand_a).first()
    FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=line.article,
        prix_achat=Decimal("50.00"),
        devise_prix_achat="EUR",
        prix_vente=Decimal("75.00"),
        devise_prix_vente="EUR",
        quantity=1,
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.post(
        url,
        valid_logistics_payload(
            logistics_company,
            logistics_user,
            proforma,
            brand_details=[
                {
                    "marque": brand_a.id,
                    "date_prevue": "2026-07-20",
                    "origine_marchandise": "Espagne",
                    "nature_marchandise": "Articles marque A",
                }
            ],
        ),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "plusieurs devises d'achat" in str(response.data["details"]["proformas"])
    assert LogisticsOrder.objects.count() == 0


def test_logistics_list_returns_dashboard_stats(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    _, brand_a, brand_b = logistics_proformas
    test_create_logistics_orders_splits_proforma_lines_by_brand(
        api_client, logistics_company, logistics_user, logistics_proformas
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
    assert response.data["stats"]["couts_logistiques"] == Decimal("400.00")
    assert response.data["stats"]["couts_detail"]["transport"] == Decimal("0.00")
    assert response.data["stats"]["statuts_workflow"] == [
        {"statut": "Réception commande", "total": 2}
    ]
    assert response.data["stats"]["statuts_paiement"] == [
        {"statut_paiement": "Non demandé", "total": 2}
    ]
    assert response.data["stats"]["marques"] == [
        {"id": brand_a.id, "nom": "Brand A"},
        {"id": brand_b.id, "nom": "Brand B"},
    ]
    assert [item["marque__nom"] for item in response.data["stats"]["kpi_marques"]] == [
        "Brand A",
        "Brand B",
    ]
    assert len(response.data["stats"]["monthly_flow"]) == 6
    assert {
        "month",
        "commandes",
        "livraisons",
        "paiements",
        "cout_total",
    }.issubset(response.data["stats"]["monthly_flow"][-1].keys())


def test_logistics_filters_accept_selectable_multi_values(
    api_client, logistics_company, logistics_user, logistics_proformas
):
    _, brand_a, brand_b = logistics_proformas
    test_create_logistics_orders_splits_proforma_lines_by_brand(
        api_client, logistics_company, logistics_user, logistics_proformas
    )
    LogisticsOrder.objects.filter(marque__nom="Brand A").update(
        statut="Réception commande",
        statut_paiement="Non demandé",
        statut_titre_importation="À ouvrir",
    )
    LogisticsOrder.objects.filter(marque__nom="Brand B").update(
        statut="Transit",
        statut_paiement="Validé",
        statut_titre_importation="Validé",
    )
    url = reverse("logistique:logistique-list-create")

    response = api_client.get(
        url,
        {
            "company_id": logistics_company.id,
            "pagination": "true",
            "marque_ids": f"{brand_a.id},{brand_b.id}",
            "statut": "Réception commande,Transit",
            "statut_paiement": "Non demandé,Validé",
            "statut_titre_importation": "À ouvrir,Validé",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 2


def test_comptable_can_validate_requested_payment(
    api_client, logistics_company, logistics_user, logistics_proformas, comptable_user
):
    test_create_logistics_orders_splits_proforma_lines_by_brand(
        api_client, logistics_company, logistics_user, logistics_proformas
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
    swift_file = SimpleUploadedFile(
        "swift.pdf",
        b"%PDF-1.4 swift",
        content_type="application/pdf",
    )
    validate_response = comptable_client.post(
        validate_url,
        {
            "date_paiement": "2026-07-04",
            "montant_paiement": "250.00",
            "reference_paiement": "SWIFT-001",
            "methode_paiement": "Virement",
            "swift_file": swift_file,
        },
        format="multipart",
    )

    assert validate_response.status_code == status.HTTP_200_OK
    order.refresh_from_db()
    assert order.statut == "Paiement effectué"
    assert order.statut_paiement == "Validé"
    assert order.paiement_valide_par == comptable_user
    assert order.reference_paiement == "SWIFT-001"
    assert order.swift_file
    assert order.date_upload_swift is not None
    assert order.events.filter(action="Validation paiement").exists()


def test_logistics_responsible_options_are_company_scoped(
    api_client, logistics_company, logistics_user
):
    url = reverse("logistique:logistique-responsables")

    response = api_client.get(url, {"company_id": logistics_company.id})

    assert response.status_code == status.HTTP_200_OK
    assert response.data == [
        {
            "id": logistics_user.id,
            "first_name": "Log",
            "last_name": "User",
            "email": "logistics@example.com",
            "role": "Caissier",
            "label": "Log User - Caissier",
        }
    ]
