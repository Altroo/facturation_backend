import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from client.models import Client
from company.models import Company
from parameter.models import Ville


@pytest.mark.django_db
class TestClientAPI:
    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.ville = Ville.objects.create(nom="Casablanca")
        self.company = Company.objects.create(raison_sociale="TestCorp")

        self.client_pm = Client.objects.create(
            code_client="CLT0001",
            client_type=Client.PERSONNE_MORALE,
            raison_sociale="Société X",
            ICE="123456789",
            registre_de_commerce="RC123",
            delai_de_paiement=30,
            ville=self.ville,
            company=self.company,
        )

        self.client_pp = Client.objects.create(
            code_client="CLT0002",
            client_type=Client.PERSONNE_PHYSIQUE,
            nom="Ali",
            prenom="Ben",
            adresse="123 Rue",
            tel="+212600000000",
            delai_de_paiement=45,
            ville=self.ville,
        )

    def test_list_clients(self):
        url = reverse("client:client-list-create")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_create_client_pm(self):
        url = reverse("client:client-list-create")
        payload = {
            "code_client": "CLT0003",
            "client_type": "PM",
            "raison_sociale": "Société Y",
            "ICE": "987654321",
            "registre_de_commerce": "RC456",
            "delai_de_paiement": 60,
            "ville": self.ville.id,
            "company": self.company.id,
        }
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert Client.objects.filter(code_client="CLT0003").exists()

    def test_create_client_pp(self):
        url = reverse("client:client-list-create")
        payload = {
            "code_client": "CLT0004",
            "client_type": "PP",
            "nom": "Fatima",
            "prenom": "Zahra",
            "adresse": "456 Avenue",
            "tel": "+212611111111",
            "delai_de_paiement": 30,
            "ville": self.ville.id,
        }
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert Client.objects.filter(code_client="CLT0004").exists()

    def test_get_client_detail(self):
        url = reverse("client:client-detail", args=[self.client_pm.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code_client"] == self.client_pm.code_client

    def test_update_client(self):
        url = reverse("client:client-detail", args=[self.client_pm.id])
        payload = {
            "code_client": self.client_pm.code_client,
            "client_type": "PM",
            "raison_sociale": "Updated Société",
            "ville": self.ville.id,
            "ICE": "123456789",
            "registre_de_commerce": "RC123",
            "delai_de_paiement": 30,
            "company": self.company.id,
        }
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_200_OK
        self.client_pm.refresh_from_db()
        assert self.client_pm.raison_sociale == "Updated Société"

    def test_update_client_pp(self):
        url = reverse("client:client-detail", args=[self.client_pp.id])
        payload = {
            "code_client": self.client_pp.code_client,
            "client_type": "PP",
            "nom": "Updated Ali",
            "prenom": "Updated Ben",
            "adresse": "789 Boulevard",
            "tel": "+212622222222",
            "delai_de_paiement": 60,
            "ville": self.ville.id,
        }
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_200_OK
        self.client_pp.refresh_from_db()
        assert self.client_pp.nom == "Updated Ali"
        assert self.client_pp.prenom == "Updated Ben"

    def test_delete_client(self):
        url = reverse("client:client-detail", args=[self.client_pp.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Client.objects.filter(id=self.client_pp.id).exists()

    def test_generate_code(self):
        url = reverse("client:client-generate-code")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code_client"].startswith("CLT")

    def test_archive_toggle(self):
        url = reverse("client:client-archive", args=[self.client_pp.id])
        response = self.client.patch(url, {"archived": True})
        assert response.status_code == status.HTTP_200_OK
        self.client_pp.refresh_from_db()
        assert self.client_pp.archived is True

    def test_archive_toggle_without_field(self):
        url = reverse("client:client-archive", args=[self.client_pp.id])
        original_state = self.client_pp.archived
        response = self.client.patch(url)
        assert response.status_code == status.HTTP_200_OK
        self.client_pp.refresh_from_db()
        assert self.client_pp.archived != original_state

    def test_paginated_client_list(self):
        url = reverse("client:client-list-create")
        response = self.client.get(url + "?pagination=true&page_size=1")
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) == 1
        assert "count" in response.data

    def test_filter_archived_true(self):
        self.client_pp.archived = True
        self.client_pp.save()
        url = reverse("client:client-list-create")
        response = self.client.get(url + "?archived=true&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert all(
            client["code_client"] == self.client_pp.code_client
            for client in response.data["results"]
        )

    def test_filter_archived_false(self):
        self.client_pp.archived = False
        self.client_pp.save()
        url = reverse("client:client-list-create")
        response = self.client.get(url + "?archived=false&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert any(
            client["code_client"] == self.client_pm.code_client
            for client in response.data["results"]
        )

    def test_search_client_by_code(self):
        url = reverse("client:client-list-create")
        response = self.client.get(url + "?search=CLT0001&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert any(
            client["code_client"] == "CLT0001" for client in response.data["results"]
        )

    def test_search_client_by_name(self):
        self.client_pp.nom = "Fatima"
        self.client_pp.save()
        url = reverse("client:client-list-create")
        response = self.client.get(url + "?search=Fatima&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert any(
            client.get("nom") and "Fatima" in client["nom"]
            for client in response.data["results"]
        )
