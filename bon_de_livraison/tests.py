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
from parameter.models import ModePaiement, Ville, LivrePar
from .filters import BonDeLivraisonFilter
from .models import BonDeLivraison, BonDeLivraisonLine

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
pytestmark = pytest.mark.django_db


@pytest.fixture
def bon_de_livraison_user():
    return CustomUser.objects.create_user(
        email="bon_livraison@example.com",
        password="pass",
        first_name="Bon",
        last_name="Livraison",
    )


@pytest.fixture
def bon_de_livraison_company():
    return Company.objects.create(
        raison_sociale="Bon Livraison Co", ICE="BONLIVRAISON"
    )


@pytest.fixture
def bon_de_livraison_ville():
    return Ville.objects.create(nom="LivraisonVille")


@pytest.fixture
def bon_de_livraison_livre_par():
    return LivrePar.objects.create(nom="Jean Dupont")


@pytest.fixture
def bon_de_livraison_client(bon_de_livraison_ville, bon_de_livraison_company):
    return Client.objects.create(
        code_client="BL001",
        client_type="PM",
        raison_sociale="Livraison Client",
        ville=bon_de_livraison_ville,
        company=bon_de_livraison_company,
    )


@pytest.fixture
def bon_de_livraison_mode_paiement():
    return ModePaiement.objects.create(nom="LivraisonPay")


@pytest.fixture
def bon_de_livraison_article(bon_de_livraison_company):
    return Article.objects.create(
        company=bon_de_livraison_company,
        reference="BL001",
        designation="Livraison Article",
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        tva=20,
    )


@pytest.fixture
def bon_de_livraison_obj(
    bon_de_livraison_client,
    bon_de_livraison_mode_paiement,
    bon_de_livraison_livre_par,
    bon_de_livraison_user,
):
    return BonDeLivraison.objects.create(
        numero_bon_livraison="BL/01",
        client=bon_de_livraison_client,
        date_bon_livraison="2025-01-01",
        numero_bon_commande_client="BC-001",
        livre_par=bon_de_livraison_livre_par,
        mode_paiement=bon_de_livraison_mode_paiement,
        statut="Brouillon",
        created_by_user=bon_de_livraison_user,
        remise=Decimal("5.00"),
        remise_type="Pourcentage",
    )


@pytest.fixture
def bon_de_livraison_with_lines(bon_de_livraison_obj, bon_de_livraison_article):
    BonDeLivraisonLine.objects.create(
        bon_de_livraison=bon_de_livraison_obj,
        article=bon_de_livraison_article,
        prix_achat=Decimal("80.00"),
        prix_vente=Decimal("100.00"),
        quantity=2,
    )
    bon_de_livraison_obj.recalc_totals()
    bon_de_livraison_obj.save()
    return bon_de_livraison_obj


