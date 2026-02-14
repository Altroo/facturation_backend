from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from core.tests import (
    DocConfig,
    SharedDocumentAPITestsMixin,
    SharedDocumentFilterTestsMixin,
    SharedDocumentModelTestsMixin,
    SharedDocumentAdminTestsMixin,
)
from parameter.models import ModePaiement, Ville
from .filters import FactureClientFilter
from .models import FactureClient, FactureClientLine

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


@pytest.fixture
def fc_conv_user():
    return CustomUser.objects.create_user(
        email="fc_conv@example.com",
        password="pass",
        first_name="FC",
        last_name="Conv",
    )


@pytest.fixture
def fc_conv_company():
    return Company.objects.create(raison_sociale="FC Conv Co", ICE="FCCONV")


def _create_fc_membership(user, company):
    caissier_role, _ = Role.objects.get_or_create(
        name="Caissier",
    )
    return Membership.objects.create(user=user, company=company, role=caissier_role)


@pytest.fixture
def fc_conv_ville(fc_conv_company):
    return Ville.objects.create(nom="FCConvVille", company=fc_conv_company)


@pytest.fixture
def fc_conv_client(fc_conv_ville, fc_conv_company):
    return Client.objects.create(
        code_client="FCCONV001",
        client_type="PM",
        raison_sociale="FC Conv Client",
        ville=fc_conv_ville,
        company=fc_conv_company,
    )


@pytest.fixture
def fc_conv_mode_paiement(fc_conv_company):
    return ModePaiement.objects.create(nom="FCConvPay", company=fc_conv_company)


@pytest.fixture
def fc_conv_article(fc_conv_company):
    return Article.objects.create(
        company=fc_conv_company,
        reference="FCCONV001",
        designation="FC Conv Article",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )


@pytest.fixture
def fc_conv_obj(fc_conv_client, fc_conv_mode_paiement, fc_conv_user):
    return FactureClient.objects.create(
        numero_facture="FCCONV/01",
        client=fc_conv_client,
        date_facture="2025-01-01",
        mode_paiement=fc_conv_mode_paiement,
        statut="Envoyé",
        created_by_user=fc_conv_user,
        remise=Decimal("5.00"),
        remise_type="Pourcentage",
    )


@pytest.fixture
def fc_conv_with_lines(fc_conv_obj, fc_conv_article):
    FactureClientLine.objects.create(
        facture_client=fc_conv_obj,
        article=fc_conv_article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=2,
    )
    fc_conv_obj.recalc_totals()
    fc_conv_obj.save()
    return fc_conv_obj


