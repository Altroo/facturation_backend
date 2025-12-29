from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from account.models import CustomUser, Membership
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
from .filters import DeviFilter
from .models import Devi, DeviLine

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


@pytest.fixture
def devi_conv_user():
    return CustomUser.objects.create_user(
        email="devi_conv@example.com",
        password="pass",
        first_name="Devi",
        last_name="Conv",
    )


@pytest.fixture
def devi_conv_company():
    return Company.objects.create(raison_sociale="Devi Conv Co", ICE="DEVICONV")


@pytest.fixture
def devi_conv_ville():
    return Ville.objects.create(nom="ConvVille")


@pytest.fixture
def devi_conv_client(devi_conv_ville, devi_conv_company):
    return Client.objects.create(
        code_client="CONV001",
        client_type="PM",
        raison_sociale="Conv Client",
        ville=devi_conv_ville,
        company=devi_conv_company,
    )


@pytest.fixture
def devi_conv_mode_paiement():
    return ModePaiement.objects.create(nom="ConvPay")


@pytest.fixture
def devi_conv_article(devi_conv_company):
    return Article.objects.create(
        company=devi_conv_company,
        reference="CONV001",
        designation="Conv Article",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )


@pytest.fixture
def devi_conv_obj(devi_conv_client, devi_conv_mode_paiement, devi_conv_user):
    return Devi.objects.create(
        numero_devis="CONV/01",
        client=devi_conv_client,
        date_devis="2025-01-01",
        mode_paiement=devi_conv_mode_paiement,
        statut="Brouillon",
        created_by_user=devi_conv_user,
        remise=Decimal("5.00"),
        remise_type="Pourcentage",
    )


@pytest.fixture
def devi_conv_with_lines(devi_conv_obj, devi_conv_article):
    DeviLine.objects.create(
        devis=devi_conv_obj,
        article=devi_conv_article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=2,
    )
    devi_conv_obj.recalc_totals()
    devi_conv_obj.save()
    return devi_conv_obj


