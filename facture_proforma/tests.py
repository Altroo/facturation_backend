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
from .filters import FactureProFormaFilter
from .models import FactureProForma, FactureProFormaLine

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


def _create_pf_membership(user, company):
    """Helper to create membership with Caissier role."""
    caissier_role, _ = Role.objects.get_or_create(name="Caissier")
    return Membership.objects.create(user=user, company=company, role=caissier_role)


@pytest.fixture
def pf_conv_user():
    return CustomUser.objects.create_user(
        email="pf_conv@example.com",
        password="pass",
        first_name="PF",
        last_name="Conv",
    )


@pytest.fixture
def pf_conv_company():
    return Company.objects.create(raison_sociale="PF Conv Co", ICE="PFCONV")


@pytest.fixture
def pf_conv_ville():
    return Ville.objects.create(nom="PFConvVille")


@pytest.fixture
def pf_conv_client(pf_conv_ville, pf_conv_company):
    return Client.objects.create(
        code_client="PFCONV001",
        client_type="PM",
        raison_sociale="PF Conv Client",
        ville=pf_conv_ville,
        company=pf_conv_company,
    )


@pytest.fixture
def pf_conv_mode_paiement():
    return ModePaiement.objects.create(nom="PFConvPay")


@pytest.fixture
def pf_conv_article(pf_conv_company):
    return Article.objects.create(
        company=pf_conv_company,
        reference="PFCONV001",
        designation="PF Conv Article",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )


@pytest.fixture
def pf_conv_obj(pf_conv_client, pf_conv_mode_paiement, pf_conv_user):
    return FactureProForma.objects.create(
        numero_facture="PFCONV/01",
        client=pf_conv_client,
        date_facture="2025-01-01",
        mode_paiement=pf_conv_mode_paiement,
        statut="Envoyé",
        created_by_user=pf_conv_user,
        remise=Decimal("5.00"),
        remise_type="Pourcentage",
    )


@pytest.fixture
def pf_conv_with_lines(pf_conv_obj, pf_conv_article):
    FactureProFormaLine.objects.create(
        facture_pro_forma=pf_conv_obj,
        article=pf_conv_article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=2,
    )
    pf_conv_obj.recalc_totals()
    pf_conv_obj.save()
    return pf_conv_obj


