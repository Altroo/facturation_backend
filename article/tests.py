import os

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Membership
from article.models import Article
from company.models import Company
from parameter.models import Marque, Categorie, Unite, Emplacement

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
class TestArticleAPI:
    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            raison_sociale="TestCorp",
            ICE="ICE_MAIN",
            registre_de_commerce="RC_MAIN",
            nbr_employe="1 à 5",
        )

        Membership.objects.create(user=self.user, company=self.company)

        # Create parameter objects
        self.marque = Marque.objects.create(nom="TestMarque")
        self.categorie = Categorie.objects.create(nom="TestCategorie")
        self.unite = Unite.objects.create(nom="Pièce")
        self.emplacement = Emplacement.objects.create(nom="Entrepôt A")

        # Create test articles
        self.article_produit = Article.objects.create(
            reference="ART0001",
            designation="Article Test 1",
            type_article="produit",
            company=self.company,
            marque=self.marque,
            categorie=self.categorie,
            unite=self.unite,
            emplacement=self.emplacement,
            prix_achat=100,
            prix_vente=150,
            tva=20,
            remarque="Test remarque",
        )

        self.article_service = Article.objects.create(
            reference="ART0002",
            designation="Service Test 1",
            type_article="service",
            company=self.company,
            prix_vente=200,
            tva=20,
        )

    def _list_url(self, extra=""):
        base = reverse("article:article-list-create")
        params = f"?company_id={self.company.id}"
        if extra:
            params += f"&{extra.lstrip('?')}"
        return f"{base}{params}"

    # --- Core CRUD tests ---
    def test_list_articles(self):
        response = self.client.get(self._list_url())
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_create_article_produit(self):
        url = reverse("article:article-list-create")
        payload = {
            "reference": "ART0003",
            "designation": "Nouveau Produit",
            "type_article": "Produit",
            "company": self.company.id,
            "marque": self.marque.id,
            "categorie": self.categorie.id,
            "unite": self.unite.id,
            "emplacement": self.emplacement.id,
            "prix_achat": 80,
            "prix_vente": 120,
            "tva": 20,
            "remarque": "Test creation",
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Article.objects.filter(reference="ART0003").exists()

    def test_create_article_service(self):
        url = reverse("article:article-list-create")
        payload = {
            "reference": "ART0004",
            "designation": "Nouveau Service",
            "type_article": "Service",
            "company": self.company.id,
            "prix_vente": 250,
            "tva": 20,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Article.objects.filter(reference="ART0004").exists()

    def test_get_article_detail(self):
        url = reverse("article:article-detail", args=[self.article_produit.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reference"] == self.article_produit.reference
        assert response.data["designation"] == self.article_produit.designation
        assert "marque_name" in response.data
        assert "categorie_name" in response.data
        assert "emplacement_name" in response.data
        assert "unite_name" in response.data

    def test_update_article_put(self):
        url = reverse("article:article-detail", args=[self.article_produit.id])
        payload = {
            "reference": self.article_produit.reference,
            "designation": "Updated Designation",
            "type_article": "Produit",
            "company": self.company.id,
            "prix_achat": 110,
            "prix_vente": 160,
            "tva": 20,
        }
        response = self.client.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.article_produit.refresh_from_db()
        assert self.article_produit.designation == "Updated Designation"
        assert self.article_produit.prix_achat == 110

    def test_update_article_patch(self):
        url = reverse("article:article-detail", args=[self.article_produit.id])
        response = self.client.patch(url, {"designation": "Partial Update"})
        assert response.status_code == status.HTTP_200_OK
        self.article_produit.refresh_from_db()
        assert self.article_produit.designation == "Partial Update"

    def test_delete_article(self):
        url = reverse("article:article-detail", args=[self.article_service.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Article.objects.filter(id=self.article_service.id).exists()

    def test_generate_reference_code(self):
        url = reverse("article:article-generate-reference")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reference"].startswith("ART")
        # Should be ART0003 (next after ART0002)
        assert response.data["reference"] == "ART0003"

    def test_generate_reference_code_increments_from_existing(self):
        Article.objects.create(
            reference="ART0010",
            designation="High Number",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        url = reverse("article:article-generate-reference")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        # Should be ART0011
        assert response.data["reference"] == "ART0011"

    def test_generate_reference_code_when_no_articles(self):
        Article.objects.all().delete()
        url = reverse("article:article-generate-reference")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["reference"] == "ART0001"

    def test_archive_toggle(self):
        url = reverse("article:article-archive", args=[self.article_produit.id])
        response = self.client.patch(url, {"archived": True})
        assert response.status_code == status.HTTP_200_OK
        self.article_produit.refresh_from_db()
        assert self.article_produit.archived is True

    def test_archive_toggle_without_field(self):
        url = reverse("article:article-archive", args=[self.article_produit.id])
        original_state = self.article_produit.archived
        response = self.client.patch(url)
        assert response.status_code == status.HTTP_200_OK
        self.article_produit.refresh_from_db()
        assert self.article_produit.archived != original_state

    # --- Pagination & filters ---
    def test_paginated_article_list(self):
        response = self.client.get(self._list_url("pagination=true&page_size=1"))
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert len(response.data["results"]) == 1
        assert "count" in response.data

    def test_filter_archived_true(self):
        self.article_produit.archived = True
        self.article_produit.save()
        response = self.client.get(self._list_url("archived=true"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["reference"] == self.article_produit.reference

    def test_filter_archived_false(self):
        self.article_produit.archived = False
        self.article_produit.save()
        self.article_service.archived = True
        self.article_service.save()
        response = self.client.get(self._list_url("archived=false"))
        assert response.status_code == status.HTTP_200_OK
        assert any(
            article["reference"] == self.article_produit.reference
            for article in response.data
        )

    def test_list_requires_company_id(self):
        base = reverse("article:article-list-create")
        response = self.client.get(base)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # --- Forbidden access cases ---
    def test_list_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp",
            ICE="ICE001",
            registre_de_commerce="RC001",
            nbr_employe="5 à 10",
        )
        url = reverse("article:article-list-create") + f"?company_id={other_company.id}"
        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp2",
            ICE="ICE002",
            registre_de_commerce="RC002",
            nbr_employe="5 à 10",
        )
        url = reverse("article:article-list-create")
        payload = {
            "reference": "ART0100",
            "designation": "Forbidden Article",
            "type_article": "Produit",
            "company": other_company.id,
            "prix_vente": 100,
            "tva": 20,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Article.objects.filter(reference="ART0100").exists()

    def test_detail_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp3",
            ICE="ICE003",
            registre_de_commerce="RC003",
            nbr_employe="5 à 10",
        )
        alien_article = Article.objects.create(
            reference="ART0099",
            designation="Alien Article",
            type_article="produit",
            company=other_company,
            prix_vente=100,
            tva=20,
        )
        url = reverse("article:article-detail", args=[alien_article.id])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_put_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp4",
            ICE="ICE004",
            registre_de_commerce="RC004",
            nbr_employe="5 à 10",
        )
        alien_article = Article.objects.create(
            reference="ART0098",
            designation="Alien Article 2",
            type_article="produit",
            company=other_company,
            prix_vente=100,
            tva=20,
        )
        url = reverse("article:article-detail", args=[alien_article.id])
        payload = {
            "reference": "ART0098",
            "designation": "Updated",
            "type_article": "Produit",
            "company": other_company.id,
            "prix_vente": 150,
            "tva": 20,
        }
        response = self.client.put(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp5",
            ICE="ICE005",
            registre_de_commerce="RC005",
            nbr_employe="5 à 10",
        )
        alien_article = Article.objects.create(
            reference="ART0097",
            designation="Alien Article 3",
            type_article="produit",
            company=other_company,
            prix_vente=100,
            tva=20,
        )
        url = reverse("article:article-detail", args=[alien_article.id])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_archive_toggle_forbidden_without_membership(self):
        other_company = Company.objects.create(
            raison_sociale="OtherCorp6",
            ICE="ICE006",
            registre_de_commerce="RC006",
            nbr_employe="5 à 10",
        )
        alien_article = Article.objects.create(
            reference="ART0500",
            designation="Alien Article 4",
            type_article="service",
            company=other_company,
            prix_vente=200,
            tva=20,
        )
        url = reverse("article:article-archive", args=[alien_article.id])
        response = self.client.patch(url, {"archived": True})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # --- Validation & edge cases ---
    def test_validation_required_fields_missing(self):
        url = reverse("article:article-list-create")
        payload = {
            "type_article": "Produit",
            "company": self.company.id,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "reference" in response.data["details"]
        assert "designation" in response.data["details"]

    def test_get_nonexistent_article_returns_404(self):
        url = reverse("article:article-detail", args=[999999])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_put_nonexistent_article_returns_404(self):
        url = reverse("article:article-detail", args=[999999])
        payload = {
            "reference": "ART9999",
            "designation": "Ghost",
            "type_article": "Produit",
            "company": self.company.id,
            "prix_vente": 100,
            "tva": 20,
        }
        response = self.client.put(url, payload, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_nonexistent_article_returns_404(self):
        url = reverse("article:article-detail", args=[999999])
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_nonexistent_article_returns_404(self):
        url = reverse("article:article-detail", args=[999999])
        response = self.client.patch(url, {"designation": "Nope"})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_archive_toggle_invalid_id(self):
        url = reverse("article:article-archive", args=[999999])
        response = self.client.patch(url, {"archived": True})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_includes_related_names(self):
        response = self.client.get(self._list_url())
        assert response.status_code == status.HTTP_200_OK
        # Check first article has related names
        article = response.data[0]
        assert "company_name" in article
        # For the produit article, these should be present
        if article["reference"] == self.article_produit.reference:
            assert "marque_name" in article
            assert "categorie_name" in article
            assert "emplacement_name" in article
            assert "unite_name" in article


@pytest.mark.django_db
class TestArticleImagesAndPhotos:
    def setup_method(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            email="test@example.com", password="pass"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            raison_sociale="ImgCorp",
            ICE="ICEIMG123",
            registre_de_commerce="RCIMG",
            nbr_employe="1 à 5",
        )
        Membership.objects.create(user=self.user, company=self.company)

    def test_create_article_with_base64_photo(self):
        url = reverse("article:article-list-create")
        payload = {
            "reference": "ART0001",
            "designation": "Article avec photo",
            "type_article": "Produit",
            "company": self.company.id,
            "prix_vente": 100,
            "tva": 20,
            "photo": BASE64_PNG,
        }
        response = self.client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        article = Article.objects.get(reference="ART0001")
        assert article.photo
        assert article.photo.name

        # Check that detail returns URL
        detail_url = reverse("article:article-detail", args=[article.id])
        detail = self.client.get(detail_url)
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["photo"] is None or detail.data["photo"].startswith("http")

    def test_update_article_replaces_photo_with_base64(self):
        # Create article with initial photo
        article = Article.objects.create(
            reference="ART0002",
            designation="Test Replace Photo",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        update_url = reverse("article:article-detail", args=[article.id])

        # Add initial photo
        seed = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        old_photo_name = article.photo.name

        # Replace with new photo
        response = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": BASE64_PNG,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        assert article.photo.name != old_photo_name

        detail = self.client.get(update_url)
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["photo"] is None or detail.data["photo"].startswith("http")

    def test_explicit_null_deletes_photo_file_and_reference(self):
        # Create article with photo
        article = Article.objects.create(
            reference="ART0003",
            designation="Test Delete Photo",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        update_url = reverse("article:article-detail", args=[article.id])

        # Add photo
        seed = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        photo_path = article.photo.path if article.photo else None

        # Delete photo with explicit null
        resp = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": None,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        article.refresh_from_db()

        assert not article.photo
        if photo_path:
            assert not os.path.exists(photo_path)

        detail = self.client.get(update_url)
        assert detail.status_code == status.HTTP_200_OK
        assert detail.data["photo"] is None

    def test_update_with_http_string_does_not_replace_existing_photo(self):
        # Create article with photo
        article = Article.objects.create(
            reference="ART0004",
            designation="Test Keep Photo",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        update_url = reverse("article:article-detail", args=[article.id])

        # Add photo
        seed = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": BASE64_PNG,
            },
            format="json",
        )
        assert seed.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        existing_name = article.photo.name

        # Update with URL string (should keep existing)
        resp = self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": "https://example.com/existing/photo.png",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        assert article.photo.name == existing_name

    def test_patch_photo_field(self):
        article = Article.objects.create(
            reference="ART0005",
            designation="Test Patch Photo",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        url = reverse("article:article-detail", args=[article.id])

        # Add photo with PATCH
        response = self.client.patch(url, {"photo": BASE64_PNG}, format="json")
        assert response.status_code == status.HTTP_200_OK
        article.refresh_from_db()
        assert article.photo
        assert article.photo.name

    def test_list_returns_photo_url(self):
        # Create article with photo
        article = Article.objects.create(
            reference="ART0006",
            designation="Test List Photo",
            type_article="produit",
            company=self.company,
            prix_vente=100,
            tva=20,
        )
        update_url = reverse("article:article-detail", args=[article.id])

        self.client.put(
            update_url,
            {
                "reference": article.reference,
                "designation": article.designation,
                "type_article": "Produit",
                "company": self.company.id,
                "prix_vente": 100,
                "tva": 20,
                "photo": BASE64_PNG,
            },
            format="json",
        )

        # List articles
        list_url = (
            reverse("article:article-list-create") + f"?company_id={self.company.id}"
        )
        response = self.client.get(list_url)
        assert response.status_code == status.HTTP_200_OK

        # Find the article in the list
        article_data = next(
            (item for item in response.data if item["reference"] == "ART0006"), None
        )
        assert article_data is not None
        assert "photo" in article_data
        assert article_data["photo"] is None or article_data["photo"].startswith("http")