# -----------------------------------------------------------------------------
# Test Classes
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestFactureClientAPI(SharedDocumentAPITestsMixin):
    cfg = DocConfig(
        list_create_url_name="facture_client:facture-client-list-create",
        detail_url_name="facture_client:facture-client-detail",
        status_update_url_name="facture_client:facture-client-statut-update",
        generate_numero_url_name="facture_client:generate-numero-facture-client",
        numero_field="numero_facture",
        date_field="date_facture",
        req_field="numero_bon_commande_client",
        fk_mode_paiement_field="mode_paiement",
        line_parent_fk_attr="facture_client",
    )

    Model = FactureClient
    LineModel = FactureClientLine

    def setup_method(self):
        # Use common base setup
        self.base_setup_method()

        # Create facture_client-specific document and line
        self.doc = FactureClient.objects.create(
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

        self.doc_line = FactureClientLine.objects.create(
            facture_client=self.doc,
            article=self.article,
            prix_achat=100.00,
            prix_vente=120.00,
            quantity=2,
            remise=5.00,
            remise_type="Pourcentage",
        )

    def test_list_facture_client_requires_client_id(self):
        self.shared_test_list_requires_company_id()

    def test_list_facture_client(self):
        self.shared_test_list()

    def test_list_facture_client_with_pagination(self):
        self.shared_test_list_with_pagination()

    def test_create_facture_client_basic(self):
        self.shared_test_create_basic()

    def test_create_facture_client_with_lignes(self):
        self.shared_test_create_with_lignes()

    def test_get_facture_client_detail(self):
        self.shared_test_get_detail()

    def test_create_facture_client_without_client_fails(self):
        self.shared_test_create_without_client_fails()

    def test_create_facture_client_invalid_numero_format(self):
        self.shared_test_create_invalid_numero_format()

    def test_get_facture_client_detail_unauthorized(self):
        self.shared_test_get_detail_unauthorized()

    def test_update_facture_client_basic(self):
        self.shared_test_update_basic()

    def test_update_facture_client_with_lignes_upsert(self):
        self.shared_test_update_with_lignes_upsert()

    def test_update_facture_client_delete_missing_lines(self):
        self.shared_test_update_delete_missing_lines()

    def test_delete_facture_client(self):
        self.shared_test_delete()

    def test_filter_facture_client_by_statut(self):
        self.shared_test_filter_by_statut()

    def test_search_facture_client_by_numero(self):
        self.shared_test_search_by_numero()

    def test_generate_numero_facture(self):
        self.shared_test_generate_numero()

    def test_update_facture_client_status(self):
        self.shared_test_update_status()

    def test_update_facture_client_status_invalid(self):
        self.shared_test_update_status_invalid()

    def test_smoke_totals_present_on_detail(self):
        self.shared_test_get_detail()

    def test_smoke_totals_present_on_list(self):
        self.shared_test_list()

    def test_smoke_upsert_lines(self):
        self.shared_test_update_with_lignes_upsert()

    def test_smoke_generate_numero(self):
        self.shared_test_generate_numero()


@pytest.mark.django_db
class TestFactureClientFilters(SharedDocumentFilterTestsMixin):
    FilterClass = FactureClientFilter

    def setup_method(self):
        # Use common base setup for filters
        self.base_filter_setup_method()

        # Create facture_client-specific documents
        self.doc1 = FactureClient.objects.create(
            numero_facture="NUM-001",
            client=self.client_a,
            date_facture="2024-06-01",
            numero_bon_commande_client="REQ-ALPHA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.doc2 = FactureClient.objects.create(
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
        self.shared_test_global_search_matches_numero_and_client_and_req(
            numero_field="numero_facture",
            client_label="client alpha",
            req_value="REQ-BETA",
        )

    def test_filter_statut_case_insensitive_and_trim(self):
        self.shared_test_filter_statut_case_insensitive_and_trim()

    def test_client_id_filter(self):
        self.shared_test_client_id_filter()

    def test_empty_search_returns_queryset_unchanged(self):
        self.shared_test_empty_search_returns_queryset_unchanged()

    def test_filter_statut_empty_returns_all(self):
        self.shared_test_filter_statut_empty_returns_all()

    def test_filter_statut_none_returns_all(self):
        self.shared_test_filter_statut_none_returns_all()

    def test_search_with_tsquery_metacharacters(self):
        self.shared_test_search_with_tsquery_metacharacters()

    def test_search_with_special_chars_fallback(self):
        self.shared_test_search_with_special_chars_fallback()

    def test_search_with_pipe_metachar(self):
        self.shared_test_search_with_pipe_metachar()

    def test_search_with_parentheses_metachar(self):
        self.shared_test_search_with_parentheses_metachar()

    def test_search_with_empty_string(self):
        """Test search with empty string returns queryset unchanged (line 27 coverage)."""
        base_qs = FactureClient.objects.all()
        filt = FactureClientFilter({"search": ""}, queryset=base_qs)
        assert filt.qs.count() == base_qs.count()

    def test_filter_statut_with_empty_string(self):
        """Test filter_statut with empty string returns all (line 21 coverage)."""
        base_qs = FactureClient.objects.all()
        count_before = base_qs.count()
        filt = FactureClientFilter({"statut": ""}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_filter_statut_direct_call_empty(self):
        """Test filter_statut method directly with empty value (line 21 coverage)."""
        base_qs = FactureClient.objects.all()
        result = FactureClientFilter.filter_statut(base_qs, "statut", "")
        assert result.count() == base_qs.count()

    def test_filter_statut_direct_call_none(self):
        """Test filter_statut method directly with None value (line 21 coverage)."""
        base_qs = FactureClient.objects.all()
        result = FactureClientFilter.filter_statut(base_qs, "statut", None)
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_empty(self):
        """Test global_search method directly with empty value (line 27 coverage)."""
        base_qs = FactureClient.objects.all()
        filter_instance = FactureClientFilter()
        result = filter_instance.global_search(base_qs, "search", "")
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_whitespace(self):
        """Test global_search method directly with whitespace (line 27 coverage)."""
        base_qs = FactureClient.objects.all()
        filter_instance = FactureClientFilter()
        result = filter_instance.global_search(base_qs, "search", "   ")
        assert result.count() == base_qs.count()


@pytest.mark.django_db
class TestFactureClientUtilsExtra:
    """Extra tests for facture_client utils."""

    def test_get_next_numero_with_gaps(self):
        """Test get_next_numero_facture_client finds gaps."""
        from facture_client.utils import get_next_numero_facture_client
        from datetime import datetime

        # Create fixtures
        company = Company.objects.create(raison_sociale="UtilCo", ICE="UTIL123")
        ville = Ville.objects.create(nom="UtilVille", company=company)
        client = Client.objects.create(
            code_client="UTIL001",
            client_type="PM",
            raison_sociale="Util Client",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_fc@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCash", company=company)

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create with gap (0001, 0003)
        FactureClient.objects.create(
            numero_facture=f"0001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureClient.objects.create(
            numero_facture=f"0003/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_client(company.id)
        assert next_num == f"0002/{year_suffix}"

    def test_get_next_numero_with_invalid_format(self):
        """Test get_next_numero_facture_client handles invalid formats."""
        from facture_client.utils import get_next_numero_facture_client
        from datetime import datetime

        company = Company.objects.create(raison_sociale="UtilCo2", ICE="UTIL456")
        ville = Ville.objects.create(nom="UtilVille2", company=company)
        client = Client.objects.create(
            code_client="UTIL002",
            client_type="PM",
            raison_sociale="Util Client2",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_fc2@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCash2", company=company)

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create with invalid format
        FactureClient.objects.create(
            numero_facture=f"INVALID/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_client(company.id)
        assert "0001" in next_num or "0002" in next_num

    def test_get_next_numero_empty_db(self):
        """Test get_next_numero_facture_client with no existing records."""
        from facture_client.utils import get_next_numero_facture_client
        from datetime import datetime

        # Clear all facture_client
        FactureClient.objects.all().delete()
        
        company = Company.objects.create(raison_sociale="Empty Test Co", ICE="EMPTY123")

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_facture_client(company.id)
        assert next_num == f"0001/{year_suffix}"

    def test_get_next_numero_consecutive(self):
        """Test get_next_numero_facture_client with consecutive numbers."""
        from facture_client.utils import get_next_numero_facture_client
        from datetime import datetime

        company = Company.objects.create(raison_sociale="UtilCo3", ICE="UTIL789")
        ville = Ville.objects.create(nom="UtilVille3", company=company)
        client = Client.objects.create(
            code_client="UTIL003",
            client_type="PM",
            raison_sociale="Util Client3",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_fc3@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCash3", company=company)

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create consecutive factures
        FactureClient.objects.create(
            numero_facture=f"0001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureClient.objects.create(
            numero_facture=f"0002/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_client(company.id)
        assert next_num == f"0003/{year_suffix}"


@pytest.mark.django_db
class TestFactureClientModelExtra(SharedDocumentModelTestsMixin):
    """Extra tests for FactureClient model methods."""

    numero_field = "numero_facture"

    def test_recalc_totals(self, fc_conv_with_lines):
        self.shared_test_recalc_totals(fc_conv_with_lines)

    def test_lignes_count(self, fc_conv_with_lines):
        self.shared_test_lignes_count(fc_conv_with_lines)

    def test_str_representation(self, fc_conv_obj):
        self.shared_test_str_representation(fc_conv_obj)


@pytest.mark.django_db
class TestFactureClientAdminExtra(SharedDocumentAdminTestsMixin):
    """Extra tests for FactureClient admin."""

    from facture_client.admin import FactureClientAdmin, FactureClientLineAdmin

    AdminClass = FactureClientAdmin
    LineAdminClass = FactureClientLineAdmin
    Model = FactureClient
    LineModel = FactureClientLine
    numero_field = "numero_facture"
    date_field = "date_facture"
    line_numero_method = "numero_facture"

    def test_admin_get_numero_field_name(self):
        self.shared_test_admin_get_numero_field_name()

    def test_admin_get_date_field_name(self):
        self.shared_test_admin_get_date_field_name()

    def test_line_admin_numero_facture(self, fc_conv_with_lines):
        self.shared_test_line_admin_numero(fc_conv_with_lines)

    def test_line_admin_article_reference(self, fc_conv_with_lines):
        self.shared_test_line_admin_article_reference(fc_conv_with_lines)

    def test_line_admin_article_designation(self, fc_conv_with_lines):
        self.shared_test_line_admin_article_designation(fc_conv_with_lines)


@pytest.mark.django_db
class TestFactureClientLineModelExtra:
    """Extra tests for FactureClientLine model."""

    def test_line_str_representation(self, fc_conv_with_lines):
        """Test FactureClientLine string representation."""
        line = fc_conv_with_lines.lignes.first()
        expected = f"{fc_conv_with_lines} - {line.article}"
        assert str(line) == expected


@pytest.mark.django_db
class TestFactureClientConversionExtra:
    """Extra tests for FactureClient conversion to BonDeLivraison."""

    def test_convert_to_bon_de_livraison(self, fc_conv_with_lines, fc_conv_user):
        """Test converting FactureClient to BonDeLivraison."""
        from bon_de_livraison.models import BonDeLivraison

        bon_livraison = fc_conv_with_lines.convert_to_bon_de_livraison(
            "BL-001", fc_conv_user
        )

        assert bon_livraison is not None
        assert isinstance(bon_livraison, BonDeLivraison)
        assert bon_livraison.client == fc_conv_with_lines.client
        assert bon_livraison.mode_paiement == fc_conv_with_lines.mode_paiement
        assert bon_livraison.created_by_user == fc_conv_user
        assert bon_livraison.lignes.count() == fc_conv_with_lines.lignes.count()
        assert bon_livraison.numero_bon_livraison == "BL-001"
        assert bon_livraison.date_bon_livraison == fc_conv_with_lines.date_facture
        assert (
            bon_livraison.numero_bon_commande_client
            == fc_conv_with_lines.numero_bon_commande_client
        )

    def test_conversion_copies_remise(self, fc_conv_with_lines, fc_conv_user):
        """Test that conversion copies remise fields."""
        bon_livraison = fc_conv_with_lines.convert_to_bon_de_livraison(
            "BL-002", fc_conv_user
        )

        assert bon_livraison.remise == fc_conv_with_lines.remise
        assert bon_livraison.remise_type == fc_conv_with_lines.remise_type

    def test_conversion_copies_line_details(self, fc_conv_with_lines, fc_conv_user):
        """Test that conversion copies line details correctly."""
        bon_livraison = fc_conv_with_lines.convert_to_bon_de_livraison(
            "BL-003", fc_conv_user
        )

        original_line = fc_conv_with_lines.lignes.first()
        new_line = bon_livraison.lignes.first()

        assert new_line.article == original_line.article
        assert new_line.quantity == original_line.quantity
        assert new_line.prix_vente == original_line.prix_vente
        assert new_line.prix_achat == original_line.prix_achat

    def test_conversion_copies_totals(self, fc_conv_with_lines, fc_conv_user):
        """Test that conversion copies all totals correctly."""
        bon_livraison = fc_conv_with_lines.convert_to_bon_de_livraison(
            "BL-004", fc_conv_user
        )

        assert bon_livraison.total_ht == fc_conv_with_lines.total_ht
        assert bon_livraison.total_tva == fc_conv_with_lines.total_tva
        assert bon_livraison.total_ttc == fc_conv_with_lines.total_ttc
        assert (
            bon_livraison.total_ttc_apres_remise
            == fc_conv_with_lines.total_ttc_apres_remise
        )

    def test_conversion_sets_brouillon_status(self, fc_conv_with_lines, fc_conv_user):
        """Test that converted BonDeLivraison has Brouillon status."""
        bon_livraison = fc_conv_with_lines.convert_to_bon_de_livraison(
            "BL-005", fc_conv_user
        )

        assert bon_livraison.statut == "Brouillon"


@pytest.mark.django_db
class TestFactureClientPDFGeneration:
    """Test PDF generation for facture client."""

    def test_generate_pdf(self, fc_conv_user, fc_conv_company, fc_conv_with_lines):
        """Test generating PDF for facture client."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse(
                "facture_client:facture-client-pdf-fr", args=[fc_conv_with_lines.id]
            )
            + f"?company_id={fc_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "filename" in response["Content-Disposition"]

    def test_pdf_no_company_id(self, fc_conv_user, fc_conv_company, fc_conv_with_lines):
        """Test PDF fails without company_id."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = reverse(
            "facture_client:facture-client-pdf-fr", args=[fc_conv_with_lines.id]
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pdf_not_found(self, fc_conv_user, fc_conv_company):
        """Test PDF fails for non-existent facture client."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse("facture_client:facture-client-pdf-fr", args=[99999])
            + f"?company_id={fc_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_pdf_sans_remise_type(
        self, fc_conv_user, fc_conv_company, fc_conv_with_lines
    ):
        """Test PDF generation with sans_remise type."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse(
                "facture_client:facture-client-pdf-fr", args=[fc_conv_with_lines.id]
            )
            + f"?company_id={fc_conv_company.id}&type=sans_remise"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"

    def test_pdf_avec_unite_type(
        self, fc_conv_user, fc_conv_company, fc_conv_with_lines
    ):
        """Test PDF generation with avec_unite type."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse(
                "facture_client:facture-client-pdf-fr", args=[fc_conv_with_lines.id]
            )
            + f"?company_id={fc_conv_company.id}&type=avec_unite"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
class TestFactureClientUnpaidListView:
    """Test unpaid facture client list view."""

    def test_unpaid_list_requires_company_id(self, fc_conv_user, fc_conv_company):
        """Test that unpaid list requires company_id parameter."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = reverse("facture_client:facture-client-unpaid-list")
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unpaid_list_success(self, fc_conv_user, fc_conv_company, fc_conv_client):
        """Test successful retrieval of unpaid factures."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        # Create factures
        FactureClient.objects.create(
            numero_facture="FC/001",
            client=fc_conv_client,
            date_facture="2025-01-01",
            statut="Validé",
            created_by_user=fc_conv_user,
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse("facture_client:facture-client-unpaid-list")
            + f"?company_id={fc_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "chiffre_affaire_total" in response.data
        assert "total_reglements" in response.data
        assert "total_impayes" in response.data

    def test_unpaid_list_with_pagination(
        self, fc_conv_user, fc_conv_company, fc_conv_client
    ):
        """Test unpaid list with pagination."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        # Create multiple unpaid factures
        for i in range(5):
            FactureClient.objects.create(
                numero_facture=f"FC/00{i}",
                client=fc_conv_client,
                date_facture=f"2025-01-{i+1:02d}",
                statut="Validé",
                created_by_user=fc_conv_user,
                total_ttc_apres_remise=Decimal("1000.00"),
            )

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse("facture_client:facture-client-unpaid-list")
            + f"?company_id={fc_conv_company.id}&pagination=true"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "chiffre_affaire_total" in response.data

    def test_unpaid_list_post_disabled(self, fc_conv_user, fc_conv_company):
        """Test that POST is disabled for unpaid list."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse("facture_client:facture-client-unpaid-list")
            + f"?company_id={fc_conv_company.id}"
        )
        response = client_api.post(url, {})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestFactureClientForPaymentView:
    """Test facture client for payment view."""

    def test_for_payment_view_requires_company_id(self, fc_conv_user):
        """Test that for payment view requires company_id parameter."""
        from django.urls import reverse
        from rest_framework import status

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = reverse("facture_client:facture-client-for-payment")
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_for_payment_view_success(
        self, fc_conv_user, fc_conv_company, fc_conv_client
    ):
        """Test successful retrieval of factures for payment."""
        from django.urls import reverse
        from rest_framework import status

        _create_fc_membership(fc_conv_user, fc_conv_company)

        # Create facture with Accepté status
        FactureClient.objects.create(
            numero_facture="FC/001",
            client=fc_conv_client,
            date_facture="2025-01-01",
            statut="Accepté",
            created_by_user=fc_conv_user,
            total_ttc_apres_remise=Decimal("1000.00"),
        )

        client_api = APIClient()
        client_api.force_authenticate(user=fc_conv_user)

        url = (
            reverse("facture_client:facture-client-for-payment")
            + f"?company_id={fc_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)