# -----------------------------------------------------------------------------
# Test Classes
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestFactureProFormaAPI(SharedDocumentAPITestsMixin):
    cfg = DocConfig(
        list_create_url_name="facture_proforma:facture-proforma-list-create",
        detail_url_name="facture_proforma:facture-proforma-detail",
        status_update_url_name="facture_proforma:facture-proforma-statut-update",
        generate_numero_url_name="facture_proforma:generate-numero-facture-proforma",
        numero_field="numero_facture",
        date_field="date_facture",
        req_field="numero_bon_commande_client",
        fk_mode_paiement_field="mode_paiement",
        line_parent_fk_attr="facture_pro_forma",
        convert_to_facture_client_url_name="facture_proforma:convert-to-facture-client",
        convert_to_facture_client_method="convert_to_facture_client",
    )

    Model = FactureProForma
    LineModel = FactureProFormaLine

    def setup_method(self):
        # Use common base setup
        self.base_setup_method()

        # Create facture_proforma-specific document and line
        self.doc = FactureProForma.objects.create(
            numero_facture="0002/25",
            client=self.client_obj,
            date_facture="2024-06-01",
            numero_bon_commande_client="REQ-001",
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
            statut="Envoyé",
        )

        self.doc_line = FactureProFormaLine.objects.create(
            facture_pro_forma=self.doc,
            article=self.article,
            prix_achat=100.00,
            prix_vente=120.00,
            quantity=2,
            remise=5.00,
            remise_type="Pourcentage",
        )

    def test_list_proforma_requires_client_id(self):
        self.shared_test_list_requires_company_id()

    def test_list_proforma(self):
        self.shared_test_list()

    def test_list_proforma_with_pagination(self):
        self.shared_test_list_with_pagination()

    def test_create_proforma_basic(self):
        self.shared_test_create_basic()

    def test_create_proforma_with_lignes(self):
        self.shared_test_create_with_lignes()

    def test_get_proforma_detail(self):
        self.shared_test_get_detail()

    def test_create_proforma_without_client_fails(self):
        self.shared_test_create_without_client_fails()

    def test_create_proforma_invalid_numero_format(self):
        self.shared_test_create_invalid_numero_format()

    def test_get_proforma_detail_unauthorized(self):
        self.shared_test_get_detail_unauthorized()

    def test_update_proforma_basic(self):
        self.shared_test_update_basic()

    def test_update_proforma_with_lignes_upsert(self):
        self.shared_test_update_with_lignes_upsert()

    def test_update_proforma_delete_missing_lines(self):
        self.shared_test_update_delete_missing_lines()

    def test_delete_proforma(self):
        self.shared_test_delete()

    def test_filter_proforma_by_statut(self):
        self.shared_test_filter_by_statut()

    def test_search_proforma_by_numero(self):
        self.shared_test_search_by_numero()

    def test_generate_numero_facture(self):
        self.shared_test_generate_numero()

    def test_update_proforma_status(self):
        self.shared_test_update_status()

    def test_update_proforma_status_invalid(self):
        self.shared_test_update_status_invalid()

    def test_convert_to_facture_client(self, monkeypatch):
        self.shared_test_convert_to_facture_client(monkeypatch)

    def test_smoke_totals_present_on_detail(self):
        self.shared_test_get_detail()

    def test_smoke_totals_present_on_list(self):
        self.shared_test_list()

    def test_smoke_upsert_lines(self):
        self.shared_test_update_with_lignes_upsert()