# -----------------------------------------------------------------------------
# Test Classes
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestDeviAPI(SharedDocumentAPITestsMixin):
    cfg = DocConfig(
        list_create_url_name="devi:devi-list-create",
        detail_url_name="devi:devi-detail",
        status_update_url_name="devi:devi-statut-update",
        generate_numero_url_name="devi:generate-numero-devis",
        numero_field="numero_devis",
        date_field="date_devis",
        req_field="numero_demande_prix_client",
        fk_mode_paiement_field="mode_paiement",
        line_parent_fk_attr="devis",
        convert_to_facture_client_url_name="devi:convert-to-facture-client",
        convert_to_facture_proforma_url_name="devi:convert-to-facture-proforma",
        convert_to_facture_client_method="convert_to_facture_client",
        convert_to_facture_proforma_method="convert_to_facture_proforma",
    )

    Model = Devi
    LineModel = DeviLine

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="user@dev.com", password="pass", first_name="Test", last_name="User"
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        self.ville = Ville.objects.create(nom="TestVille")
        self.company = Company.objects.create(
            raison_sociale="TestCompany", ICE="ICE-1234"
        )
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

        self.article = Article.objects.create(
            company=self.company,
            reference="ART-001",
            designation="Test Article",
            prix_achat=100.00,
            prix_vente=120.00,
            type_article="Produit",
        )

        self.doc = Devi.objects.create(
            numero_devis="0002/25",
            client=self.client_obj,
            date_devis="2024-06-01",
            numero_demande_prix_client="REQ-001",
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        self.doc_line = DeviLine.objects.create(
            devis=self.doc,
            article=self.article,
            prix_achat=100.00,
            prix_vente=120.00,
            quantity=2,
            remise=5.00,
            remise_type="Pourcentage",
        )

    def test_list_devi_requires_client_id(self):
        self.shared_test_list_requires_company_id()

    def test_list_devi(self):
        self.shared_test_list()

    def test_list_devi_with_pagination(self):
        self.shared_test_list_with_pagination()

    def test_create_devi_basic(self):
        self.shared_test_create_basic()

    def test_create_devi_with_lignes(self):
        self.shared_test_create_with_lignes()

    def test_get_devi_detail(self):
        self.shared_test_get_detail()

    def test_create_devi_without_client_fails(self):
        self.shared_test_create_without_client_fails()

    def test_create_devi_invalid_numero_format(self):
        self.shared_test_create_invalid_numero_format()

    def test_get_devi_detail_unauthorized(self):
        self.shared_test_get_detail_unauthorized()

    def test_update_devi_basic(self):
        self.shared_test_update_basic()

    def test_update_devi_with_lignes_upsert(self):
        self.shared_test_update_with_lignes_upsert()

    def test_update_devi_delete_missing_lines(self):
        self.shared_test_update_delete_missing_lines()

    def test_delete_devi(self):
        self.shared_test_delete()

    def test_filter_devi_by_statut(self):
        self.shared_test_filter_by_statut()

    def test_search_devi_by_numero(self):
        self.shared_test_search_by_numero()

    def test_generate_numero_devis(self):
        self.shared_test_generate_numero()

    def test_update_devi_status(self):
        self.shared_test_update_status()

    def test_update_devi_status_invalid(self):
        self.shared_test_update_status_invalid()

    def test_convert_to_facture_client(self, monkeypatch):
        self.shared_test_convert_to_facture_client(monkeypatch)

    def test_convert_to_facture_proforma(self, monkeypatch):
        self.shared_test_convert_to_facture_proforma(monkeypatch)

    def test_smoke_totals_present_on_detail(self):
        self.shared_test_get_detail()

    def test_smoke_totals_present_on_list(self):
        self.shared_test_list()

    def test_smoke_upsert_lines(self):
        self.shared_test_update_with_lignes_upsert()


@pytest.mark.django_db
class TestDeviFilters(SharedDocumentFilterTestsMixin):
    FilterClass = DeviFilter

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

        self.doc1 = Devi.objects.create(
            numero_devis="NUM-001",
            client=self.client_a,
            date_devis="2024-06-01",
            numero_demande_prix_client="REQ-ALPHA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.doc2 = Devi.objects.create(
            numero_devis="NUM-002",
            client=self.client_b,
            date_devis="2024-06-02",
            numero_demande_prix_client="REQ-BETA",
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
            statut="Accepté",
        )

    def test_global_search_matches_numero_and_client_and_req(self):
        self.shared_test_global_search_matches_numero_and_client_and_req(
            numero_field="numero_devis",
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
        base_qs = Devi.objects.all()
        filt = DeviFilter({"search": ""}, queryset=base_qs)
        assert filt.qs.count() == base_qs.count()

    def test_filter_statut_with_empty_string(self):
        """Test filter_statut with empty string returns all (line 21 coverage)."""
        base_qs = Devi.objects.all()
        count_before = base_qs.count()
        filt = DeviFilter({"statut": ""}, queryset=base_qs)
        assert filt.qs.count() == count_before

    def test_filter_statut_direct_call_empty(self):
        """Test filter_statut method directly with empty value (line 21 coverage)."""
        base_qs = Devi.objects.all()
        result = DeviFilter.filter_statut(base_qs, "statut", "")
        assert result.count() == base_qs.count()

    def test_filter_statut_direct_call_none(self):
        """Test filter_statut method directly with None value (line 21 coverage)."""
        base_qs = Devi.objects.all()
        result = DeviFilter.filter_statut(base_qs, "statut", None)
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_empty(self):
        """Test global_search method directly with empty value (line 27 coverage)."""
        base_qs = Devi.objects.all()
        result = DeviFilter.global_search(base_qs, "search", "")
        assert result.count() == base_qs.count()

    def test_global_search_direct_call_whitespace(self):
        """Test global_search method directly with whitespace (line 27 coverage)."""
        base_qs = Devi.objects.all()
        result = DeviFilter.global_search(base_qs, "search", "   ")
        assert result.count() == base_qs.count()


@pytest.mark.django_db
class TestDeviConversionExtra:
    """Extra tests for Devi conversion methods."""

    def test_convert_to_facture_proforma(self, devi_conv_with_lines, devi_conv_user):
        """Test converting Devi to FactureProForma."""
        proforma = devi_conv_with_lines.convert_to_facture_proforma(
            "FP-001", devi_conv_user
        )

        assert proforma is not None
        assert proforma.client == devi_conv_with_lines.client
        assert proforma.mode_paiement == devi_conv_with_lines.mode_paiement
        assert proforma.created_by_user == devi_conv_user
        assert proforma.lignes.count() == devi_conv_with_lines.lignes.count()

    def test_convert_to_facture_client(self, devi_conv_with_lines, devi_conv_user):
        """Test converting Devi to FactureClient."""
        facture = devi_conv_with_lines.convert_to_facture_client(
            "FC-001", devi_conv_user
        )

        assert facture is not None
        assert facture.client == devi_conv_with_lines.client
        assert facture.mode_paiement == devi_conv_with_lines.mode_paiement
        assert facture.created_by_user == devi_conv_user
        assert facture.lignes.count() == devi_conv_with_lines.lignes.count()

    def test_conversion_copies_remise(self, devi_conv_with_lines, devi_conv_user):
        """Test that conversion copies remise fields."""
        proforma = devi_conv_with_lines.convert_to_facture_proforma(
            "FP-002", devi_conv_user
        )

        assert proforma.remise == devi_conv_with_lines.remise
        assert proforma.remise_type == devi_conv_with_lines.remise_type

    def test_conversion_copies_line_details(self, devi_conv_with_lines, devi_conv_user):
        """Test that conversion copies line details correctly."""
        proforma = devi_conv_with_lines.convert_to_facture_proforma(
            "FP-003", devi_conv_user
        )

        original_line = devi_conv_with_lines.lignes.first()
        new_line = proforma.lignes.first()

        assert new_line.article == original_line.article
        assert new_line.quantity == original_line.quantity
        assert new_line.prix_vente == original_line.prix_vente


@pytest.mark.django_db
class TestFactureProFormaConversionExtra:
    """Extra tests for FactureProForma conversion."""

    def test_convert_to_facture_client(self, devi_conv_with_lines, devi_conv_user):
        """Test converting FactureProForma to FactureClient."""
        proforma = devi_conv_with_lines.convert_to_facture_proforma(
            "FP-004", devi_conv_user
        )
        facture = proforma.convert_to_facture_client("FC-002", devi_conv_user)

        assert facture is not None
        assert facture.client == proforma.client
        assert facture.mode_paiement == proforma.mode_paiement
        assert facture.created_by_user == devi_conv_user
        assert facture.lignes.count() == proforma.lignes.count()


@pytest.mark.django_db
class TestDeviUtilsExtra:
    """Extra tests for devi utils."""

    def test_get_next_numero_devis_with_gaps(self):
        """Test get_next_numero_devis finds gaps in number sequence."""
        from devi.utils import get_next_numero_devis
        from datetime import datetime

        # Create company, client, user, and mode_paiement first
        company = Company.objects.create(raison_sociale="Test Co", ICE="123")
        ville = Ville.objects.create(nom="TestVille")
        client = Client.objects.create(
            code_client="CLT001",
            client_type="PM",
            raison_sociale="Test Client",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="testuser@example.com", password="pass"
        )
        mode_paiement = ModePaiement.objects.create(nom="Cash")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create devis with numbers 0001, 0003, 0004 (leaving gap at 0002)
        Devi.objects.create(
            numero_devis=f"0001/{year_suffix}",
            client=client,
            date_devis="2025-01-01",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        Devi.objects.create(
            numero_devis=f"0003/{year_suffix}",
            client=client,
            date_devis="2025-01-02",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        Devi.objects.create(
            numero_devis=f"0004/{year_suffix}",
            client=client,
            date_devis="2025-01-03",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        # Should find gap at 0002
        next_num = get_next_numero_devis()
        assert next_num == f"0002/{year_suffix}"

    def test_get_next_numero_devis_with_invalid_format(self):
        """Test get_next_numero_devis handles invalid formats."""
        from devi.utils import get_next_numero_devis
        from datetime import datetime

        # Create fixtures
        company = Company.objects.create(raison_sociale="Test Co2", ICE="456")
        ville = Ville.objects.create(nom="TestVille2")
        client = Client.objects.create(
            code_client="CLT002",
            client_type="PM",
            raison_sociale="Test Client2",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="testuser2@example.com", password="pass"
        )
        mode_paiement = ModePaiement.objects.create(nom="Cash2")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create devis with invalid format (should be skipped)
        Devi.objects.create(
            numero_devis=f"INVALID/{year_suffix}",
            client=client,
            date_devis="2025-01-01",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        # Should return 0001 since invalid format is skipped
        next_num = get_next_numero_devis()
        assert "0001" in next_num or "0002" in next_num

    def test_get_next_numero_devis_empty_db(self):
        """Test get_next_numero_devis with no existing records."""
        from devi.utils import get_next_numero_devis
        from datetime import datetime

        # Clear all devis
        Devi.objects.all().delete()

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_devis()
        assert next_num == f"0001/{year_suffix}"

    def test_get_next_numero_devis_consecutive(self):
        """Test get_next_numero_devis with consecutive numbers."""
        from devi.utils import get_next_numero_devis
        from datetime import datetime

        company = Company.objects.create(raison_sociale="Test Co3", ICE="789")
        ville = Ville.objects.create(nom="TestVille3")
        client = Client.objects.create(
            code_client="CLT003",
            client_type="PM",
            raison_sociale="Test Client3",
            ville=ville,
            company=company,
        )
        user = CustomUser.objects.create_user(
            email="testuser3@example.com", password="pass"
        )
        mode_paiement = ModePaiement.objects.create(nom="Cash3")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create consecutive devis
        Devi.objects.create(
            numero_devis=f"0001/{year_suffix}",
            client=client,
            date_devis="2025-01-01",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        Devi.objects.create(
            numero_devis=f"0002/{year_suffix}",
            client=client,
            date_devis="2025-01-02",
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_devis()
        assert next_num == f"0003/{year_suffix}"


@pytest.mark.django_db
class TestDeviModelExtra(SharedDocumentModelTestsMixin):
    """Extra tests for Devi model methods."""

    numero_field = "numero_devis"

    def test_recalc_totals(self, devi_conv_with_lines):
        self.shared_test_recalc_totals(devi_conv_with_lines)

    def test_lignes_count(self, devi_conv_with_lines):
        self.shared_test_lignes_count(devi_conv_with_lines)

    def test_str_representation(self, devi_conv_obj):
        self.shared_test_str_representation(devi_conv_obj)


@pytest.mark.django_db
class TestDeviAdminExtra(SharedDocumentAdminTestsMixin):
    """Extra tests for Devi admin."""

    from devi.admin import DeviAdmin, DeviLineAdmin

    AdminClass = DeviAdmin
    LineAdminClass = DeviLineAdmin
    Model = Devi
    LineModel = DeviLine
    numero_field = "numero_devis"
    date_field = "date_devis"
    line_numero_method = "devis_numero"

    def test_admin_get_numero_field_name(self):
        self.shared_test_admin_get_numero_field_name()

    def test_admin_get_date_field_name(self):
        self.shared_test_admin_get_date_field_name()

    def test_line_admin_devis_numero(self, devi_conv_with_lines):
        self.shared_test_line_admin_numero(devi_conv_with_lines)

    def test_line_admin_article_reference(self, devi_conv_with_lines):
        self.shared_test_line_admin_article_reference(devi_conv_with_lines)

    def test_line_admin_article_designation(self, devi_conv_with_lines):
        self.shared_test_line_admin_article_designation(devi_conv_with_lines)


@pytest.mark.django_db
class TestDeviLineModelExtra:
    """Extra tests for DeviLine model."""

    def test_line_str_representation(self, devi_conv_with_lines):
        """Test DeviLine string representation."""
        line = devi_conv_with_lines.lignes.first()
        expected = f"{devi_conv_with_lines} - {line.article}"
        assert str(line) == expected
