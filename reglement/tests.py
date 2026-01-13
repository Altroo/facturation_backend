from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership
from article.models import Article
from client.models import Client
from company.models import Company
from facture_client.models import FactureClient, FactureClientLine
from parameter.models import ModePaiement, Ville
from .filters import ReglementFilter
from .models import Reglement

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


@pytest.fixture
def reglement_user():
    return CustomUser.objects.create_user(
        email="reglement@example.com",
        password="pass",
        first_name="Reglement",
        last_name="User",
    )


@pytest.fixture
def reglement_company():
    return Company.objects.create(raison_sociale="Reglement Co", ICE="REGLCO")


@pytest.fixture
def reglement_ville():
    return Ville.objects.create(nom="ReglementVille")


@pytest.fixture
def reglement_client(reglement_ville, reglement_company):
    return Client.objects.create(
        code_client="REGL001",
        client_type="PM",
        raison_sociale="Reglement Client",
        ville=reglement_ville,
        company=reglement_company,
    )


@pytest.fixture
def reglement_mode_paiement():
    return ModePaiement.objects.create(nom="ReglementPay")


@pytest.fixture
def reglement_mode_reglement():
    return ModePaiement.objects.create(nom="Espèces")


@pytest.fixture
def reglement_mode_reglement_cheque():
    return ModePaiement.objects.create(nom="Chèque")


@pytest.fixture
def reglement_article(reglement_company):
    return Article.objects.create(
        company=reglement_company,
        reference="REGL001",
        designation="Reglement Article",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )


@pytest.fixture
def reglement_facture(reglement_client, reglement_mode_paiement, reglement_user):
    """Create a facture with total_ttc_apres_remise = 1200 (100*2*1.2 = 240 TTC for 2 items)."""
    facture = FactureClient.objects.create(
        numero_facture="REG/01",
        client=reglement_client,
        date_facture="2025-01-01",
        mode_paiement=reglement_mode_paiement,
        statut="Accepté",
        created_by_user=reglement_user,
        remise=Decimal("0.00"),
        remise_type="",
    )
    return facture


@pytest.fixture
def reglement_facture_with_lines(reglement_facture, reglement_article):
    """Create facture with lines. Total = 100 * 5 = 500 HT, + 20% TVA = 600 TTC."""
    FactureClientLine.objects.create(
        facture_client=reglement_facture,
        article=reglement_article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=5,
    )
    reglement_facture.recalc_totals()
    reglement_facture.save()
    return reglement_facture


@pytest.fixture
def reglement_obj(reglement_facture_with_lines, reglement_mode_reglement):
    """Create a reglement of 200 for a facture of 600 TTC."""
    return Reglement.objects.create(
        facture_client=reglement_facture_with_lines,
        mode_reglement=reglement_mode_reglement,
        libelle="Premier règlement",
        montant=Decimal("200.00"),
        date_reglement="2025-01-15",
        date_echeance="2025-02-15",
        statut="Valide",
    )


@pytest.fixture
def reglement_membership(reglement_user, reglement_company):
    return Membership.objects.create(user=reglement_user, company=reglement_company)


