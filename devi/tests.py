from datetime import datetime
from re import match
from urllib.parse import quote

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership
from article.models import Article
from client.models import Client
from company.models import Company
from devi.models import Devi, DeviLine
from parameter.models import ModePaiement, Ville
from .filters import DeviLineFilter, DeviFilter


@pytest.mark.django_db
class TestDeviAPI:

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="user@dev.com", password="pass", first_name="Test", last_name="User"
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        # Core objects
        self.ville = Ville.objects.create(nom="TestVille")
        self.company = Company.objects.create(
            raison_sociale="TestCompany", ICE="ICE-1234"
        )

        # Attach membership
        Membership.objects.create(user=self.user, company=self.company)

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

        # Article with company and unique reference
        self.article = Article.objects.create(
            company=self.company,
            reference="ART-001",
            designation="Test Article",
            prix_achat=100,
            prix_vente=120,
            type_article="Produit",
        )

        # Devi with unique numero_devis, include devi-level remise fields
        self.devi = Devi.objects.create(
            numero_devis="0002/25",
            client=self.client_obj,
            date_devis="2024-06-01",
            numero_demande_prix_client="REQ-001",
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        # Create a DeviLine (updated fields: remise + remise_type)
        self.devi_line = DeviLine.objects.create(
            devis=self.devi,
            article=self.article,
            prix_achat=100,
            prix_vente=120,
            quantity=2,
            remise=5,
            remise_type="Pourcentage",
        )

    def test_list_devis_requires_client_id(self):
        """List endpoint requires company_id parameter."""
        url = reverse("devi:devi-list-create")
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_devis(self):
        """List devis for a specific company."""
        url = reverse("devi:devi-list-create") + f"?company_id={self.company.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert any(d["id"] == self.devi.id for d in response.data)
        # Check list serializer fields
        devi_data = next(d for d in response.data if d["id"] == self.devi.id)
        assert "client_name" in devi_data
        assert "mode_paiement_name" in devi_data
        assert "created_by_user_name" in devi_data
        assert "lignes_count" in devi_data
        assert devi_data["lignes_count"] == 1
        # Ensure devi-level remise fields are present
        assert "remise" in devi_data
        assert "remise_type" in devi_data
        # Ensure totals are present and numeric or None
        for key in ("total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in devi_data
            assert devi_data.get(key) is None or isinstance(
                devi_data.get(key), (int, float)
            )

    def test_list_devis_with_pagination(self):
        """List devis with pagination enabled."""
        url = (
            reverse("devi:devi-list-create")
            + f"?company_id={self.company.id}&pagination=true"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        # Paginated response has results array
        assert "results" in response.data
        assert "count" in response.data
        # Ensure totals exist on items
        if response.data["results"]:
            item = response.data["results"][0]
            for key in ("total_tva", "total_ttc", "total_ttc_apres_remise"):
                assert key in item
                assert item.get(key) is None or isinstance(item.get(key), (int, float))

    def test_create_devi_basic(self):
        """Create a basic devi without lines."""
        url = reverse("devi:devi-list-create")
        payload = {
            "numero_devis": "0003/25",
            "client": self.client_obj.id,
            "date_devis": "2024-06-02",
            "numero_demande_prix_client": "REQ-002",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "New remark",
            "remise": 0,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Verify response structure (uses DeviDetailSerializer)
        assert "lignes" in response.data
        assert response.data["numero_devis"] == "0003/25"
        assert response.data["created_by_user"] == self.user.id
        # Newly created devi includes remise fields
        assert response.data.get("remise") == 0
        assert response.data.get("remise_type") == "Pourcentage"
        # Totals present (may be None if no lines) and numeric when present
        for key in ("total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert response.data.get(key) is None or isinstance(
                response.data.get(key), (int, float)
            )

        # Verify DB
        devi = Devi.objects.get(numero_devis=payload["numero_devis"])
        assert devi.created_by_user == self.user
        assert devi.statut == "Brouillon"  # default status

    def test_create_devi_with_lignes(self):
        """Create devi with nested lines."""
        url = reverse("devi:devi-list-create")
        payload = {
            "numero_devis": "0004/25",
            "client": self.client_obj.id,
            "date_devis": "2024-06-05",
            "numero_demande_prix_client": "REQ-010",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "With lines",
            "remise": 0,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    "article": self.article.id,
                    "prix_achat": 150,
                    "prix_vente": 180,
                    "quantity": 1,
                    "remise": 0,
                    "remise_type": "Pourcentage",
                }
            ],
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Response includes detailed lignes
        assert isinstance(response.data.get("lignes"), list)
        assert len(response.data["lignes"]) == 1
        line = response.data["lignes"][0]
        assert line.get("article") == self.article.id
        assert line.get("prix_achat") == 150
        assert "id" in line
        assert "designation" in line  # from DeviLineSerializer
        assert "reference" in line
        # Totals present and numeric
        for key in ("total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert response.data.get(key) is None or isinstance(
                response.data.get(key), (int, float)
            )

        # Verify DB
        devi = Devi.objects.get(pk=response.data["id"])
        assert DeviLine.objects.filter(devis=devi, article=self.article).exists()

    def test_get_devi_detail(self):
        """Get detailed devi with nested lines."""
        url = reverse("devi:devi-detail", args=[self.devi.id])
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["numero_devis"] == self.devi.numero_devis

        # Detail includes lignes
        assert isinstance(response.data.get("lignes"), list)
        assert len(response.data["lignes"]) == 1
        ligne = response.data["lignes"][0]
        assert ligne.get("article") == self.article.id
        assert ligne.get("designation") == self.article.designation
        assert ligne.get("reference") == self.article.reference
        # Ensure devi-level remise fields are present
        assert response.data.get("remise") == 0
        assert response.data.get("remise_type") == "Pourcentage"
        # Totals present and numeric
        for key in ("total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert response.data.get(key) is None or isinstance(
                response.data.get(key), (int, float)
            )

    def test_create_devi_without_client_fails(self):
        """Creating devi without client should fail."""
        url = reverse("devi:devi-list-create")
        payload = {
            "numero_devis": "0010/25",
            "date_devis": "2024-06-02",
            "remise": 0,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_devi_invalid_numero_format(self):
        """Creating devi with invalid numero format should fail."""
        url = reverse("devi:devi-list-create")
        payload = {
            "numero_devis": "INVALID",
            "client": self.client_obj.id,
            "date_devis": "2024-06-02",
            "numero_demande_prix_client": "REQ-002",
            "remise": 0,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Check if error is in nested structure or flat structure
        if "details" in response.data:
            assert "numero_devis" in response.data["details"]
        else:
            assert "numero_devis" in response.data

    def test_get_devi_detail_unauthorized(self):
        """User without membership cannot access devi."""
        other_user = CustomUser.objects.create_user(
            email="other@dev.com", password="pass"
        )
        client = APIClient()
        client.force_authenticate(user=other_user)

        url = reverse("devi:devi-detail", args=[self.devi.id])
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_devi_basic(self):
        """Update devi basic fields."""
        url = reverse("devi:devi-detail", args=[self.devi.id])
        payload = {
            "numero_devis": self.devi.numero_devis,
            "client": self.client_obj.id,
            "date_devis": "2024-06-03",
            "numero_demande_prix_client": "REQ-003",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Updated remark",
            "remise": 0,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify DB
        self.devi.refresh_from_db()
        assert self.devi.remarque == "Updated remark"
        assert self.devi.date_devis.isoformat() == "2024-06-03"
        assert self.devi.created_by_user == self.user  # preserved

    def test_update_devi_with_lignes_upsert(self):
        """Update devi with upsert logic: update existing, add new lines."""
        url = reverse("devi:devi-detail", args=[self.devi.id])
        payload = {
            "numero_devis": self.devi.numero_devis,
            "client": self.client_obj.id,
            "date_devis": "2024-06-07",
            "numero_demande_prix_client": "REQ-004",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Upsert lines",
            "remise": 0,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    # Update existing line
                    "id": self.devi_line.id,
                    "article": self.article.id,
                    "prix_achat": 110,
                    "prix_vente": 130,
                    "quantity": 5,
                    "remise": 2,
                    "remise_type": "Pourcentage",
                },
                {
                    # Add new line (no id)
                    "article": self.article.id,
                    "prix_achat": 200,
                    "prix_vente": 250,
                    "quantity": 3,
                    "remise": 10,
                    "remise_type": "Pourcentage",
                },
            ],
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Existing line updated
        self.devi_line.refresh_from_db()
        assert self.devi_line.prix_achat == 110
        assert self.devi_line.quantity == 5

        # New line created
        assert DeviLine.objects.filter(devis=self.devi, prix_achat=200).exists()

        # Response includes both lines
        returned_lines = response.data.get("lignes", [])
        assert len(returned_lines) == 2

    def test_update_devi_delete_missing_lines(self):
        """Lines not in update payload should be deleted."""
        # Create a second line
        line2 = DeviLine.objects.create(
            devis=self.devi,
            article=self.article,
            prix_achat=50,
            prix_vente=60,
            quantity=1,
            remise=0,
            remise_type="Pourcentage",
        )

        url = reverse("devi:devi-detail", args=[self.devi.id])
        payload = {
            "numero_devis": self.devi.numero_devis,
            "client": self.client_obj.id,
            "date_devis": "2024-06-08",
            "numero_demande_prix_client": "REQ-005",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Delete line2",
            "remise": 0,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    # Only include line1
                    "id": self.devi_line.id,
                    "article": self.article.id,
                    "prix_achat": 100,
                    "prix_vente": 120,
                    "quantity": 2,
                    "remise": 5,
                    "remise_type": "Pourcentage",
                }
            ],
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # line2 should be deleted
        assert not DeviLine.objects.filter(id=line2.id).exists()
        assert DeviLine.objects.filter(devis=self.devi).count() == 1

    def test_delete_devi(self):
        """Delete devi."""
        url = reverse("devi:devi-detail", args=[self.devi.id])
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Devi.objects.filter(id=self.devi.id).exists()
        # Cascade delete lines
        assert not DeviLine.objects.filter(devis=self.devi).exists()

    def test_filter_devi_by_statut(self):
        """Filter devis by statut."""
        # Create devi with different status
        Devi.objects.create(
            numero_devis="0005/25",
            client=self.client_obj,
            date_devis="2024-06-10",
            numero_demande_prix_client="REQ-006",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        url = (
            reverse("devi:devi-list-create")
            + f"?company_id={self.company.id}&statut=Brouillon"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert all(devi.get("statut") == "Brouillon" for devi in response.data)

    def test_search_devi_by_numero(self):
        """Search devis by numero."""
        numero = self.devi.numero_devis
        url = (
            reverse("devi:devi-list-create")
            + f"?company_id={self.company.id}&search={quote(numero, safe='')}"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(numero in devi.get("numero_devis", "") for devi in response.data)

    def test_generate_numero_devis(self):
        """Generate next available numero_devis, filling gaps first."""
        year_suffix = f"{datetime.now().year % 100:02d}"

        # Clear any existing devis from setup_method
        Devi.objects.all().delete()

        # Setup: create some Devi entries
        Devi.objects.create(
            numero_devis=f"0001/{year_suffix}",
            client=self.client_obj,
            date_devis="2024-06-01",
            mode_paiement=self.mode_paiement,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        Devi.objects.create(
            numero_devis=f"0002/{year_suffix}",
            client=self.client_obj,
            date_devis="2024-06-02",
            mode_paiement=self.mode_paiement,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        Devi.objects.create(
            numero_devis=f"0008/{year_suffix}",
            client=self.client_obj,
            date_devis="2024-06-03",
            mode_paiement=self.mode_paiement,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        url = reverse("devi:generate-numero-devis")
        response = self.client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "numero_devis" in response.data
        assert match(r"^\d{4}/\d{2}$", response.data["numero_devis"])
        assert response.data["numero_devis"] == f"0003/{year_suffix}"

    def test_update_devi_status(self):
        """Update devi status via dedicated endpoint."""
        url = reverse("devi:devi-statut-update", args=[self.devi.id])
        payload = {"statut": "Accepté"}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "Accepté"

        # Verify DB
        self.devi.refresh_from_db()
        assert self.devi.statut == "Accepté"

    def test_update_devi_status_invalid(self):
        """Invalid status should fail."""
        url = reverse("devi:devi-statut-update", args=[self.devi.id])
        payload = {"statut": "InvalidStatus"}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # DeviLine endpoints tests
    def test_list_devi_lines_requires_devis_id(self):
        """List lines endpoint requires devis_id parameter."""
        url = reverse("devi:devi-line-list-create")
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_devi_lines(self):
        """List lines for a specific devi."""
        url = reverse("devi:devi-line-list-create") + f"?devis_id={self.devi.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) == 1
        assert response.data[0]["article"] == self.article.id

    def test_create_devi_line(self):
        """Create a new devi line."""
        url = reverse("devi:devi-line-list-create")
        payload = {
            "devis": self.devi.id,
            "article": self.article.id,
            "prix_achat": 150,
            "prix_vente": 180,
            "quantity": 3,
            "remise": 5,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["prix_achat"] == 150

        # Verify DB
        assert DeviLine.objects.filter(devis=self.devi, prix_achat=150).exists()

    def test_get_devi_line_detail(self):
        """Get a specific devi line."""
        url = reverse("devi:devi-line-detail-edit-delete", args=[self.devi_line.id])
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.devi_line.id
        assert response.data["designation"] == self.article.designation

    def test_update_devi_line(self):
        """Update a devi line via PUT."""
        url = reverse("devi:devi-line-detail-edit-delete", args=[self.devi_line.id])
        payload = {
            "devis": self.devi.id,
            "article": self.article.id,
            "prix_achat": 200,
            "prix_vente": 250,
            "quantity": 10,
            "remise": 15,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify DB
        self.devi_line.refresh_from_db()
        assert self.devi_line.prix_achat == 200
        assert self.devi_line.quantity == 10

    def test_partial_update_devi_line(self):
        """Partial update a devi line via PATCH."""
        url = reverse("devi:devi-line-detail-edit-delete", args=[self.devi_line.id])
        payload = {"quantity": 15}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify DB
        self.devi_line.refresh_from_db()
        assert self.devi_line.quantity == 15
        # Other fields unchanged
        assert self.devi_line.prix_achat == 100

    def test_delete_devi_line(self):
        """Delete a devi line."""
        url = reverse("devi:devi-line-detail-edit-delete", args=[self.devi_line.id])
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not DeviLine.objects.filter(id=self.devi_line.id).exists()


@pytest.mark.django_db
class TestDeviFilters:
    def setup_method(self):
        user_object = get_user_model()
        self.user = user_object.objects.create_user(
            email="filter@dev.com", password="p"
        )

        self.ville = Ville.objects.create(nom="SearchVille")
        self.company = Company.objects.create(raison_sociale="FilterCo", ICE="ICEFILT")
        Membership.objects.create(user=self.user, company=self.company)

        self.client_a = Client.objects.create(
            code_client="C001",
            client_type="PM",
            raison_sociale="Client Alpha",
            company=self.company,
            ville=self.ville,
        )
        self.client_b = Client.objects.create(
            code_client="C002",
            client_type="PM",
            raison_sociale="Other Client",
            company=self.company,
            ville=self.ville,
        )

        self.mode = ModePaiement.objects.create(nom="Cash")

        self.devi1 = Devi.objects.create(
            numero_devis="NUM-001",
            client=self.client_a,
            date_devis="2024-06-01",
            numero_demande_prix_client="REQ-ALPHA",
            mode_paiement=self.mode,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.devi2 = Devi.objects.create(
            numero_devis="NUM-002",
            client=self.client_b,
            date_devis="2024-06-02",
            numero_demande_prix_client="REQ-BETA",
            mode_paiement=self.mode,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=self.user,
            statut="Accepté",
        )

    def test_global_search_matches_numero_and_client_and_req(self):
        filt = DeviFilter({"search": "NUM-001"}, queryset=Devi.objects.all())
        assert self.devi1 in filt.qs
        assert self.devi2 not in filt.qs

        filt_client = DeviFilter(
            {"search": "client alpha"}, queryset=Devi.objects.all()
        )
        assert self.devi1 in filt_client.qs

        filt_req = DeviFilter({"search": "REQ-BETA"}, queryset=Devi.objects.all())
        assert self.devi2 in filt_req.qs

    def test_filter_statut_case_insensitive_and_trim(self):
        filt = DeviFilter({"statut": "brouillon"}, queryset=Devi.objects.all())
        # devi1 default statut should be Brouillon
        assert self.devi1 in filt.qs
        filt_accept = DeviFilter(
            {"statut": " accept\u00e9 "}, queryset=Devi.objects.all()
        )  # trimmed + case-insensitive
        assert self.devi2 in filt_accept.qs

    def test_client_id_filter(self):
        filt = DeviFilter({"client_id": self.client_a.id}, queryset=Devi.objects.all())
        qs = list(filt.qs)
        assert qs == [self.devi1]

    def test_empty_search_returns_queryset_unchanged(self):
        base_qs = Devi.objects.all()
        filt = DeviFilter({"search": "   "}, queryset=base_qs)
        assert set(filt.qs) == set(base_qs)


@pytest.mark.django_db
class TestDeviLineFilters:
    def setup_method(self):
        self.ville = Ville.objects.create(nom="LineVille")
        self.company = Company.objects.create(raison_sociale="LineCo", ICE="ICELINE")
        self.client = Client.objects.create(
            code_client="CLN1",
            client_type="PM",
            raison_sociale="LineClient",
            company=self.company,
            ville=self.ville,
        )
        self.mode = ModePaiement.objects.create(nom="Card")
        self.devi = Devi.objects.create(
            numero_devis="DL-001",
            client=self.client,
            date_devis="2024-06-01",
            mode_paiement=self.mode,
            remise=0,
            remise_type="Pourcentage",
            created_by_user=None,
        )

        self.article_a = Article.objects.create(
            company=self.company,
            reference="REF-A",
            designation="FindThisArticle",
            prix_achat=10,
            prix_vente=15,
            type_article="Produit",
        )
        self.article_b = Article.objects.create(
            company=self.company,
            reference="REF-B",
            designation="OtherArticle",
            prix_achat=5,
            prix_vente=8,
            type_article="Produit",
        )

        self.line = DeviLine.objects.create(
            devis=self.devi,
            article=self.article_a,
            prix_achat=10,
            prix_vente=15,
            quantity=1,
            remise=0,
            remise_type="Pourcentage",
        )

    def test_global_search_matches_article_designation_and_reference(self):
        filt = DeviLineFilter(
            {"search": "FindThisArticle"}, queryset=DeviLine.objects.all()
        )
        assert self.line in filt.qs

        filt_ref = DeviLineFilter({"search": "REF-A"}, queryset=DeviLine.objects.all())
        assert self.line in filt_ref.qs

    def test_empty_search_returns_queryset_unchanged(self):
        base_qs = DeviLine.objects.filter(devis=self.devi)
        filt = DeviLineFilter({"search": ""}, queryset=base_qs)
        assert set(filt.qs) == set(base_qs)