@pytest.mark.django_db
class TestFactureProFormaFilters(SharedDocumentFilterTestsMixin):
    FilterClass = FactureProFormaFilter

    def setup_method(self):
        # Use common base setup for filters
        self.base_filter_setup_method()

        # Create facture_proforma-specific documents
        self.doc1 = FactureProForma.objects.create(
            numero_facture="NUM-001",
            client=self.client_a,
            date_facture="2024-06-01",
            numero_bon_commande_client="REQ-ALPHA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.doc2 = FactureProForma.objects.create(
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
        base_qs = FactureProForma.objects.all()
        filt = FactureProFormaFilter({"search": ""}, queryset=base_qs)
        assert filt.qs.count() == base_qs.count()

    def test_filter_statut_with_empty_string(self):
        """Test filter_statut with empty string returns all (line 21 coverage)."""
        base_qs = FactureProForma.objects.all()
        count_before = base_qs.count()
        filt = FactureProFormaFilter({"statut": ""}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_filter_statut_direct_call_empty(self):
        """Test filter_statut method directly with empty value (line 21 coverage)."""
        base_qs = FactureProForma.objects.all()
        result = FactureProFormaFilter.filter_statut(base_qs, "statut", "")
        assert result.count() == base_qs.count()

    def test_filter_statut_direct_call_none(self):
        """Test filter_statut method directly with None value (line 21 coverage)."""
        base_qs = FactureProForma.objects.all()
        result = FactureProFormaFilter.filter_statut(base_qs, "statut", None)
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_empty(self):
        """Test global_search method directly with empty value (line 27 coverage)."""
        base_qs = FactureProForma.objects.all()
        filter_instance = FactureProFormaFilter()
        result = filter_instance.global_search(base_qs, "search", "")
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_whitespace(self):
        """Test global_search method directly with whitespace (line 27 coverage)."""
        base_qs = FactureProForma.objects.all()
        filter_instance = FactureProFormaFilter()
        result = filter_instance.global_search(base_qs, "search", "   ")
        assert result.count() == base_qs.count()


@pytest.mark.django_db
class TestFactureProFormaUtilsExtra:
    """Extra tests for facture_proforma utils."""

    def test_get_next_numero_with_gaps(self):
        """Test get_next_numero_facture_pro_forma finds gaps."""
        from facture_proforma.utils import get_next_numero_facture_pro_forma
        from datetime import datetime

        # Create fixtures
        company = Company.objects.create(raison_sociale="UtilCoPF", ICE="UTILPF123")
        ville = Ville.objects.create(nom="UtilVillePF")
        client = Client.objects.create(
            code_client="UTILPF001",
            client_type="PM",
            raison_sociale="Util Client PF",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_pf@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCashPF")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create with gap (0001, 0003)
        FactureProForma.objects.create(
            numero_facture=f"0001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureProForma.objects.create(
            numero_facture=f"0003/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"0002/{year_suffix}"

    def test_get_next_numero_with_invalid_format(self):
        """Test get_next_numero_facture_pro_forma handles invalid formats."""
        from facture_proforma.utils import get_next_numero_facture_pro_forma
        from datetime import datetime

        company = Company.objects.create(raison_sociale="UtilCoPF2", ICE="UTILPF456")
        ville = Ville.objects.create(nom="UtilVillePF2")
        client = Client.objects.create(
            code_client="UTILPF002",
            client_type="PM",
            raison_sociale="Util Client PF2",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_pf2@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCashPF2")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create with invalid format
        FactureProForma.objects.create(
            numero_facture=f"INVALID/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_pro_forma(company.id)
        assert "0001" in next_num or "0002" in next_num

    def test_get_next_numero_empty_db(self):
        """Test get_next_numero_facture_pro_forma with no existing records."""
        from facture_proforma.utils import get_next_numero_facture_pro_forma
        from datetime import datetime

        # Clear all
        FactureProForma.objects.all().delete()
        
        company = Company.objects.create(raison_sociale="Empty Test Co", ICE="EMPTY123")

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"0001/{year_suffix}"

    def test_get_next_numero_consecutive(self):
        """Test get_next_numero_facture_pro_forma with consecutive numbers."""
        from facture_proforma.utils import get_next_numero_facture_pro_forma
        from datetime import datetime

        company = Company.objects.create(raison_sociale="UtilCoPF3", ICE="UTILPF789")
        ville = Ville.objects.create(nom="UtilVillePF3")
        client = Client.objects.create(
            code_client="UTILPF003",
            client_type="PM",
            raison_sociale="Util Client PF3",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="util_pf3@example.com", password="pass"
        )
        mode = ModePaiement.objects.create(nom="UtilCashPF3")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create consecutive factures
        FactureProForma.objects.create(
            numero_facture=f"0001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureProForma.objects.create(
            numero_facture=f"0002/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"0003/{year_suffix}"


@pytest.mark.django_db
class TestFactureProFormaModelExtra(SharedDocumentModelTestsMixin):
    """Extra tests for FactureProForma model methods."""

    numero_field = "numero_facture"

    def test_recalc_totals(self, pf_conv_with_lines):
        self.shared_test_recalc_totals(pf_conv_with_lines)

    def test_lignes_count(self, pf_conv_with_lines):
        self.shared_test_lignes_count(pf_conv_with_lines)

    def test_str_representation(self, pf_conv_obj):
        self.shared_test_str_representation(pf_conv_obj)

    def test_convert_to_facture_client(self, pf_conv_with_lines, pf_conv_user):
        """Test converting FactureProForma to FactureClient."""
        facture = pf_conv_with_lines.convert_to_facture_client("FC-PF001", pf_conv_user)

        assert facture is not None
        assert facture.client == pf_conv_with_lines.client
        assert facture.mode_paiement == pf_conv_with_lines.mode_paiement
        assert facture.created_by_user == pf_conv_user
        assert facture.lignes.count() == pf_conv_with_lines.lignes.count()

    def test_conversion_copies_remise(self, pf_conv_with_lines, pf_conv_user):
        """Test that conversion copies remise fields."""
        facture = pf_conv_with_lines.convert_to_facture_client("FC-PF002", pf_conv_user)

        assert facture.remise == pf_conv_with_lines.remise
        assert facture.remise_type == pf_conv_with_lines.remise_type

    def test_conversion_copies_line_details(self, pf_conv_with_lines, pf_conv_user):
        """Test that conversion copies line details correctly."""
        facture = pf_conv_with_lines.convert_to_facture_client("FC-PF003", pf_conv_user)

        original_line = pf_conv_with_lines.lignes.first()
        new_line = facture.lignes.first()

        assert new_line.article == original_line.article
        assert new_line.quantity == original_line.quantity
        assert new_line.prix_vente == original_line.prix_vente


@pytest.mark.django_db
class TestFactureProFormaAdminExtra(SharedDocumentAdminTestsMixin):
    """Extra tests for FactureProForma admin."""

    from facture_proforma.admin import FactureProFormaAdmin, FactureProFormaLineAdmin

    AdminClass = FactureProFormaAdmin
    LineAdminClass = FactureProFormaLineAdmin
    Model = FactureProForma
    LineModel = FactureProFormaLine
    numero_field = "numero_facture"
    date_field = "date_facture"
    line_numero_method = "numero_facture"

    def test_admin_get_numero_field_name(self):
        self.shared_test_admin_get_numero_field_name()

    def test_admin_get_date_field_name(self):
        self.shared_test_admin_get_date_field_name()

    def test_line_admin_numero_facture(self, pf_conv_with_lines):
        self.shared_test_line_admin_numero(pf_conv_with_lines)

    def test_line_admin_article_reference(self, pf_conv_with_lines):
        self.shared_test_line_admin_article_reference(pf_conv_with_lines)

    def test_line_admin_article_designation(self, pf_conv_with_lines):
        self.shared_test_line_admin_article_designation(pf_conv_with_lines)


@pytest.mark.django_db
class TestFactureProFormaLineModelExtra:
    """Extra tests for FactureProFormaLine model."""

    def test_line_str_representation(self, pf_conv_with_lines):
        """Test FactureProFormaLine string representation."""
        line = pf_conv_with_lines.lignes.first()
        expected = f"{pf_conv_with_lines} - {line.article}"
        assert str(line) == expected


@pytest.mark.django_db
class TestFactureProFormaPDFGeneration:
    """Test PDF generation for facture pro forma."""

    def test_generate_pdf(self, pf_conv_user, pf_conv_company, pf_conv_with_lines):
        """Test generating PDF for facture pro forma."""
        from django.urls import reverse
        from rest_framework import status

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse(
                "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
            )
            + f"?company_id={pf_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "filename" in response["Content-Disposition"]

    def test_pdf_no_company_id(self, pf_conv_user, pf_conv_company, pf_conv_with_lines):
        """Test PDF fails without company_id."""
        from django.urls import reverse
        from rest_framework import status

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = reverse(
            "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pdf_not_found(self, pf_conv_user, pf_conv_company):
        """Test PDF fails for non-existent facture proforma."""
        from django.urls import reverse
        from rest_framework import status

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse("facture_proforma:facture-proforma-pdf-fr", args=[99999])
            + f"?company_id={pf_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_pdf_sans_remise_type(
        self, pf_conv_user, pf_conv_company, pf_conv_with_lines
    ):
        """Test PDF generation with sans_remise type."""
        from django.urls import reverse
        from rest_framework import status

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse(
                "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
            )
            + f"?company_id={pf_conv_company.id}&type=sans_remise"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"

    def test_pdf_avec_unite_type(
        self, pf_conv_user, pf_conv_company, pf_conv_with_lines
    ):
        """Test PDF generation with avec_unite type."""
        from django.urls import reverse
        from rest_framework import status

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse(
                "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
            )
            + f"?company_id={pf_conv_company.id}&type=avec_unite"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
