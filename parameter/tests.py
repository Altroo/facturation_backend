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