# -----------------------------------------------------------------------------
# Model Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementModel:
    """Tests for Reglement model."""

    def test_str_representation(self, reglement_obj):
        """Test string representation."""
        expected = f"Règlement {reglement_obj.id} - {reglement_obj.facture_client.numero_facture}"
        assert str(reglement_obj) == expected

    def test_get_total_reglements_for_facture(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test calculating total règlements for a facture."""
        # Initial state - no reglements
        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id
        )
        assert total == Decimal("0.00")

        # Add first reglement
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test 1",
            montant=Decimal("100.00"),
            statut="Valide",
        )
        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id
        )
        assert total == Decimal("100.00")

        # Add second reglement
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test 2",
            montant=Decimal("150.00"),
            statut="Valide",
        )
        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id
        )
        assert total == Decimal("250.00")

    def test_get_total_reglements_excludes_annule(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that annulé règlements are excluded from total."""
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Valid",
            montant=Decimal("100.00"),
            statut="Valide",
        )
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Cancelled",
            montant=Decimal("50.00"),
            statut="Annulé",
        )

        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id
        )
        assert total == Decimal("100.00")

    def test_get_total_reglements_with_exclude_id(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test excluding specific reglement from total calculation."""
        reg1 = Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test 1",
            montant=Decimal("100.00"),
            statut="Valide",
        )
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test 2",
            montant=Decimal("150.00"),
            statut="Valide",
        )

        # Exclude first reglement
        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id, exclude_reglement_id=reg1.id
        )
        assert total == Decimal("150.00")

    def test_get_reste_a_payer(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test calculating reste à payer."""
        # Facture total is 600 TTC (500 HT + 20% TVA)
        reste = Reglement.get_reste_a_payer(reglement_facture_with_lines)
        assert reste == Decimal("600.00")

        # Add reglement of 200
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test",
            montant=Decimal("200.00"),
            statut="Valide",
        )
        reste = Reglement.get_reste_a_payer(reglement_facture_with_lines)
        assert reste == Decimal("400.00")

    def test_default_statut_is_valide(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that default status is Valide."""
        reglement = Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Test",
            montant=Decimal("100.00"),
        )
        assert reglement.statut == "Valide"


# -----------------------------------------------------------------------------
# API Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementAPI:
    """Tests for Reglement API endpoints."""

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="api_user@dev.com",
            password="pass",
            first_name="Test",
            last_name="User",
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        self.ville = Ville.objects.create(nom="APIVille")
        self.company = Company.objects.create(
            raison_sociale="API Company", ICE="API-1234"
        )
        Membership.objects.create(user=self.user, company=self.company)

        self.client_obj = Client.objects.create(
            code_client="API001",
            client_type="PM",
            raison_sociale="API Client",
            ICE="APIICE",
            ville=self.ville,
            company=self.company,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="API Payment")
        self.mode_reglement = ModePaiement.objects.create(nom="API Règlement")

        self.article = Article.objects.create(
            company=self.company,
            reference="API-ART",
            designation="API Article",
            prix_achat=100.00,
            prix_vente=120.00,
            tva=20,
        )

        # Create facture with 1000 TTC total
        self.facture = FactureClient.objects.create(
            numero_facture="API/01",
            client=self.client_obj,
            date_facture="2025-01-01",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            created_by_user=self.user,
        )
        FactureClientLine.objects.create(
            facture_client=self.facture,
            article=self.article,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("1000.00"),  # High price to get 1000 HT
            quantity=1,
        )
        self.facture.recalc_totals()
        self.facture.save()
        # Total is 1000 HT + 20% TVA = 1200 TTC

        self.reglement = Reglement.objects.create(
            facture_client=self.facture,
            mode_reglement=self.mode_reglement,
            libelle="Initial payment",
            montant=Decimal("300.00"),
            date_reglement="2025-01-15",
            date_echeance="2025-02-15",
            statut="Valide",
        )

    @staticmethod
    def _list_create_url():
        return reverse("reglement:reglement-list-create")

    @staticmethod
    def _detail_url(pk):
        return reverse("reglement:reglement-detail", args=[pk])

    @staticmethod
    def _status_url(pk):
        return reverse("reglement:reglement-statut-update", args=[pk])

    def test_list_requires_company_id(self):
        """Test that list requires company_id."""
        url = self._list_create_url()
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_reglements(self):
        """Test listing règlements."""
        url = self._list_create_url() + f"?company_id={self.company.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "chiffre_affaire_total" in response.data
        assert "total_reglements" in response.data
        assert "total_impayes" in response.data

    def test_list_reglements_with_pagination(self):
        """Test listing règlements with pagination."""
        url = self._list_create_url() + f"?company_id={self.company.id}&pagination=true"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "count" in response.data
        assert "chiffre_affaire_total" in response.data

    def test_list_aggregated_stats(self):
        """Test that aggregated stats are correct."""
        url = self._list_create_url() + f"?company_id={self.company.id}"
        response = self.client_api.get(url)

        # Facture total = 1200 TTC, reglement = 300
        assert Decimal(response.data["chiffre_affaire_total"]) == Decimal("1200.00")
        assert Decimal(response.data["total_reglements"]) == Decimal("300.00")
        assert Decimal(response.data["total_impayes"]) == Decimal("900.00")

    def test_create_reglement(self):
        """Test creating a règlement."""
        url = self._list_create_url()
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "New payment",
            "montant": "200.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["libelle"] == "New payment"
        assert Decimal(response.data["montant"]) == Decimal("200.00")

    def test_create_reglement_exceeds_reste(self):
        """Test that creating a règlement exceeding reste à payer fails."""
        url = self._list_create_url()
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Too much",
            "montant": "1000.00",  # Reste is only 900 (1200 - 300)
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Check that montant error is in the response (could be nested in 'details')
        assert "montant" in response.data or "montant" in response.data.get(
            "details", {}
        )

    def test_create_reglement_negative_montant(self):
        """Test that creating a règlement with negative montant fails."""
        url = self._list_create_url()
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Negative",
            "montant": "-100.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_reglement_zero_montant(self):
        """Test that creating a règlement with zero montant fails."""
        url = self._list_create_url()
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Zero",
            "montant": "0.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_multiple_reglements_scenario(self):
        """Test the scenario: facture 1000, reglement1 500, reglement2 200, remaining 300."""
        # Create a fresh facture with 1000 TTC
        facture2 = FactureClient.objects.create(
            numero_facture="API/02",
            client=self.client_obj,
            date_facture="2025-01-02",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            created_by_user=self.user,
        )
        FactureClientLine.objects.create(
            facture_client=facture2,
            article=self.article,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("833.33"),  # ~833.33 HT * 1.2 TVA ≈ 1000 TTC
            quantity=1,
        )
        facture2.recalc_totals()
        facture2.save()

        url = self._list_create_url()

        # First reglement: 500
        payload1 = {
            "facture_client": facture2.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Espèces",
            "montant": "500.00",
            "date_reglement": "2025-01-15",
            "date_echeance": "2025-02-15",
        }
        response1 = self.client_api.post(url, payload1, format="json")
        assert response1.status_code == status.HTTP_201_CREATED

        # Second reglement: 200
        payload2 = {
            "facture_client": facture2.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Chèque",
            "montant": "200.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response2 = self.client_api.post(url, payload2, format="json")
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify reste à payer
        reste = Reglement.get_reste_a_payer(facture2)
        expected_reste = facture2.total_ttc_apres_remise - Decimal("700.00")
        assert reste == expected_reste

        # Third reglement exceeding remaining should fail
        payload3 = {
            "facture_client": facture2.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Too much",
            "montant": str(reste + Decimal("1.00")),  # 1 more than remaining
            "date_reglement": "2025-01-25",
            "date_echeance": "2025-02-25",
        }
        response3 = self.client_api.post(url, payload3, format="json")
        assert response3.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_reglement_detail(self):
        """Test getting règlement detail."""
        url = self._detail_url(self.reglement.id)
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.reglement.id
        assert "montant_facture" in response.data
        assert "total_reglements_facture" in response.data
        assert "reste_a_payer" in response.data

    def test_get_reglement_detail_financial_fields(self):
        """Test that detail shows correct financial fields."""
        url = self._detail_url(self.reglement.id)
        response = self.client_api.get(url)

        # Facture = 1200 TTC, reglement = 300
        assert Decimal(response.data["montant_facture"]) == Decimal("1200.00")
        assert Decimal(response.data["total_reglements_facture"]) == Decimal("300.00")
        assert Decimal(response.data["reste_a_payer"]) == Decimal("900.00")

    def test_get_reglement_detail_unauthorized(self):
        """Test that unauthorized user cannot access règlement."""
        other_user = get_user_model().objects.create_user(
            email="other@dev.com", password="pass"
        )
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)

        url = self._detail_url(self.reglement.id)
        response = other_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_reglement(self):
        """Test updating a règlement."""
        url = self._detail_url(self.reglement.id)
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Updated payment",
            "montant": "350.00",
            "date_reglement": "2025-01-16",
            "date_echeance": "2025-02-16",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["libelle"] == "Updated payment"
        assert Decimal(response.data["montant"]) == Decimal("350.00")

    def test_update_reglement_exceeds_reste(self):
        """Test that updating to exceed reste à payer fails."""
        url = self._detail_url(self.reglement.id)
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Too much",
            "montant": "1500.00",  # More than facture total
            "date_reglement": "2025-01-16",
            "date_echeance": "2025-02-16",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_reglement_same_amount_succeeds(self):
        """Test that updating with same amount succeeds (edge case for exclusion)."""
        url = self._detail_url(self.reglement.id)
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Same amount",
            "montant": "300.00",  # Same as current
            "date_reglement": "2025-01-16",
            "date_echeance": "2025-02-16",
        }
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_delete_reglement(self):
        """Test deleting a règlement."""
        url = self._detail_url(self.reglement.id)
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Reglement.objects.filter(id=self.reglement.id).exists()

    def test_switch_statut_to_annule(self):
        """Test switching status to Annulé."""
        url = self._status_url(self.reglement.id)
        response = self.client_api.patch(url, {"statut": "Annulé"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "Annulé"

    def test_switch_statut_to_valide(self):
        """Test switching status to Valide."""
        self.reglement.statut = "Annulé"
        self.reglement.save()

        url = self._status_url(self.reglement.id)
        response = self.client_api.patch(url, {"statut": "Valide"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["statut"] == "Valide"

    def test_switch_statut_invalid(self):
        """Test switching to invalid status fails."""
        url = self._status_url(self.reglement.id)
        response = self.client_api.patch(url, {"statut": "Invalid"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_switch_statut_valide_exceeds_reste(self):
        """Test that revalidating when exceeding reste fails."""
        # Create another facture with lower amount
        facture2 = FactureClient.objects.create(
            numero_facture="API/03",
            client=self.client_obj,
            date_facture="2025-01-03",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            created_by_user=self.user,
        )
        FactureClientLine.objects.create(
            facture_client=facture2,
            article=self.article,
            prix_achat=Decimal("10.00"),
            prix_vente=Decimal("100.00"),  # 100 HT * 1.2 = 120 TTC
            quantity=1,
        )
        facture2.recalc_totals()
        facture2.save()

        # Create reglement for full amount
        Reglement.objects.create(
            facture_client=facture2,
            mode_reglement=self.mode_reglement,
            libelle="Full payment",
            montant=facture2.total_ttc_apres_remise,
            statut="Valide",
        )

        # Create another reglement and annul it
        reg2 = Reglement.objects.create(
            facture_client=facture2,
            mode_reglement=self.mode_reglement,
            libelle="Extra",
            montant=Decimal("50.00"),
            statut="Annulé",
        )

        # Try to revalidate - should fail as facture is already fully paid
        url = self._status_url(reg2.id)
        response = self.client_api.patch(url, {"statut": "Valide"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_without_facture_fails(self):
        """Test that creating without facture_client fails."""
        url = self._list_create_url()
        payload = {
            "mode_reglement": self.mode_reglement.id,
            "libelle": "No facture",
            "montant": "100.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_reglements_forbidden_when_not_member(self):
        """Test listing règlements requires membership in company."""
        other_user = get_user_model().objects.create_user(
            email="other-list@dev.com", password="pass"
        )
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)

        url = self._list_create_url() + f"?company_id={self.company.id}"
        response = other_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_reglement_forbidden_without_membership(self):
        """Test create fails if user not member of facture's company."""
        outsider = get_user_model().objects.create_user(
            email="outsider@dev.com", password="pass"
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)

        url = self._list_create_url()
        payload = {
            "facture_client": self.facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "No access",
            "montant": "50.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = outsider_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_reglement_for_missing_facture(self):
        """Test creating for non-existent facture returns 404."""
        url = self._list_create_url()
        payload = {
            "facture_client": 999999,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Missing facture",
            "montant": "50.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_reglement_detail_not_found(self):
        """Test getting non-existent règlement returns 404."""
        url = self._detail_url(999999)
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_reglement_forbidden_without_membership(self):
        """Test delete is forbidden for non-members."""
        outsider = get_user_model().objects.create_user(
            email="outsider-del@dev.com", password="pass"
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)

        url = self._detail_url(self.reglement.id)
        response = outsider_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Reglement.objects.filter(id=self.reglement.id).exists()

    def test_status_update_forbidden_without_membership(self):
        """Test statut update is forbidden for non-members."""
        outsider = get_user_model().objects.create_user(
            email="outsider-status@dev.com", password="pass"
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)

        url = self._status_url(self.reglement.id)
        response = outsider_client.patch(url, {"statut": "Annulé"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# -----------------------------------------------------------------------------
# Filter Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementFilters:
    """Tests for ReglementFilter."""

    def setup_method(self):
        self.user = get_user_model().objects.create_user(
            email="filter@dev.com", password="p"
        )

        self.ville = Ville.objects.create(nom="FilterVille")
        self.company = Company.objects.create(raison_sociale="FilterCo", ICE="FILTCO")
        Membership.objects.create(user=self.user, company=self.company)

        self.client_a = Client.objects.create(
            code_client="FILT001",
            client_type="PM",
            raison_sociale="Alpha Client",
            company=self.company,
            ville=self.ville,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="FilterPay")
        self.mode_reglement = ModePaiement.objects.create(nom="FilterReg")
        self.mode_reglement2 = ModePaiement.objects.create(nom="FilterReg2")

        self.article = Article.objects.create(
            company=self.company,
            reference="FILT-ART",
            designation="Filter Article",
            prix_achat=100.00,
            prix_vente=200.00,
            tva=20,
        )

        self.facture1 = FactureClient.objects.create(
            numero_facture="FILT/01",
            client=self.client_a,
            date_facture="2025-01-01",
            mode_paiement=self.mode_paiement,
            statut="Accepté",
            created_by_user=self.user,
        )
        FactureClientLine.objects.create(
            facture_client=self.facture1,
            article=self.article,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("500.00"),
            quantity=2,
        )
        self.facture1.recalc_totals()
        self.facture1.save()

        self.reg1 = Reglement.objects.create(
            facture_client=self.facture1,
            mode_reglement=self.mode_reglement,
            libelle="Payment Alpha",
            montant=Decimal("200.00"),
            date_reglement="2025-01-15",
            date_echeance="2025-02-15",
            statut="Valide",
        )
        self.reg2 = Reglement.objects.create(
            facture_client=self.facture1,
            mode_reglement=self.mode_reglement2,
            libelle="Payment Beta",
            montant=Decimal("100.00"),
            date_reglement="2025-01-20",
            date_echeance="2025-03-20",
            statut="Annulé",
        )
        # Force a libelle containing tsquery metacharacters for fallback coverage
        self.reg1.libelle = "Payment Alpha&"
        self.reg1.save()

    def test_filter_by_statut(self):
        """Test filtering by statut."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"statut": "Valide"}, queryset=base_qs)
        assert filt.qs.count() == 1
        assert filt.qs.first().statut == "Valide"

    def test_filter_by_statut_case_insensitive(self):
        """Test filtering by statut is case-insensitive."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"statut": "valide"}, queryset=base_qs)
        assert filt.qs.count() == 1

    def test_filter_by_facture_client_id(self):
        """Test filtering by facture_client_id."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter(
            {"facture_client_id": self.facture1.id}, queryset=base_qs
        )
        assert filt.qs.count() == 2

    def test_filter_by_mode_reglement_id(self):
        """Test filtering by mode_reglement_id."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter(
            {"mode_reglement_id": self.mode_reglement.id}, queryset=base_qs
        )
        assert filt.qs.count() == 1

    def test_filter_by_date_reglement(self):
        """Test filtering by date_reglement."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"date_reglement": "2025-01-15"}, queryset=base_qs)
        assert filt.qs.count() == 1

    def test_filter_by_date_reglement_gte(self):
        """Test filtering by date_reglement_gte."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"date_reglement_gte": "2025-01-18"}, queryset=base_qs)
        assert filt.qs.count() == 1
        assert filt.qs.first().date_reglement.isoformat() == "2025-01-20"

    def test_filter_by_date_echeance_lte(self):
        """Test filtering by date_echeance_lte."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"date_echeance_lte": "2025-02-28"}, queryset=base_qs)
        assert filt.qs.count() == 1

    def test_global_search_by_libelle(self):
        """Test global search by libelle."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"search": "Alpha"}, queryset=base_qs)
        assert filt.qs.count() >= 1
        assert any("Alpha" in r.libelle for r in filt.qs)

    def test_global_search_by_facture_numero(self):
        """Test global search by facture numero."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"search": "FILT/01"}, queryset=base_qs)
        assert filt.qs.count() >= 1

    def test_global_search_by_client_name(self):
        """Test global search by client name."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"search": "Alpha Client"}, queryset=base_qs)
        assert filt.qs.count() >= 1

    def test_global_search_empty_returns_all(self):
        """Test that empty search returns all."""
        base_qs = Reglement.objects.all()
        count_before = base_qs.count()
        filt = ReglementFilter({"search": ""}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_filter_statut_empty_returns_all(self):
        """Test that empty statut returns all."""
        base_qs = Reglement.objects.all()
        count_before = base_qs.count()
        filt = ReglementFilter({"statut": ""}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_global_search_whitespace_returns_all(self):
        """Test whitespace search returns all results."""
        base_qs = Reglement.objects.all()
        count_before = base_qs.count()
        filt = ReglementFilter({"search": "   "}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_filter_statut_whitespace_returns_all(self):
        """Test whitespace statut returns all results."""
        base_qs = Reglement.objects.all()
        count_before = base_qs.count()
        filt = ReglementFilter({"statut": "   "}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_global_search_skips_fts_on_metachar(self):
        """Search containing tsquery metacharacters should skip FTS path."""
        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"search": "Alpha&"}, queryset=base_qs)
        ids = list(filt.qs.values_list("id", flat=True))
        assert self.reg1.id in ids

    def test_global_search_database_error_fallback(self, monkeypatch):
        """DatabaseError during FTS should fall back to icontains search."""
        from reglement import filters as reg_filters

        def _raise_db_error(*_args, **_kwargs):
            from django.db.utils import DatabaseError

            raise DatabaseError("forced for test")

        monkeypatch.setattr(reg_filters, "SearchQuery", _raise_db_error)

        base_qs = Reglement.objects.all()
        filt = ReglementFilter({"search": "Alpha"}, queryset=base_qs)
        ids = list(filt.qs.values_list("id", flat=True))
        assert self.reg1.id in ids


# -----------------------------------------------------------------------------
# Admin Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementAdmin:
    """Tests for ReglementAdmin."""

    def test_admin_client_name(self, reglement_obj):
        """Test admin client_name method."""
        from reglement.admin import ReglementAdmin
        from django.contrib.admin.sites import AdminSite

        admin = ReglementAdmin(Reglement, AdminSite())
        client_name = admin.client_name(reglement_obj)
        assert client_name == reglement_obj.facture_client.client.raison_sociale

    def test_admin_statut_badge(self, reglement_obj):
        """Test admin statut_badge method."""
        from reglement.admin import ReglementAdmin
        from django.contrib.admin.sites import AdminSite

        admin = ReglementAdmin(Reglement, AdminSite())
        badge = admin.statut_badge(reglement_obj)
        assert "Valide" in badge
        assert "#28a745" in badge  # Green color for Valide

    def test_admin_form_validates_montant_exceeds_reste(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test admin form prevents montant exceeding reste à payer."""
        from reglement.admin import ReglementAdminForm

        # Facture total is 600 TTC, try to create with 700
        form_data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Too much",
            "montant": Decimal("700.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert not form.is_valid()
        assert "montant" in form.errors

    def test_admin_form_allows_valid_montant(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test admin form allows valid montant."""
        from reglement.admin import ReglementAdminForm

        # Facture total is 600 TTC, create with 400
        form_data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Valid amount",
            "montant": Decimal("400.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert form.is_valid(), form.errors

    def test_admin_form_update_excludes_self(self, reglement_obj):
        """Test admin form excludes current instance when updating."""
        from reglement.admin import ReglementAdminForm

        # Update with same amount should work
        form_data = {
            "facture_client": reglement_obj.facture_client.id,
            "mode_reglement": reglement_obj.mode_reglement.id,
            "libelle": "Updated",
            "montant": reglement_obj.montant,
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data, instance=reglement_obj)
        assert form.is_valid(), form.errors

    def test_admin_form_validates_negative_montant(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test admin form prevents negative montant."""
        from reglement.admin import ReglementAdminForm

        form_data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Negative",
            "montant": Decimal("-100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert not form.is_valid()
        assert "montant" in form.errors

    def test_admin_form_validates_zero_montant(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test admin form prevents zero montant."""
        from reglement.admin import ReglementAdminForm

        form_data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Zero",
            "montant": Decimal("0.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert not form.is_valid()
        assert "montant" in form.errors

    def test_admin_form_allows_annule_exceeding_montant(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test admin form allows Annulé status with exceeding montant (doesn't count)."""
        from reglement.admin import ReglementAdminForm

        # Facture total is 600 TTC, but with Annulé status, 700 should be allowed
        form_data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Cancelled payment",
            "montant": Decimal("700.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Annulé",
        }
        form = ReglementAdminForm(data=form_data)
        assert form.is_valid(), form.errors


# -----------------------------------------------------------------------------
# Serializer Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementSerializers:
    """Tests for Reglement serializers."""

    def test_list_serializer_fields(self, reglement_obj):
        """Test ReglementListSerializer contains expected fields."""
        from reglement.serializers import ReglementListSerializer

        serializer = ReglementListSerializer(reglement_obj)
        data = serializer.data

        assert "id" in data
        assert "facture_client" in data
        assert "facture_client_numero" in data
        assert "client_name" in data
        assert "mode_reglement" in data
        assert "mode_reglement_name" in data
        assert "libelle" in data
        assert "montant" in data
        assert "date_reglement" in data
        assert "date_echeance" in data
        assert "statut" in data

    def test_detail_serializer_financial_fields(self, reglement_obj):
        """Test ReglementDetailSerializer contains financial fields."""
        from reglement.serializers import ReglementDetailSerializer

        serializer = ReglementDetailSerializer(reglement_obj)
        data = serializer.data

        assert "montant_facture" in data
        assert "total_reglements_facture" in data
        assert "reste_a_payer" in data

    def test_create_serializer_validation_positive_montant(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that create serializer validates positive montant."""
        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("-100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "montant" in serializer.errors

    def test_create_serializer_validation_exceeds_reste(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that create serializer validates montant against reste à payer."""
        from reglement.serializers import ReglementCreateSerializer

        # Facture total is 600 TTC
        data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("700.00"),  # More than 600 TTC
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "montant" in serializer.errors

    def test_update_serializer_excludes_self_from_validation(self, reglement_obj):
        """Test that update serializer excludes current reglement from reste calculation."""
        from reglement.serializers import ReglementUpdateSerializer

        # Update with same amount should work
        data = {
            "facture_client": reglement_obj.facture_client.id,
            "mode_reglement": reglement_obj.mode_reglement.id,
            "libelle": "Updated",
            "montant": reglement_obj.montant,
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementUpdateSerializer(instance=reglement_obj, data=data)
        assert serializer.is_valid(), serializer.errors


# -----------------------------------------------------------------------------
# Edge Case Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementEdgeCases:
    """Tests for edge cases in règlement handling."""

    def test_full_payment_then_no_more_allowed(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that after full payment, no more règlements are allowed."""
        # Facture total is 600 TTC
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Full payment",
            montant=reglement_facture_with_lines.total_ttc_apres_remise,
            statut="Valide",
        )

        # Try to add another payment
        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Extra",
            "montant": Decimal("1.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()

    def test_exact_remaining_amount_allowed(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that exact remaining amount is allowed."""
        # Add partial payment
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Partial",
            montant=Decimal("400.00"),
            statut="Valide",
        )

        # Remaining is 200 (600 - 400)
        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": reglement_facture_with_lines.id,
            "mode_reglement": reglement_mode_reglement.id,
            "libelle": "Final",
            "montant": Decimal("200.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_cancelled_reglement_frees_up_amount(
        self, reglement_facture_with_lines, reglement_mode_reglement
    ):
        """Test that cancelling a reglement frees up the amount."""
        # Full payment
        reg = Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Full payment",
            montant=reglement_facture_with_lines.total_ttc_apres_remise,
            statut="Valide",
        )

        # Cancel it
        reg.statut = "Annulé"
        reg.save()

        # Now full amount should be available again
        reste = Reglement.get_reste_a_payer(reglement_facture_with_lines)
        assert reste == reglement_facture_with_lines.total_ttc_apres_remise

    def test_multiple_partial_payments_tracking(
        self,
        reglement_facture_with_lines,
        reglement_mode_reglement,
        reglement_mode_reglement_cheque,
    ):
        """Test tracking multiple partial payments with different modes."""
        # Facture total is 600 TTC
        # Payment 1: 200 cash
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Cash payment",
            montant=Decimal("200.00"),
            statut="Valide",
        )

        # Payment 2: 150 cheque
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement_cheque,
            libelle="Cheque payment",
            montant=Decimal("150.00"),
            statut="Valide",
        )

        # Payment 3: 100 cash (canceled)
        Reglement.objects.create(
            facture_client=reglement_facture_with_lines,
            mode_reglement=reglement_mode_reglement,
            libelle="Cancelled",
            montant=Decimal("100.00"),
            statut="Annulé",
        )

        # Total valid = 350, remaining = 250
        total = Reglement.get_total_reglements_for_facture(
            reglement_facture_with_lines.id
        )
        assert total == Decimal("350.00")

        reste = Reglement.get_reste_a_payer(reglement_facture_with_lines)
        assert reste == Decimal("250.00")


# -----------------------------------------------------------------------------
# Facture Status Validation Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestReglementFactureStatusValidation:
    """Tests for facture status validation when creating/updating règlements."""

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="facture_status@dev.com",
            password="pass",
            first_name="Test",
            last_name="User",
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        self.ville = Ville.objects.create(nom="StatusVille")
        self.company = Company.objects.create(
            raison_sociale="Status Company", ICE="STATUS-1234"
        )
        Membership.objects.create(user=self.user, company=self.company)

        self.client_obj = Client.objects.create(
            code_client="STATUS001",
            client_type="PM",
            raison_sociale="Status Client",
            ville=self.ville,
            company=self.company,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="Status Payment")
        self.mode_reglement = ModePaiement.objects.create(nom="Status Règlement")

        self.article = Article.objects.create(
            company=self.company,
            reference="STATUS-ART",
            designation="Status Article",
            prix_achat=100.00,
            prix_vente=500.00,
            tva=20,
        )

    def _create_facture_with_status(self, statut, numero):
        """Helper to create a facture with given status."""
        facture = FactureClient.objects.create(
            numero_facture=numero,
            client=self.client_obj,
            date_facture="2025-01-01",
            mode_paiement=self.mode_paiement,
            statut=statut,
            created_by_user=self.user,
        )
        FactureClientLine.objects.create(
            facture_client=facture,
            article=self.article,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("500.00"),
            quantity=1,
        )
        facture.recalc_totals()
        facture.save()
        return facture

    def test_create_reglement_for_brouillon_fails(self):
        """Test that creating règlement for Brouillon facture fails."""
        facture = self._create_facture_with_status("Brouillon", "BROUILLON/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "facture_client" in serializer.errors

    def test_create_reglement_for_refuse_fails(self):
        """Test that creating règlement for Refusé facture fails."""
        facture = self._create_facture_with_status("Refusé", "REFUSE/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "facture_client" in serializer.errors

    def test_create_reglement_for_annule_fails(self):
        """Test that creating règlement for Annulé facture fails."""
        facture = self._create_facture_with_status("Annulé", "ANNULE/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "facture_client" in serializer.errors

    def test_create_reglement_for_expire_fails(self):
        """Test that creating règlement for Expiré facture fails."""
        facture = self._create_facture_with_status("Expiré", "EXPIRE/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "facture_client" in serializer.errors

    def test_create_reglement_for_envoye_succeeds(self):
        """Test that creating règlement for Envoyé facture succeeds."""
        facture = self._create_facture_with_status("Envoyé", "ENVOYE/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_create_reglement_for_accepte_succeeds(self):
        """Test that creating règlement for Accepté facture succeeds."""
        facture = self._create_facture_with_status("Accepté", "ACCEPTE/01")

        from reglement.serializers import ReglementCreateSerializer

        data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        serializer = ReglementCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_api_create_reglement_for_brouillon_fails(self):
        """Test API endpoint rejects règlement for Brouillon facture."""
        facture = self._create_facture_with_status("Brouillon", "API-BROUILLON/01")

        url = reverse("reglement:reglement-list-create")
        payload = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": "100.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_api_create_reglement_for_accepte_succeeds(self):
        """Test API endpoint accepts règlement for Accepté facture."""
        facture = self._create_facture_with_status("Accepté", "API-ACCEPTE/01")

        url = reverse("reglement:reglement-list-create")
        payload = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": "100.00",
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
        }
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_admin_form_rejects_brouillon_facture(self):
        """Test admin form rejects règlement for Brouillon facture."""
        from reglement.admin import ReglementAdminForm

        facture = self._create_facture_with_status("Brouillon", "ADMIN-BROUILLON/01")

        form_data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert not form.is_valid()
        assert "facture_client" in form.errors

    def test_admin_form_accepts_accepte_facture(self):
        """Test admin form accepts règlement for Accepté facture."""
        from reglement.admin import ReglementAdminForm

        facture = self._create_facture_with_status("Accepté", "ADMIN-ACCEPTE/01")

        form_data = {
            "facture_client": facture.id,
            "mode_reglement": self.mode_reglement.id,
            "libelle": "Test",
            "montant": Decimal("100.00"),
            "date_reglement": "2025-01-20",
            "date_echeance": "2025-02-20",
            "statut": "Valide",
        }
        form = ReglementAdminForm(data=form_data)
        assert form.is_valid(), form.errors

    def test_switch_status_to_valide_for_annule_facture_fails(self):
        """Test that revalidating règlement for Annulé facture fails."""
        facture = self._create_facture_with_status("Accepté", "SWITCH/01")

        # Create and cancel a reglement
        reglement = Reglement.objects.create(
            facture_client=facture,
            mode_reglement=self.mode_reglement,
            libelle="Test",
            montant=Decimal("100.00"),
            statut="Annulé",
        )

        # Change facture status to Annulé
        facture.statut = "Annulé"
        facture.save()

        # Try to revalidate
        url = reverse("reglement:reglement-statut-update", args=[reglement.id])
        response = self.client_api.patch(url, {"statut": "Valide"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestReglementPDFGeneration:
    """Test PDF generation for reglements."""

    def test_generate_reglement_pdf(
        self,
        reglement_user,
        reglement_company,
        reglement_facture,
        reglement_mode_reglement,
    ):
        """Test generating PDF for a règlement."""
        Membership.objects.create(user=reglement_user, company=reglement_company)

        reglement = Reglement.objects.create(
            facture_client=reglement_facture,
            mode_reglement=reglement_mode_reglement,
            libelle="Test Payment",
            montant=Decimal("500.00"),
            date_reglement="2026-01-05",
            date_echeance="2026-01-05",
            statut="Valide",
        )

        client_api = APIClient()
        client_api.force_authenticate(user=reglement_user)

        url = (
            reverse("reglement:reglement-pdf", args=[reglement.id])
            + f"?company_id={reglement_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "filename" in response["Content-Disposition"]

    def test_pdf_no_company_id(
        self,
        reglement_user,
        reglement_company,
        reglement_facture,
        reglement_mode_reglement,
    ):
        """Test PDF fails without company_id."""
        Membership.objects.create(user=reglement_user, company=reglement_company)

        reglement = Reglement.objects.create(
            facture_client=reglement_facture,
            mode_reglement=reglement_mode_reglement,
            libelle="Test Payment",
            montant=Decimal("500.00"),
        )

        client_api = APIClient()
        client_api.force_authenticate(user=reglement_user)

        url = reverse("reglement:reglement-pdf", args=[reglement.id])
        response = client_api.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pdf_not_found(self, reglement_user, reglement_company):
        """Test PDF fails for non-existent règlement."""
        Membership.objects.create(user=reglement_user, company=reglement_company)

        client_api = APIClient()
        client_api.force_authenticate(user=reglement_user)

        url = (
            reverse("reglement:reglement-pdf", args=[99999])
            + f"?company_id={reglement_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