# -----------------------------------------------------------------------------
# Test Classes
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestBonDeLivraisonAPI(SharedDocumentAPITestsMixin):
    cfg = DocConfig(
        list_create_url_name="bon_de_livraison:bon-de-livraison-list-create",
        detail_url_name="bon_de_livraison:bon-de-livraison-detail",
        status_update_url_name="bon_de_livraison:bon-de-livraison-statut-update",
        generate_numero_url_name="bon_de_livraison:generate-numero-bon-livraison",
        numero_field="numero_bon_livraison",
        date_field="date_bon_livraison",
        req_field="numero_bon_commande_client",
        fk_mode_paiement_field="mode_paiement",
        line_parent_fk_attr="bon_de_livraison",
        convert_to_facture_client_url_name=None,
        convert_to_facture_proforma_url_name=None,
        convert_to_facture_client_method=None,
        convert_to_facture_proforma_method=None,
    )

    Model = BonDeLivraison
    LineModel = BonDeLivraisonLine

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="user@bon.com", password="pass", first_name="Test", last_name="User"
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
        self.livre_par = LivrePar.objects.create(nom="Jean Dupont")

        self.article = Article.objects.create(
            company=self.company,
            reference="ART-001",
            designation="Test Article",
            prix_achat=100.00,
            prix_vente=120.00,
            type_article="Produit",
        )

        self.doc = BonDeLivraison.objects.create(
            numero_bon_livraison="0002/25",
            client=self.client_obj,
            date_bon_livraison="2024-06-01",
            numero_bon_commande_client="BC-001",
            livre_par=self.livre_par,
            mode_paiement=self.mode_paiement,
            remarque="Test remark",
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        self.doc_line = BonDeLivraisonLine.objects.create(
            bon_de_livraison=self.doc,
            article=self.article,
            prix_achat=100.00,
            prix_vente=120.00,
            quantity=2,
            remise=5.00,
            remise_type="Pourcentage",
        )

    def test_list_bon_de_livraison_requires_client_id(self):
        self.shared_test_list_requires_company_id()

    def test_list_bon_de_livraison(self):
        self.shared_test_list()

    def test_list_bon_de_livraison_with_pagination(self):
        self.shared_test_list_with_pagination()

    def test_create_bon_de_livraison_basic(self):
        self.shared_test_create_basic()

    def test_create_bon_de_livraison_with_lignes(self):
        self.shared_test_create_with_lignes()

    def test_get_bon_de_livraison_detail(self):
        self.shared_test_get_detail()

    def test_create_bon_de_livraison_without_client_fails(self):
        self.shared_test_create_without_client_fails()

    def test_create_bon_de_livraison_invalid_numero_format(self):
        self.shared_test_create_invalid_numero_format()

    def test_get_bon_de_livraison_detail_unauthorized(self):
        self.shared_test_get_detail_unauthorized()

    def test_update_bon_de_livraison_basic(self):
        self.shared_test_update_basic()

    def test_update_bon_de_livraison_with_lignes_upsert(self):
        self.shared_test_update_with_lignes_upsert()

    def test_update_bon_de_livraison_delete_missing_lines(self):
        self.shared_test_update_delete_missing_lines()

    def test_delete_bon_de_livraison(self):
        self.shared_test_delete()

    def test_filter_bon_de_livraison_by_statut(self):
        self.shared_test_filter_by_statut()

    def test_search_bon_de_livraison_by_numero(self):
        self.shared_test_search_by_numero()

    def test_generate_numero_bon_de_livraison(self):
        self.shared_test_generate_numero()

    def test_update_bon_de_livraison_status(self):
        self.shared_test_update_status()

    def test_update_bon_de_livraison_status_invalid(self):
        self.shared_test_update_status_invalid()

    def test_smoke_totals_present_on_detail(self):
        self.shared_test_get_detail()

    def test_smoke_totals_present_on_list(self):
        self.shared_test_list()

    def test_smoke_upsert_lines(self):
        self.shared_test_update_with_lignes_upsert()


@pytest.mark.django_db
class TestBonDeLivraisonFilters(SharedDocumentFilterTestsMixin):
    FilterClass = BonDeLivraisonFilter

    def setup_method(self):
        user_object = get_user_model()
        self.user = user_object.objects.create_user(
            email="filter@bon.com", password="p"
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
        self.livre_par = LivrePar.objects.create(nom="Livreur Test")

        self.doc1 = BonDeLivraison.objects.create(
            numero_bon_livraison="NUM-001",
            client=self.client_a,
            date_bon_livraison="2024-06-01",
            numero_bon_commande_client="BC-ALPHA",
            livre_par=self.livre_par,
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )
        self.doc2 = BonDeLivraison.objects.create(
            numero_bon_livraison="NUM-002",
            client=self.client_b,
            date_bon_livraison="2024-06-02",
            numero_bon_commande_client="BC-BETA",
            livre_par=self.livre_par,
            mode_paiement=self.mode,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
            statut="Accepté",
        )

    def test_filter_statut(self):
        self.shared_test_filter_statut_case_insensitive_and_trim()

    def test_filter_client_id(self):
        self.shared_test_client_id_filter()

    def test_global_search(self):
        self.shared_test_global_search_matches_numero_and_client_and_req(
            numero_field="numero_bon_livraison",
            client_label="client alpha",
            req_value="BC-BETA",
        )


@pytest.mark.django_db
class TestBonDeLivraisonModels(SharedDocumentModelTestsMixin):
    Model = BonDeLivraison
    LineModel = BonDeLivraisonLine

    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="model@bon.com", password="pass"
        )
        self.ville = Ville.objects.create(nom="ModelVille")
        self.company = Company.objects.create(raison_sociale="ModelCo", ICE="ICEMOD")
        Membership.objects.create(user=self.user, company=self.company)

        self.client_obj = Client.objects.create(
            code_client="CMOD",
            client_type="PM",
            raison_sociale="ModelClient",
            company=self.company,
            ville=self.ville,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="ModPay")
        self.livre_par = LivrePar.objects.create(nom="Model Livreur")

        self.article = Article.objects.create(
            company=self.company,
            reference="ARTMOD",
            designation="Model Article",
            prix_achat=100.00,
            prix_vente=150.00,
            tva=20,
        )

        self.doc = BonDeLivraison.objects.create(
            numero_bon_livraison="MOD-001",
            client=self.client_obj,
            date_bon_livraison="2024-05-10",
            numero_bon_commande_client="BC-MOD",
            livre_par=self.livre_par,
            mode_paiement=self.mode_paiement,
            remise=0.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        self.line = BonDeLivraisonLine.objects.create(
            bon_de_livraison=self.doc,
            article=self.article,
            prix_achat=100.00,
            prix_vente=150.00,
            quantity=5,
            remise=10.00,
            remise_type="Pourcentage",
        )

    def test_document_creation(self):
        assert self.doc.pk is not None
        assert str(self.doc) == "MOD-001"

    def test_line_creation(self):
        assert self.line.pk is not None

    def test_totals_recalculation(self):
        self.doc.recalc_totals()
        assert self.doc.total_ht > 0

    def test_totals_with_line_remise(self):
        self.line.remise = Decimal("10.00")
        self.line.remise_type = "Pourcentage"
        self.line.save()
        self.doc.recalc_totals()
        assert self.doc.total_ht > 0

    def test_totals_with_doc_remise(self):
        self.doc.remise = Decimal("5.00")
        self.doc.remise_type = "Pourcentage"
        self.doc.save()
        assert self.doc.total_ttc_apres_remise <= self.doc.total_ttc


@pytest.mark.django_db
class TestBonDeLivraisonAdmin(SharedDocumentAdminTestsMixin):
    Model = BonDeLivraison
    LineModel = BonDeLivraisonLine

    def setup_method(self):
        from django.contrib.admin.sites import site

        self.user = CustomUser.objects.create_superuser(
            email="admin@bon.com", password="pass"
        )
        self.ville = Ville.objects.create(nom="AdminVille")
        self.company = Company.objects.create(raison_sociale="AdminCo", ICE="ICEADM")
        Membership.objects.create(user=self.user, company=self.company)

        self.client_obj = Client.objects.create(
            code_client="CADM",
            client_type="PM",
            raison_sociale="AdminClient",
            company=self.company,
            ville=self.ville,
        )
        self.mode_paiement = ModePaiement.objects.create(nom="AdminPay")
        self.livre_par = LivrePar.objects.create(nom="Admin Livreur")

        self.article = Article.objects.create(
            company=self.company,
            reference="ARTADM",
            designation="Admin Article",
            prix_achat=50.00,
            prix_vente=80.00,
            tva=20,
        )

        self.doc = BonDeLivraison.objects.create(
            numero_bon_livraison="ADM-001",
            client=self.client_obj,
            date_bon_livraison="2024-05-15",
            numero_bon_commande_client="BC-ADM",
            livre_par=self.livre_par,
            mode_paiement=self.mode_paiement,
            remise=5.00,
            remise_type="Pourcentage",
            created_by_user=self.user,
        )

        self.line = BonDeLivraisonLine.objects.create(
            bon_de_livraison=self.doc,
            article=self.article,
            prix_achat=50.00,
            prix_vente=80.00,
            quantity=3,
        )

        self.site = site

    def test_document_admin_registration(self):
        from bon_de_livraison.admin import BonDeLivraisonAdmin
        assert self.Model in self.site._registry
        assert isinstance(self.site._registry[self.Model], BonDeLivraisonAdmin)

    def test_line_admin_registration(self):
        from bon_de_livraison.admin import BonDeLivraisonLineAdmin
        assert self.LineModel in self.site._registry
        assert isinstance(self.site._registry[self.LineModel], BonDeLivraisonLineAdmin)

    def test_document_admin_list_display(self):
        from bon_de_livraison.admin import BonDeLivraisonAdmin
        admin_obj = BonDeLivraisonAdmin(self.Model, self.site)
        assert "numero_bon_livraison" in admin_obj.list_display

    def test_line_admin_list_display(self):
        from bon_de_livraison.admin import BonDeLivraisonLineAdmin
        admin_obj = BonDeLivraisonLineAdmin(self.LineModel, self.site)
        assert len(admin_obj.list_display) > 0


@pytest.mark.django_db
class TestBonDeLivraisonUtilsExtra:
    """Extra tests for bon_de_livraison utils."""

    def test_get_next_numero_bon_livraison_with_gaps(self):
        """Test get_next_numero_bon_livraison finds gaps in number sequence."""
        from bon_de_livraison.utils import get_next_numero_bon_livraison
        from datetime import datetime

        # Create company, client, user, livre_par, and mode_paiement first
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
        livre_par = LivrePar.objects.create(nom="Test Livreur")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create bons with numbers 0001, 0003, 0004 (leaving gap at 0002)
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"0001/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-01",
            numero_bon_commande_client="BC-001",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"0003/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-02",
            numero_bon_commande_client="BC-002",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"0004/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-03",
            numero_bon_commande_client="BC-003",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        # Should find gap at 0002
        next_num = get_next_numero_bon_livraison()
        assert next_num == f"0002/{year_suffix}"

    def test_get_next_numero_bon_livraison_with_invalid_format(self):
        """Test get_next_numero_bon_livraison handles invalid formats."""
        from bon_de_livraison.utils import get_next_numero_bon_livraison
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
        livre_par = LivrePar.objects.create(nom="Test Livreur 2")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create bon with invalid format (should be skipped)
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"INVALID/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-01",
            numero_bon_commande_client="BC-INV",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        # Should return 0001 since invalid format is skipped
        next_num = get_next_numero_bon_livraison()
        assert "0001" in next_num or "0002" in next_num

    def test_get_next_numero_bon_livraison_empty_db(self):
        """Test get_next_numero_bon_livraison with no existing records."""
        from bon_de_livraison.utils import get_next_numero_bon_livraison
        from datetime import datetime

        # Clear all bons
        BonDeLivraison.objects.all().delete()

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_bon_livraison()
        assert next_num == f"0001/{year_suffix}"

    def test_get_next_numero_bon_livraison_consecutive(self):
        """Test get_next_numero_bon_livraison with consecutive numbers."""
        from bon_de_livraison.utils import get_next_numero_bon_livraison
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
        livre_par = LivrePar.objects.create(nom="Test Livreur 3")

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create consecutive bons
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"0001/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-01",
            numero_bon_commande_client="BC-101",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )
        BonDeLivraison.objects.create(
            numero_bon_livraison=f"0002/{year_suffix}",
            client=client,
            date_bon_livraison="2025-01-02",
            numero_bon_commande_client="BC-102",
            livre_par=livre_par,
            mode_paiement=mode_paiement,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_bon_livraison()
        assert next_num == f"0003/{year_suffix}"


@pytest.mark.django_db
class TestBonDeLivraisonAdminExtra(SharedDocumentAdminTestsMixin):
    """Extra tests for BonDeLivraison admin."""

    from bon_de_livraison.admin import BonDeLivraisonAdmin, BonDeLivraisonLineAdmin

    AdminClass = BonDeLivraisonAdmin
    LineAdminClass = BonDeLivraisonLineAdmin
    Model = BonDeLivraison
    LineModel = BonDeLivraisonLine
    numero_field = "numero_bon_livraison"
    date_field = "date_bon_livraison"
    line_numero_method = "bon_de_livraison_numero"

    def test_admin_get_numero_field_name(self):
        self.shared_test_admin_get_numero_field_name()

    def test_admin_get_date_field_name(self):
        self.shared_test_admin_get_date_field_name()

    def test_line_admin_bon_de_livraison_numero(self, bon_de_livraison_with_lines):
        self.shared_test_line_admin_numero(bon_de_livraison_with_lines)

    def test_line_admin_article_reference(self, bon_de_livraison_with_lines):
        self.shared_test_line_admin_article_reference(bon_de_livraison_with_lines)

    def test_line_admin_article_designation(self, bon_de_livraison_with_lines):
        self.shared_test_line_admin_article_designation(bon_de_livraison_with_lines)


@pytest.mark.django_db
class TestBonDeLivraisonLineModelExtra:
    """Extra tests for BonDeLivraisonLine model."""

    def test_line_str_representation(self, bon_de_livraison_with_lines):
        """Test BonDeLivraisonLine string representation."""
        line = bon_de_livraison_with_lines.lignes.first()
        expected = f"{bon_de_livraison_with_lines} - {line.article}"
        assert str(line) == expected
