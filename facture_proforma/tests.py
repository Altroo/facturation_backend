from datetime import datetime
from re import match
from types import SimpleNamespace
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
from core.tests import is_numeric_or_none, assert_numeric_equal
from parameter.models import ModePaiement, Ville
from .filters import FactureProFormaFilter
from .models import FactureProForma, FactureProFormaLine


@pytest.mark.django_db
class TestFactureProFormaAPI:

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
            prix_achat=100.00,
            prix_vente=120.00,
            type_article="Produit",
        )

        self.facture_pro_forma = FactureProForma.objects.create(
            numero_facture="0002/25",
            client=self.client_obj,
            date_facture="2024-06-01",
            numero_bon_commande_client="REQ-001",
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        self.facture_pro_forma_line = FactureProFormaLine.objects.create(
            facture_pro_forma=self.facture_pro_forma,
            article=self.article,
            prix_achat=100.00,
            prix_vente=120.00,
            quantity=2,
            remise=5.00,
            remise_type="Pourcentage",
        )

    def test_list_proforma_requires_client_id(self):
        """List endpoint requires company_id parameter."""
        url = reverse("facture_proforma:facture-proforma-list-create")
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_proforma(self):
        """List pro forma for a specific company."""
        url = (
            reverse("facture_proforma:facture-proforma-list-create")
            + f"?company_id={self.company.id}"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert any(d["id"] == self.facture_pro_forma.id for d in response.data)
        # Check list serializer fields
        proforma_data = next(
            d for d in response.data if d["id"] == self.facture_pro_forma.id
        )
        assert "client_name" in proforma_data
        assert "mode_paiement_name" in proforma_data
        assert "created_by_user_name" in proforma_data
        assert "lignes_count" in proforma_data
        assert proforma_data["lignes_count"] == 1
        # Ensure pro forma-level remise fields are present
        assert "remise" in proforma_data
        assert "remise_type" in proforma_data
        # Ensure totals are present and numeric or None
        for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in proforma_data
            assert is_numeric_or_none(proforma_data.get(key))

    def test_list_proforma_with_pagination(self):
        """List pro forma with pagination enabled."""
        url = (
            reverse("facture_proforma:facture-proforma-list-create")
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
            for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
                assert key in item
                assert is_numeric_or_none(item.get(key))

    def test_create_proforma_basic(self):
        """Create a basic pro forma without lines."""
        url = reverse("facture_proforma:facture-proforma-list-create")
        payload = {
            "numero_facture": "0003/25",
            "client": self.client_obj.id,
            "date_facture": "2024-06-02",
            "numero_bon_commande_client": "REQ-002",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "New remark",
            "remise": 0.00,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Verify response structure (uses proformaDetailSerializer)
        assert "lignes" in response.data
        assert response.data["numero_facture"] == "0003/25"
        assert response.data["created_by_user"] == self.user.id
        # Newly created pro forma includes remise fields
        assert_numeric_equal(response.data.get("remise"), 0.00)
        assert response.data.get("remise_type") == "Pourcentage"
        # Totals present (may be None if no lines) and numeric when present
        for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert is_numeric_or_none(response.data.get(key))

        # Verify DB
        proforma = FactureProForma.objects.get(numero_facture=payload["numero_facture"])
        assert proforma.created_by_user == self.user
        assert proforma.statut == "Brouillon"  # default status

    def test_create_proforma_with_lignes(self):
        """Create pro forma with nested lines."""
        url = reverse("facture_proforma:facture-proforma-list-create")
        payload = {
            "numero_facture": "0004/25",
            "client": self.client_obj.id,
            "date_facture": "2024-06-05",
            "numero_bon_commande_client": "REQ-010",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "With lines",
            "remise": 0.00,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    "article": self.article.id,
                    "prix_achat": 150.00,
                    "prix_vente": 180.00,
                    "quantity": 1,
                    "remise": 0.00,
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
        assert_numeric_equal(line.get("prix_achat"), 150.00)
        assert "id" in line
        assert "designation" in line  # from proformaLineSerializer
        assert "reference" in line
        # Totals present and numeric
        for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert is_numeric_or_none(response.data.get(key))

        # Verify DB
        facture_pro_forma = FactureProForma.objects.get(pk=response.data["id"])
        assert FactureProFormaLine.objects.filter(
            facture_pro_forma=facture_pro_forma, article=self.article
        ).exists()

    def test_get_proforma_detail(self):
        """Get detailed pro forma with nested lines."""
        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["numero_facture"] == self.facture_pro_forma.numero_facture

        # Detail includes lignes
        assert isinstance(response.data.get("lignes"), list)
        assert len(response.data["lignes"]) == 1
        ligne = response.data["lignes"][0]
        assert ligne.get("article") == self.article.id
        assert ligne.get("designation") == self.article.designation
        assert ligne.get("reference") == self.article.reference
        # Ensure pro forma-level remise fields are present
        assert_numeric_equal(response.data.get("remise"), 0.00)
        assert response.data.get("remise_type") == "Pourcentage"
        # Totals present and numeric
        for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in response.data
            assert is_numeric_or_none(response.data.get(key))

    def test_create_proforma_without_client_fails(self):
        """Creating pro forma without client should fail."""
        url = reverse("facture_proforma:facture-proforma-list-create")
        payload = {
            "numero_facture": "0010/25",
            "date_facture": "2024-06-02",
            "remise": 0.00,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_proforma_invalid_numero_format(self):
        """Creating pro forma with invalid numero format should fail."""
        url = reverse("facture_proforma:facture-proforma-list-create")
        payload = {
            "numero_facture": "INVALID",
            "client": self.client_obj.id,
            "date_facture": "2024-06-02",
            "numero_bon_commande_client": "REQ-002",
            "remise": 0.00,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Check if error is in nested structure or flat structure
        if "details" in response.data:
            assert "numero_facture" in response.data["details"]
        else:
            assert "numero_facture" in response.data

    def test_get_proforma_detail_unauthorized(self):
        """User without membership cannot access pro forma."""
        other_user = CustomUser.objects.create_user(
            email="other@dev.com", password="pass"
        )
        client = APIClient()
        client.force_authenticate(user=other_user)

        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_proforma_basic(self):
        """Update pro forma basic fields."""
        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        payload = {
            "numero_facture": self.facture_pro_forma.numero_facture,
            "client": self.client_obj.id,
            "date_facture": "2024-06-03",
            "numero_bon_commande_client": "REQ-003",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Updated remark",
            "remise": 0.00,
            "remise_type": "Pourcentage",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify DB
        self.facture_pro_forma.refresh_from_db()
        assert self.facture_pro_forma.remarque == "Updated remark"
        assert self.facture_pro_forma.date_facture.isoformat() == "2024-06-03"
        assert self.facture_pro_forma.created_by_user == self.user  # preserved

    def test_update_proforma_with_lignes_upsert(self):
        """Update pro forma with upsert logic: update existing, add new lines."""
        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        payload = {
            "numero_facture": self.facture_pro_forma.numero_facture,
            "client": self.client_obj.id,
            "date_facture": "2024-06-07",
            "numero_bon_commande_client": "REQ-004",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Upsert lines",
            "remise": 0.00,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    # Update existing line
                    "id": self.facture_pro_forma_line.id,
                    "article": self.article.id,
                    "prix_achat": 110.00,
                    "prix_vente": 130.00,
                    "quantity": 5,
                    "remise": 2.00,
                    "remise_type": "Pourcentage",
                },
                {
                    # Add new line (no id)
                    "article": self.article.id,
                    "prix_achat": 200.00,
                    "prix_vente": 250.00,
                    "quantity": 3,
                    "remise": 10.00,
                    "remise_type": "Pourcentage",
                },
            ],
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Existing line updated
        self.facture_pro_forma_line.refresh_from_db()
        assert_numeric_equal(self.facture_pro_forma_line.prix_achat, 110.00)
        assert self.facture_pro_forma_line.quantity == 5

        # New line created
        assert FactureProFormaLine.objects.filter(
            facture_pro_forma=self.facture_pro_forma, prix_achat=200
        ).exists()

        # Response includes both lines
        returned_lines = response.data.get("lignes", [])
        assert len(returned_lines) == 2

    def test_update_proforma_delete_missing_lines(self):
        """Lines not in update payload should be deleted."""
        # Create a second line
        line2 = FactureProFormaLine.objects.create(
            facture_pro_forma=self.facture_pro_forma,
            article=self.article,
            prix_achat=50.00,
            prix_vente=60.00,
            quantity=1,
            remise=0.00,
            remise_type="Pourcentage",
        )

        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        payload = {
            "numero_facture": self.facture_pro_forma.numero_facture,
            "client": self.client_obj.id,
            "date_facture": "2024-06-08",
            "numero_bon_commande_client": "REQ-005",
            "mode_paiement": self.mode_paiement.id,
            "remarque": "Delete line2",
            "remise": 0.00,
            "remise_type": "Pourcentage",
            "lignes": [
                {
                    # Only include line1
                    "id": self.facture_pro_forma_line.id,
                    "article": self.article.id,
                    "prix_achat": 100.00,
                    "prix_vente": 120.00,
                    "quantity": 2,
                    "remise": 5.00,
                    "remise_type": "Pourcentage",
                }
            ],
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        # line2 should be deleted
        assert not FactureProFormaLine.objects.filter(id=line2.id).exists()
        assert (
            FactureProFormaLine.objects.filter(
                facture_pro_forma=self.facture_pro_forma
            ).count()
            == 1
        )

    def test_delete_proforma(self):
        """Delete pro forma."""
        url = reverse(
            "facture_proforma:facture-proforma-detail",
            args=[self.facture_pro_forma.id],
        )
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not FactureProForma.objects.filter(id=self.facture_pro_forma.id).exists()
        # Cascade delete lines
        assert not FactureProFormaLine.objects.filter(
            facture_pro_forma=self.facture_pro_forma
        ).exists()

    def test_filter_proforma_by_statut(self):
        """Filter pro forma by statut."""
        # Create pro forma with different status
        FactureProForma.objects.create(
            numero_facture="0005/25",
            client=self.client_obj,
            date_facture="2024-06-10",
            numero_bon_commande_client="REQ-006",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        url = (
            reverse("facture_proforma:facture-proforma-list-create")
            + f"?company_id={self.company.id}&statut=Brouillon"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert all(proforma.get("statut") == "Brouillon" for proforma in response.data)

    def test_search_proforma_by_numero(self):
        """Search pro forma by numero."""
        numero = self.facture_pro_forma.numero_facture
        url = (
            reverse("facture_proforma:facture-proforma-list-create")
            + f"?company_id={self.company.id}&search={quote(numero, safe='')}"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert any(
            numero in proforma.get("numero_facture", "") for proforma in response.data
        )

    def test_generate_numero_facture(self):
        """Generate next available numero_facture, filling gaps first."""
        year_suffix = f"{datetime.now().year % 100:02d}"

        # Clear any existing pro forma from setup_method
        FactureProForma.objects.all().delete()

        # Setup: create some pro forma entries
        FactureProForma.objects.create(
            numero_facture=f"0001/{year_suffix}",
            client=self.client_obj,
            date_facture="2024-06-01",
            mode_paiement=self.mode_paiement,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        FactureProForma.objects.create(
            numero_facture=f"0002/{year_suffix}",
            client=self.client_obj,
            date_facture="2024-06-02",
            mode_paiement=self.mode_paiement,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        FactureProForma.objects.create(
            numero_facture=f"0008/{year_suffix}",
            client=self.client_obj,
            date_facture="2024-06-03",
            mode_paiement=self.mode_paiement,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        url = reverse("facture_proforma:generate-numero-facture-proforma")
        response = self.client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "numero_facture" in response.data
        assert match(r"^\d{4}/\d{2}$", response.data["numero_facture"])
        assert response.data["numero_facture"] == f"0003/{year_suffix}"

    def test_update_proforma_status(self):
        """Update pro forma status via dedicated endpoint."""
        url = reverse(
            "facture_proforma:facture-proforma-statut-update",
            args=[self.facture_pro_forma.id],
        )
        payload = {"statut": "Accepté"}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "Accepté"

        # Verify DB
        self.facture_pro_forma.refresh_from_db()
        assert self.facture_pro_forma.statut == "Accepté"

    def test_update_proforma_status_invalid(self):
        """Invalid status should fail."""
        url = reverse(
            "facture_proforma:facture-proforma-statut-update",
            args=[self.facture_pro_forma.id],
        )
        payload = {"statut": "InvalidStatus"}
        response = self.client_api.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_convert_to_facture_client(self, monkeypatch):
        """POST convert facture pro forma to facture client returns created id (201)."""
        url = reverse(
            "facture_proforma:convert-to-facture-client",
            args=[self.facture_pro_forma.id],
        )
        # Replace the model method to avoid depending on external apps
        monkeypatch.setattr(
            FactureProForma,
            "convert_to_facture_client",
            lambda self_obj, numero_facture, created_by_user: SimpleNamespace(id=999),
        )
        response = self.client_api.post(url, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data.get("id") == 999


@pytest.mark.django_db
class TestFactureProFormaFilters:
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

        self.facture_pro_forma1 = FactureProForma.objects.create(
            numero_facture="NUM-001",
            client=self.client_a,
            date_facture="2024-06-01",
            numero_bon_commande_client="REQ-ALPHA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.facture_pro_forma2 = FactureProForma.objects.create(
            numero_facture="NUM-002",
            client=self.client_b,
            date_facture="2024-06-02",
            numero_bon_commande_client="REQ-BETA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
            statut="Accepté",
        )

    def test_global_search_matches_numero_and_client_and_req(self):
        filt = FactureProFormaFilter(
            {"search": "NUM-001"}, queryset=FactureProForma.objects.all()
        )
        assert self.facture_pro_forma1 in filt.qs
        assert self.facture_pro_forma2 not in filt.qs

        filt_client = FactureProFormaFilter(
            {"search": "client alpha"}, queryset=FactureProForma.objects.all()
        )
        assert self.facture_pro_forma1 in filt_client.qs

        filt_req = FactureProFormaFilter(
            {"search": "REQ-BETA"}, queryset=FactureProForma.objects.all()
        )
        assert self.facture_pro_forma2 in filt_req.qs

    def test_filter_statut_case_insensitive_and_trim(self):
        filt = FactureProFormaFilter(
            {"statut": "brouillon"}, queryset=FactureProForma.objects.all()
        )
        # proforma1 default statut should be Brouillon
        assert self.facture_pro_forma1 in filt.qs
        filt_accept = FactureProFormaFilter(
            {"statut": " accept\u00e9 "}, queryset=FactureProForma.objects.all()
        )  # trimmed + case-insensitive
        assert self.facture_pro_forma2 in filt_accept.qs

    def test_client_id_filter(self):
        filt = FactureProFormaFilter(
            {"client_id": self.client_a.id}, queryset=FactureProForma.objects.all()
        )
        qs = list(filt.qs)
        assert qs == [self.facture_pro_forma1]

    def test_empty_search_returns_queryset_unchanged(self):
        base_qs = FactureProForma.objects.all()
        filt = FactureProFormaFilter({"search": "   "}, queryset=base_qs)
        assert set(filt.qs) == set(base_qs)
