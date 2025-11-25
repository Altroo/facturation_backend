import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from parameter.models import Ville


@pytest.mark.django_db
class TestParameterAPI:
    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.ville = Ville.objects.create(nom="Casablanca")

    # --- Core CRUD ---
    def test_list_villes(self):
        url = reverse("parameter:ville-list-create")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(v["nom"] == "Casablanca" for v in response.data)

    def test_create_ville(self):
        url = reverse("parameter:ville-list-create")
        payload = {"nom": "Rabat"}
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert Ville.objects.filter(nom="Rabat").exists()

    def test_get_ville_detail(self):
        url = reverse("parameter:ville-detail", args=[self.ville.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["nom"] == "Casablanca"

    def test_update_ville(self):
        url = reverse("parameter:ville-detail", args=[self.ville.id])
        payload = {"nom": "Fès"}
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_200_OK
        self.ville.refresh_from_db()
        assert self.ville.nom == "Fès"

    def test_delete_ville(self):
        url = reverse("parameter:ville-detail", args=[self.ville.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Ville.objects.filter(id=self.ville.id).exists()

    # --- Additional coverage & edge cases ---
    def test_list_villes_ordering_desc_by_id(self):
        v2 = Ville.objects.create(nom="Tanger")
        url = reverse("parameter:ville-list-create")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        ids = [v["id"] for v in response.data]
        assert ids == sorted(ids, reverse=True)
        assert response.data[0]["id"] == v2.id

    def test_create_ville_requires_authentication(self):
        unauth = APIClient()  # not authenticated
        url = reverse("parameter:ville-list-create")
        response = unauth.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response = unauth.post(url, {"nom": "Agadir"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_detail_requires_authentication(self):
        unauth = APIClient()
        url = reverse("parameter:ville-detail", args=[self.ville.id])
        response = unauth.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response = unauth.put(url, {"nom": "Meknès"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response = unauth.delete(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_ville_detail_404(self):
        url = reverse("parameter:ville-detail", args=[999999])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_ville_404(self):
        url = reverse("parameter:ville-detail", args=[999999])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_ville_duplicate_name(self):
        url = reverse("parameter:ville-list-create")
        payload = {"nom": "Casablanca"}  # already exists
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data["details"]

    def test_update_ville_to_duplicate_name(self):
        other = Ville.objects.create(nom="Rabat")
        url = reverse("parameter:ville-detail", args=[other.id])
        payload = {"nom": "Casablanca"}  # would violate unique
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data["details"]
        other.refresh_from_db()
        assert other.nom == "Rabat"

    def test_create_ville_empty_name(self):
        url = reverse("parameter:ville-list-create")
        payload = {"nom": ""}  # invalid
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data["details"]

    def test_update_ville_empty_name(self):
        url = reverse("parameter:ville-detail", args=[self.ville.id])
        payload = {"nom": ""}  # invalid
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nom" in response.data["details"]
        self.ville.refresh_from_db()
        assert self.ville.nom == "Casablanca"

    def test_serializer_fields_shape(self):
        url = reverse("parameter:ville-list-create")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        # ensure only id and nom fields are present
        for item in response.data:
            assert set(item.keys()) == {"id", "nom"}
