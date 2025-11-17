import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership
from company.models import Company


@pytest.mark.django_db
class TestCompanyAPI:
    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="admin@example.com",
            password="pass",
            first_name="Admin",
            last_name="User",
            is_staff=True,
        )
        self.admin_group = Group.objects.create(name="Admin")
        self.company = Company.objects.create(
            raison_sociale="TestCorp",
            ICE="ICE123456",
            registre_de_commerce="RC999",
            nbr_employe="1 à 5",
        )
        Membership.objects.create(
            company=self.company, user=self.user, role=self.admin_group
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_companies(self):
        url = reverse("company:company-list-create")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(
            c["raison_sociale"] == self.company.raison_sociale for c in response.data
        )

    def test_create_company(self):
        url = reverse("company:company-list-create")
        payload = {
            "raison_sociale": "NewCorp",
            "ICE": "ICE654321",
            "nbr_employe": "5 à 10",
        }
        response = self.client.post(url, payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert Company.objects.filter(raison_sociale="NewCorp").exists()
        assert Membership.objects.filter(
            company__raison_sociale="NewCorp", user=self.user, role=self.admin_group
        ).exists()

    def test_get_company_detail(self):
        url = reverse("company:company-detail", args=[self.company.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["raison_sociale"] == "TestCorp"

    def test_update_company(self):
        url = reverse("company:company-detail", args=[self.company.id])
        payload = {
            "raison_sociale": "UpdatedCorp",
            "ICE": self.company.ICE,
            "nbr_employe": "10 à 50",
        }
        response = self.client.put(url, payload)
        assert response.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        assert self.company.raison_sociale == "UpdatedCorp"

    def test_delete_company(self):
        url = reverse("company:company-detail", args=[self.company.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Company.objects.filter(id=self.company.id).exists()

    def test_non_admin_cannot_access_company_detail(self):
        outsider = self.user_model.objects.create_user(
            email="user@example.com", password="pass"
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)
        url = reverse("company:company-detail", args=[self.company.id])
        response = outsider_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_paginated_company_list(self):
        second_company = Company.objects.create(
            raison_sociale="AnotherCorp",
            ICE="ICE000111",
            registre_de_commerce="RC123",
            nbr_employe="10 à 50",
        )
        Membership.objects.create(
            company=second_company, user=self.user, role=self.admin_group
        )

        url = reverse("company:company-list-create")
        response = self.client.get(url + "?pagination=true&page_size=1")
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) == 1
        assert "count" in response.data
        assert response.data["count"] >= 2

    def test_search_company_by_raison_sociale(self):
        url = reverse("company:company-list-create")
        response = self.client.get(url + "?search=TestCorp&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert any(
            company["raison_sociale"] == "TestCorp"
            for company in response.data["results"]
        )

    def test_search_company_by_ice(self):
        url = reverse("company:company-list-create")
        response = self.client.get(url + "?search=ICE123456&pagination=true")
        assert response.status_code == status.HTTP_200_OK
        assert any(
            company["ICE"] == "ICE123456" for company in response.data["results"]
        )
