from re import match
from urllib.parse import quote

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership
from article.models import Article
from client.models import Client
from company.models import Company
from devi.models import Devi, DeviLine
from parameter.models import ModePaiement, Ville


@pytest.mark.django_db
class TestDeviAPI:

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="user@dev.com", password="pass"
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        # core objects
        self.ville = Ville.objects.create(nom="TestVille")
        self.company = Company.objects.create(
            raison_sociale="TestCompany", ICE="ICE-1234"
        )

        # attach membership and set header so views that check company membership pass
        Membership.objects.create(user=self.user, company=self.company)
        self.client_api.credentials(HTTP_COMPANY=str(self.company.id))

        self.client_obj = Client.objects.create(
            code_client="CLT1000",
            client_type="PM",
            raison_sociale="TestClient",
            ICE="ICE1000",
            registre_de_commerce="RC1000",
            delai_de_paiement=30,
            ville=self.ville,
            company=self.company,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="Bank Transfer")

        # Article requires company and unique reference
        self.article = Article.objects.create(
            company=self.company,
            reference="ART-001",
            designation="Test Article",
            prix_achat=100,
            prix_vente=120,
            type_article="Produit",
        )

        # Devi: provide unique numero_devis
        self.devi = Devi.objects.create(
            numero_devis="0002/25",
            client=self.client_obj,
            date_devis="2024-06-01",
            numero_demande_prix_client="REQ-001",
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            created_by_user=self.user,
        )

        # create a DeviLine via API (API bug fixed so POST sets `devis`)
        url = reverse("devi:devi-line-list-create")
        payload_line = {
            "devis": self.devi.id,
            "article": self.article.id,
            "prix_achat": 100,
            "prix_vente": 120,
            "quantity": 2,
            "pourcentage_remise": 5,
        }
        response = self.client_api.post(url, payload_line, format="json")
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"DeviLine POST failed: {response.status_code} {response.data}"
        self.devi_line = DeviLine.objects.get(
            devis=self.devi, article=self.article, prix_achat=100
        )

    def test_list_devis(self):
        # endpoint requires a client_id query param
        url = reverse("devi:devi-list-create") + f"?client_id={self.client_obj.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(d["id"] == self.devi.id for d in response.data)

    def test_create_devi(self):
        url = reverse("devi:devi-list-create")
        payload = {
            "numero_devis": "0003/25",
            "client": self.client_obj.id,
            "date_devis": "2024-06-02",
            "numero_demande_prix_client": "REQ-002",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "New remark",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        devi = Devi.objects.get(numero_devis=payload["numero_devis"])
        assert devi is not None
        assert devi.created_by_user == self.user

    def test_get_devi_detail(self):
        url = reverse("devi:devi-detail", args=[self.devi.id])
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["numero_devis"] == self.devi.numero_devis

    def test_update_devi(self):
        url = reverse("devi:devi-detail", args=[self.devi.id])
        payload = {
            "numero_devis": self.devi.numero_devis,
            "client": self.client_obj.id,
            "date_devis": "2024-06-03",
            "numero_demande_prix_client": "REQ-003",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Updated remark",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.devi.refresh_from_db()
        assert self.devi.remarque == "Updated remark"
        assert self.devi.created_by_user == self.user

    def test_delete_devi(self):
        url = reverse("devi:devi-detail", args=[self.devi.id])
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Devi.objects.filter(id=self.devi.id).exists()

    def test_list_devi_lines(self):
        # endpoint requires devis_id query param
        url = reverse("devi:devi-line-list-create") + f"?devis_id={self.devi.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        # response includes article id for each line
        assert any(line.get("article") == self.article.id for line in response.data)

    def test_create_devi_line(self):
        url = reverse("devi:devi-line-list-create")
        payload = {
            "devis": self.devi.id,
            "article": self.article.id,
            "prix_achat": 200,
            "prix_vente": 250,
            "quantity": 3,
            "pourcentage_remise": 10,
        }
        # send JSON so DRF parses relation fields correctly
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        # confirm object created and linked to the correct devi
        assert DeviLine.objects.filter(
            prix_achat=200, devis=self.devi, article=self.article
        ).exists()
        # if serializer returns the created object, basic checks:
        if isinstance(response.data, dict):
            assert response.data.get("article") == self.article.id

    def test_filter_devi_by_statut(self):
        # DeviListCreateView requires client_id parameter
        url = (
            reverse("devi:devi-list-create")
            + f"?client_id={self.client_obj.id}&statut=Brouillon"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        # ensure all returned devi have the requested statut
        assert all(devi.get("statut") == "Brouillon" for devi in response.data)

    def test_search_devi_by_numero(self):
        # use existing object from setup
        numero = self.devi.numero_devis
        url = (
            reverse("devi:devi-list-create")
            + f"?client_id={self.client_obj.id}&search={quote(numero, safe='')}"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(numero in devi.get("numero_devis", "") for devi in response.data)

    def test_generate_numero_devis(self):
        url = reverse("devi:generate-numero-devis")
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "numero_devis" in response.data
        assert match(r"\d{4}/\d{2}", response.data["numero_devis"])

    def test_update_devi_status(self):
        url = reverse("devi:devi-status-update", args=[self.devi.id])
        payload = {"statut": "Accepté"}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.devi.refresh_from_db()
        assert self.devi.statut == "Accepté"

    def test_filter_deviline_by_devis_id(self):
        url = reverse("devi:devi-line-list-create") + f"?devis_id={self.devi.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        # response doesn't include 'devis' key; assert returned lines contain the expected article id
        assert any(line.get("article") == self.article.id for line in response.data)
