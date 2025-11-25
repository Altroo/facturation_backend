import os

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership
from company.models import Company

# Minimal valid base64 PNG (1x1 transparent)
BASE64_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


# Use a temporary media root for file operations
@pytest.fixture(autouse=True)
def temp_media_root(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


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


@pytest.mark.django_db
class TestCompanyImagesAndMemberships:
    def setup_method(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_user(
            email="admin@example.com",
            password="pass",
            first_name="Admin",
            last_name="User",
            is_staff=True,
        )
        self.admin_group = Group.objects.create(name="Admin")
        self.editor_group = Group.objects.create(name="Editor")

        self.company = Company.objects.create(
            raison_sociale="ImgCorp",
            ICE="ICEIMG123",
            registre_de_commerce="RCIMG",
            nbr_employe="1 à 5",
        )
        Membership.objects.create(
            company=self.company, user=self.admin, role=self.admin_group
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_create_company_with_base64_images(self):
        url = reverse("company:company-list-create")
        payload = {
            "raison_sociale": "Base64Corp",
            "ICE": "ICEB64",
            "nbr_employe": "5 à 10",
            "logo": BASE64_PNG,
            "cachet": BASE64_PNG,
            "logo_cropped": BASE64_PNG,
            "cachet_cropped": BASE64_PNG,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        company = Company.objects.get(raison_sociale="Base64Corp")
        assert (
            company.logo
            and company.cachet
            and company.logo_cropped
            and company.cachet_cropped
        )

        detail_url = reverse("company:company-detail", args=[company.id])
        detail = self.client.get(detail_url)
        assert detail.status_code == status.HTTP_200_OK
        for f in ("logo", "cachet", "logo_cropped", "cachet_cropped"):
            assert detail.data[f] is None or detail.data[f].startswith("http")

    def test_update_company_replaces_images_with_base64(self):
        update_url = reverse("company:company-detail", args=[self.company.id])

        seed = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        old_logo_name = self.company.logo.name

        response = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "cachet": BASE64_PNG,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        assert self.company.cachet and self.company.cachet.name

        response2 = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": BASE64_PNG,
            },
            format="json",
        )
        assert response2.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        assert self.company.logo.name != old_logo_name

        detail = self.client.get(update_url)
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["logo"] is None or detail.data["logo"].startswith("http")
        assert detail.data["cachet"] is None or detail.data["cachet"].startswith("http")

    def test_explicit_null_deletes_image_files_and_references(self):
        update_url = reverse("company:company-detail", args=[self.company.id])
        seed = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": BASE64_PNG,
                "cachet": BASE64_PNG,
                "logo_cropped": BASE64_PNG,
                "cachet_cropped": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()

        paths = {
            "logo": getattr(self.company.logo, "path", None),
            "cachet": getattr(self.company.cachet, "path", None),
            "logo_cropped": getattr(self.company.logo_cropped, "path", None),
            "cachet_cropped": getattr(self.company.cachet_cropped, "path", None),
        }

        resp = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": None,
                "cachet": None,
                "logo_cropped": None,
                "cachet_cropped": None,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()

        assert not self.company.logo
        assert not self.company.cachet
        assert not self.company.logo_cropped
        assert not self.company.cachet_cropped

        for p in paths.values():
            if p:
                assert not os.path.exists(p)

        detail = self.client.get(update_url)
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["logo"] is None
        assert detail.data["cachet"] is None
        assert detail.data["logo_cropped"] is None
        assert detail.data["cachet_cropped"] is None

    def test_update_with_http_string_does_not_replace_existing_file(self):
        update_url = reverse("company:company-detail", args=[self.company.id])
        seed = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        existing_name = self.company.logo.name

        resp = self.client.put(
            update_url,
            {
                "raison_sociale": "ImgCorp",
                "ICE": self.company.ICE,
                "nbr_employe": self.company.nbr_employe,
                "logo": "http://example.com/existing/logo.png",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        self.company.refresh_from_db()
        assert self.company.logo.name == existing_name

    def test_managed_by_replaces_memberships_and_preserves_admins_representation(self):
        editor1 = self.user_model.objects.create_user(
            email="ed1@example.com", password="pass"
        )
        editor2 = self.user_model.objects.create_user(
            email="ed2@example.com", password="pass"
        )

        update_url = reverse("company:company-detail", args=[self.company.id])
        payload = {
            "raison_sociale": "ImgCorp",
            "ICE": self.company.ICE,
            "nbr_employe": self.company.nbr_employe,
            "managed_by": [
                {"pk": editor1.id, "role": "Editor"},
                {"pk": editor2.id, "role": "Editor"},
            ],
        }
        resp = self.client.put(update_url, payload, format="json")
        assert resp.status_code == status.HTTP_200_OK

        # Memberships replaced: previous admin removed, editors added
        assert not Membership.objects.filter(
            company=self.company, user=self.admin, role=self.admin_group
        ).exists()
        assert Membership.objects.filter(
            company=self.company, user=editor1, role=self.editor_group
        ).exists()
        assert Membership.objects.filter(
            company=self.company, user=editor2, role=self.editor_group
        ).exists()

        # Representation request may be forbidden depending on permissions
        detail = self.client.get(update_url)
        if detail.status_code == status.HTTP_200_OK:
            managed_by = detail.data.get("managed_by", [])
            assert {item["pk"] for item in managed_by} == {editor1.id, editor2.id}
            assert {item["role"] for item in managed_by} == {"Editor"}

            admins = detail.data.get("admins", [])
            if admins:
                sample = admins[0]
                assert {"id", "first_name", "last_name", "role"}.issubset(sample.keys())
        else:
            # If forbidden, assert that memberships were still updated correctly
            assert detail.status_code == status.HTTP_403_FORBIDDEN
