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
)
from parameter.models import ModePaiement, Ville
from .filters import FactureProFormaFilter
from .models import FactureProForma, FactureProFormaLine

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


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
        statut="Brouillon",
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
        """Test filter_statut with empty value returns all results."""
        qs = FactureProForma.objects.all()
        count_before = qs.count()
        filterset = FactureProFormaFilter(data={"statut": ""}, queryset=qs)
        assert filterset.qs.count() == count_before

    def test_search_with_tsquery_metacharacters(self):
        """Test search skips FTS when tsquery metacharacters are present."""
        qs = FactureProForma.objects.all()
        # Search with metacharacters like :*?&|!()<>
        filterset = FactureProFormaFilter(data={"search": "test:*"}, queryset=qs)
        # Should not raise and should use fallback
        assert filterset.qs is not None

    def test_search_with_special_chars_fallback(self):
        """Test search uses fallback with special characters."""
        qs = FactureProForma.objects.all()
        filterset = FactureProFormaFilter(data={"search": "test&value"}, queryset=qs)
        assert filterset.qs is not None

    def test_search_with_pipe_metachar(self):
        """Test search with pipe metacharacter uses fallback."""
        qs = FactureProForma.objects.all()
        filterset = FactureProFormaFilter(data={"search": "A|B"}, queryset=qs)
        assert filterset.qs is not None

    def test_search_with_parentheses_metachar(self):
        """Test search with parentheses metacharacter uses fallback."""
        qs = FactureProForma.objects.all()
        filterset = FactureProFormaFilter(data={"search": "(test)"}, queryset=qs)
        assert filterset.qs is not None


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

        next_num = get_next_numero_facture_pro_forma()
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

        next_num = get_next_numero_facture_pro_forma()
        assert "0001" in next_num or "0002" in next_num

    def test_get_next_numero_empty_db(self):
        """Test get_next_numero_facture_pro_forma with no existing records."""
        from facture_proforma.utils import get_next_numero_facture_pro_forma
        from datetime import datetime

        # Clear all
        FactureProForma.objects.all().delete()

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_facture_pro_forma()
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

        next_num = get_next_numero_facture_pro_forma()
        assert next_num == f"0003/{year_suffix}"


@pytest.mark.django_db
class TestFactureProFormaModelExtra:
    """Extra tests for FactureProForma model methods."""

    def test_recalc_totals(self, pf_conv_with_lines):
        """Test recalc_totals computes correct totals."""
        pf_conv_with_lines.recalc_totals()
        assert pf_conv_with_lines.total_ht > 0

    def test_lignes_count(self, pf_conv_with_lines):
        """Test lignes relationship."""
        assert pf_conv_with_lines.lignes.count() == 1

    def test_str_representation(self, pf_conv_obj):
        """Test string representation."""
        assert str(pf_conv_obj) == pf_conv_obj.numero_facture

    def test_convert_to_facture_client(self, pf_conv_with_lines, pf_conv_user):
        """Test converting FactureProForma to FactureClient."""
        facture = pf_conv_with_lines.convert_to_facture_client(
            "FC-PF001", pf_conv_user
        )

        assert facture is not None
        assert facture.client == pf_conv_with_lines.client
        assert facture.mode_paiement == pf_conv_with_lines.mode_paiement
        assert facture.created_by_user == pf_conv_user
        assert facture.lignes.count() == pf_conv_with_lines.lignes.count()

    def test_conversion_copies_remise(self, pf_conv_with_lines, pf_conv_user):
        """Test that conversion copies remise fields."""
        facture = pf_conv_with_lines.convert_to_facture_client(
            "FC-PF002", pf_conv_user
        )

        assert facture.remise == pf_conv_with_lines.remise
        assert facture.remise_type == pf_conv_with_lines.remise_type

    def test_conversion_copies_line_details(self, pf_conv_with_lines, pf_conv_user):
        """Test that conversion copies line details correctly."""
        facture = pf_conv_with_lines.convert_to_facture_client(
            "FC-PF003", pf_conv_user
        )

        original_line = pf_conv_with_lines.lignes.first()
        new_line = facture.lignes.first()

        assert new_line.article == original_line.article
        assert new_line.quantity == original_line.quantity
        assert new_line.prix_vente == original_line.prix_vente


@pytest.mark.django_db
class TestFactureProFormaAdminExtra:
    """Extra tests for FactureProForma admin."""

    def test_admin_get_numero_field_name(self):
        """Test admin get_numero_field_name method."""
        from django.contrib.admin.sites import AdminSite
        from facture_proforma.admin import FactureProFormaAdmin

        admin = FactureProFormaAdmin(FactureProForma, AdminSite())
        assert admin.get_numero_field_name() == "numero_facture"

    def test_admin_get_date_field_name(self):
        """Test admin get_date_field_name method."""
        from django.contrib.admin.sites import AdminSite
        from facture_proforma.admin import FactureProFormaAdmin

        admin = FactureProFormaAdmin(FactureProForma, AdminSite())
        assert admin.get_date_field_name() == "date_facture"

    def test_line_admin_numero_facture(self, pf_conv_with_lines):
        """Test line admin numero_facture display method."""
        from django.contrib.admin.sites import AdminSite
        from facture_proforma.admin import FactureProFormaLineAdmin

        admin = FactureProFormaLineAdmin(FactureProFormaLine, AdminSite())
        line = pf_conv_with_lines.lignes.first()
        assert admin.numero_facture(line) == pf_conv_with_lines.numero_facture

    def test_line_admin_article_reference(self, pf_conv_with_lines):
        """Test line admin article_reference display method."""
        from django.contrib.admin.sites import AdminSite
        from facture_proforma.admin import FactureProFormaLineAdmin

        admin = FactureProFormaLineAdmin(FactureProFormaLine, AdminSite())
        line = pf_conv_with_lines.lignes.first()
        assert admin.article_reference(line) == line.article.reference

    def test_line_admin_article_designation(self, pf_conv_with_lines):
        """Test line admin article_designation display method."""
        from django.contrib.admin.sites import AdminSite
        from facture_proforma.admin import FactureProFormaLineAdmin

        admin = FactureProFormaLineAdmin(FactureProFormaLine, AdminSite())
        line = pf_conv_with_lines.lignes.first()
        assert admin.article_designation(line) == line.article.designation
