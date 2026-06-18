from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from facture_client.models import FactureClient, FactureClientLine
from parameter.models import ModePaiement, Ville
from .models import FactureAvoir, FactureAvoirLine


pytestmark = pytest.mark.django_db


@pytest.fixture
def avoir_context():
    user = CustomUser.objects.create_user(
        email="avoir@example.com",
        password="pass",
        first_name="Credit",
        last_name="Note",
    )
    company = Company.objects.create(raison_sociale="Avoir Co", ICE="ICE-AVOIR")
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(user=user, company=company, role=role)
    ville = Ville.objects.create(nom="Avoir Ville", company=company)
    client = Client.objects.create(
        code_client="AVC001",
        client_type="PM",
        raison_sociale="Avoir Client",
        ville=ville,
        company=company,
    )
    mode_paiement = ModePaiement.objects.create(nom="Virement", company=company)
    article = Article.objects.create(
        company=company,
        reference="AV-ART-001",
        designation="Article avoir",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )
    facture = FactureClient.objects.create(
        numero_facture="0001/26",
        client=client,
        date_facture=timezone.localdate(),
        mode_paiement=mode_paiement,
        statut="Envoyé",
        created_by_user=user,
    )
    FactureClientLine.objects.create(
        facture_client=facture,
        article=article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=Decimal("2.00"),
        remise_type="",
        remise=Decimal("0.00"),
    )
    facture.recalc_totals()
    facture.save()
    api_client = APIClient()
    api_client.force_authenticate(user=user)
    return {
        "api_client": api_client,
        "user": user,
        "company": company,
        "client": client,
        "mode_paiement": mode_paiement,
        "article": article,
        "facture": facture,
    }


def _line_payload(article, quantity="1.00"):
    return {
        "article": article.id,
        "prix_achat": "80.00",
        "devise_prix_achat": "MAD",
        "prix_vente": "100.00",
        "devise_prix_vente": "MAD",
        "quantity": quantity,
        "remise_type": "",
        "remise": "0.00",
    }


def test_create_avoir_from_facture_assigns_legal_number_and_origin_data(avoir_context):
    url = reverse("facture_avoir:facture-avoir-list-create")
    response = avoir_context["api_client"].post(
        url,
        {
            "facture_origine": avoir_context["facture"].id,
            "date_avoir": str(timezone.localdate()),
            "motif_avoir": "retour_marchandise",
            "lignes": [_line_payload(avoir_context["article"])],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["numero_avoir"].endswith(f"/{timezone.localdate().year % 100:02d}")
    assert response.data["client"] == avoir_context["client"].id
    assert response.data["facture_origine"] == avoir_context["facture"].id


def test_create_free_avoir_requires_client_and_allows_no_origin(avoir_context):
    url = reverse("facture_avoir:facture-avoir-list-create")
    response = avoir_context["api_client"].post(
        url,
        {
            "client": avoir_context["client"].id,
            "date_avoir": str(timezone.localdate()),
            "motif_avoir": "autre",
            "mode_paiement": avoir_context["mode_paiement"].id,
            "lignes": [_line_payload(avoir_context["article"])],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["facture_origine"] is None
    assert response.data["client"] == avoir_context["client"].id


def test_active_origin_avoir_cannot_credit_more_than_original_quantity(avoir_context):
    existing = FactureAvoir.objects.create(
        facture_origine=avoir_context["facture"],
        client=avoir_context["client"],
        company=avoir_context["company"],
        date_avoir=timezone.localdate(),
        motif_avoir="retour_marchandise",
        statut="Envoyé",
        created_by_user=avoir_context["user"],
    )
    FactureAvoirLine.objects.create(
        facture_avoir=existing,
        article=avoir_context["article"],
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=Decimal("2.00"),
    )
    existing.recalc_totals()
    existing.save()

    response = avoir_context["api_client"].post(
        reverse("facture_avoir:facture-avoir-list-create"),
        {
            "facture_origine": avoir_context["facture"].id,
            "date_avoir": str(timezone.localdate()),
            "motif_avoir": "retour_marchandise",
            "lignes": [_line_payload(avoir_context["article"], "1.00")],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "lignes" in response.data["details"]


def test_avoir_delete_is_not_allowed(avoir_context):
    avoir = FactureAvoir.objects.create(
        client=avoir_context["client"],
        company=avoir_context["company"],
        date_avoir=timezone.localdate(),
        motif_avoir="autre",
        created_by_user=avoir_context["user"],
    )

    response = avoir_context["api_client"].delete(
        reverse("facture_avoir:facture-avoir-detail", kwargs={"pk": avoir.pk})
    )

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.parametrize(
    "pdf_type", ["avec_unite_sans_remise", "avec_unite_avec_remise"]
)
def test_avoir_pdf_accepts_explicit_unit_variants(avoir_context, pdf_type):
    avoir = FactureAvoir.objects.create(
        client=avoir_context["client"],
        company=avoir_context["company"],
        date_avoir=timezone.localdate(),
        motif_avoir="autre",
        mode_paiement=avoir_context["mode_paiement"],
        created_by_user=avoir_context["user"],
    )
    FactureAvoirLine.objects.create(
        facture_avoir=avoir,
        article=avoir_context["article"],
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=Decimal("1.00"),
        remise_type="Pourcentage",
        remise=Decimal("10.00"),
    )
    avoir.recalc_totals()
    avoir.save()

    response = avoir_context["api_client"].get(
        reverse("facture_avoir:facture-avoir-pdf-fr", kwargs={"pk": avoir.pk})
        + f"?company_id={avoir_context['company'].id}&type={pdf_type}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
