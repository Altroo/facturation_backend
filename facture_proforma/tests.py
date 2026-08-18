from datetime import datetime
from decimal import Decimal
from re import match

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from rest_framework import status
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
from facture_proforma.admin import FactureProFormaAdmin, FactureProFormaLineAdmin
from facture_proforma.utils import get_next_numero_facture_pro_forma
from logistique.models import LogisticsOrder, LogisticsOrderProforma
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
    return Membership.objects.create(
        user=user,
        company=company,
        role=caissier_role,
        can_change_document_status=True,
    )


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
def pf_conv_ville(pf_conv_company):
    return Ville.objects.create(nom="PFConvVille", company=pf_conv_company)


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
def pf_conv_mode_paiement(pf_conv_company):
    return ModePaiement.objects.create(nom="PFConvPay", company=pf_conv_company)


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

    def test_list_marks_sources_already_linked_to_logistics(self):
        order = LogisticsOrder.objects.create(
            company=self.company,
            numero_commande="LOG-SOURCE-AVAILABILITY",
            fournisseur="Supplier One",
        )
        LogisticsOrderProforma.objects.create(commande=order, proforma=self.doc)

        response = self.client_api.get(
            self._list_create_url(), {"company_id": self.company.id}
        )

        assert response.status_code == status.HTTP_200_OK
        items = (
            response.data
            if isinstance(response.data, list)
            else response.data["results"]
        )
        item = next(value for value in items if value["id"] == self.doc.id)
        assert item["has_logistics_dossier"] is True

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
        year_suffix = f"{datetime.now().year % 100:02d}"
        url = self._generate_url() + f"?company_id={self.company.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert match(r"^P\d{3}/\d{2}$", response.data[self.cfg.numero_field])
        assert response.data[self.cfg.numero_field].endswith(f"/{year_suffix}")

    def test_update_proforma_status(self):
        self.shared_test_update_status()

    def test_update_proforma_status_invalid(self):
        self.shared_test_update_status_invalid()

    def test_accepting_proforma_requires_supplier(self):
        response = self.client_api.patch(
            self._status_url(self.doc.id), {"statut": "Accepté"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "fournisseur" in response.data["details"]
        self.doc.refresh_from_db()
        assert self.doc.statut == "Envoyé"

    def test_model_validation_blocks_accepted_proforma_without_supplier(self):
        self.doc.statut = "Accepté"

        with pytest.raises(DjangoValidationError) as exc_info:
            self.doc.full_clean()

        assert "fournisseur" in exc_info.value.message_dict

    def test_accepting_proforma_with_supplier_succeeds(self):
        self.doc.fournisseur = "Supplier One"
        self.doc.save(update_fields=["fournisseur"])

        response = self.client_api.patch(
            self._status_url(self.doc.id), {"statut": "Accepté"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        self.doc.refresh_from_db()
        assert self.doc.statut == "Accepté"

    def test_full_update_cannot_bypass_supplier_requirement_on_acceptance(self):
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["statut"] = "Accepté"

        response = self.client_api.put(
            self._detail_url(self.doc.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "fournisseur" in response.data["details"]
        self.doc.refresh_from_db()
        assert self.doc.statut == "Envoyé"

    def test_supplier_is_locked_after_logistics_dossier_creation(self):
        self.doc.fournisseur = "Supplier One"
        self.doc.save(update_fields=["fournisseur"])
        order = LogisticsOrder.objects.create(
            company=self.company,
            numero_commande="LOG-SUPPLIER-LOCK",
            fournisseur="Supplier One",
        )
        LogisticsOrderProforma.objects.create(commande=order, proforma=self.doc)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["fournisseur"] = "Supplier Two"

        response = self.client_api.put(
            self._detail_url(self.doc.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "fournisseur" in response.data["details"]
        self.doc.refresh_from_db()
        assert self.doc.fournisseur == "Supplier One"

    def test_model_validation_locks_linked_supplier(self):
        self.doc.fournisseur = "Supplier One"
        self.doc.save(update_fields=["fournisseur"])
        order = LogisticsOrder.objects.create(
            company=self.company,
            numero_commande="LOG-SUPPLIER-MODEL-LOCK",
            fournisseur="Supplier One",
        )
        LogisticsOrderProforma.objects.create(commande=order, proforma=self.doc)
        self.doc.fournisseur = "Supplier Two"

        with pytest.raises(DjangoValidationError) as exc_info:
            self.doc.full_clean()

        assert "fournisseur" in exc_info.value.message_dict

    def test_blank_legacy_supplier_can_be_filled_once_and_propagated(self):
        order = LogisticsOrder.objects.create(
            company=self.company,
            numero_commande="LOG-SUPPLIER-REMEDIATION",
            fournisseur="Legacy Brand Value",
        )
        LogisticsOrderProforma.objects.create(commande=order, proforma=self.doc)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["fournisseur"] = "Supplier One"

        response = self.client_api.put(
            self._detail_url(self.doc.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        self.doc.refresh_from_db()
        order.refresh_from_db()
        assert self.doc.fournisseur == "Supplier One"
        assert order.fournisseur == "Supplier One"
        assert order.events.filter(action="Correction fournisseur source").exists()

    def test_supplier_email_can_be_added_after_logistics_creation_and_propagates(self):
        self.doc.fournisseur = "Supplier One"
        self.doc.save(update_fields=["fournisseur"])
        order = LogisticsOrder.objects.create(
            company=self.company,
            numero_commande="LOG-SUP-EMAIL-FIX",
            fournisseur="Supplier One",
        )
        LogisticsOrderProforma.objects.create(commande=order, proforma=self.doc)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["fournisseur"] = "Supplier One"
        payload["fournisseur_email"] = "supplier@example.com"

        response = self.client_api.put(
            self._detail_url(self.doc.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        self.doc.refresh_from_db()
        order.refresh_from_db()
        assert self.doc.fournisseur_email == "supplier@example.com"
        assert order.fournisseur_email == "supplier@example.com"
        assert order.events.filter(
            action="Correction e-mail fournisseur source"
        ).exists()

    def test_supplier_email_rejects_invalid_address(self):
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["fournisseur"] = "Supplier One"
        payload["fournisseur_email"] = "not-an-email"

        response = self.client_api.put(
            self._detail_url(self.doc.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "fournisseur_email" in response.data["details"]

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

        # Create fixtures
        company = Company.objects.create(raison_sociale="UtilCoPF", ICE="UTILPF123")
        ville = Ville.objects.create(nom="UtilVillePF", company=company)
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
        mode = ModePaiement.objects.create(nom="UtilCashPF", company=company)

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create with gap (P001, P003)
        FactureProForma.objects.create(
            numero_facture=f"P001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureProForma.objects.create(
            numero_facture=f"P003/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"P002/{year_suffix}"

    def test_get_next_numero_with_invalid_format(self):
        """Test get_next_numero_facture_pro_forma handles invalid formats."""

        company = Company.objects.create(raison_sociale="UtilCoPF2", ICE="UTILPF456")
        ville = Ville.objects.create(nom="UtilVillePF2", company=company)
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
        mode = ModePaiement.objects.create(nom="UtilCashPF2", company=company)

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
        assert next_num == f"P001/{year_suffix}"

    def test_get_next_numero_empty_db(self):
        """Test get_next_numero_facture_pro_forma with no existing records."""

        # Clear all
        FactureProForma.objects.all().delete()

        company = Company.objects.create(raison_sociale="Empty Test Co", ICE="EMPTY123")

        year_suffix = f"{datetime.now().year % 100:02d}"
        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"P001/{year_suffix}"

    def test_get_next_numero_consecutive(self):
        """Test get_next_numero_facture_pro_forma with consecutive numbers."""

        company = Company.objects.create(raison_sociale="UtilCoPF3", ICE="UTILPF789")
        ville = Ville.objects.create(nom="UtilVillePF3", company=company)
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
        mode = ModePaiement.objects.create(nom="UtilCashPF3", company=company)

        year_suffix = f"{datetime.now().year % 100:02d}"

        # Create consecutive factures
        FactureProForma.objects.create(
            numero_facture=f"P001/{year_suffix}",
            client=client,
            date_facture="2025-01-01",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )
        FactureProForma.objects.create(
            numero_facture=f"P002/{year_suffix}",
            client=client,
            date_facture="2025-01-02",
            mode_paiement=mode,
            statut="Brouillon",
            created_by_user=user,
        )

        next_num = get_next_numero_facture_pro_forma(company.id)
        assert next_num == f"P003/{year_suffix}"


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
        assert facture.source_proforma == pf_conv_with_lines
        assert facture.lignes.count() == pf_conv_with_lines.lignes.count()

    def test_convert_to_facture_client_only_once_until_facture_deleted(
        self, pf_conv_with_lines, pf_conv_user
    ):
        """Conversion is blocked while the generated invoice exists."""
        facture = pf_conv_with_lines.convert_to_facture_client("FC-PF004", pf_conv_user)

        with pytest.raises(ValueError, match="déjà été convertie"):
            pf_conv_with_lines.convert_to_facture_client("FC-PF005", pf_conv_user)

        facture.delete()
        next_facture = pf_conv_with_lines.convert_to_facture_client(
            "FC-PF006", pf_conv_user
        )

        assert next_facture.source_proforma == pf_conv_with_lines

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

    def test_admin_makes_supplier_readonly_after_logistics_link(
        self, pf_conv_with_lines
    ):
        order = LogisticsOrder.objects.create(
            company=pf_conv_with_lines.company,
            numero_commande="LOG-SUPPLIER-ADMIN-LOCK",
            fournisseur="Supplier One",
        )
        LogisticsOrderProforma.objects.create(
            commande=order, proforma=pf_conv_with_lines
        )
        model_admin = FactureProFormaAdmin(FactureProForma, AdminSite())

        readonly = model_admin.get_readonly_fields(None, pf_conv_with_lines)

        assert "fournisseur" in readonly

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

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = reverse(
            "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_pdf_forbidden_cross_company_document(
        self, pf_conv_user, pf_conv_company, pf_conv_with_lines
    ):
        """Test PDF fails when company_id doesn't own the facture pro forma."""

        other_company = Company.objects.create(
            raison_sociale="Other PF Co", ICE="OTHPF"
        )
        _create_pf_membership(pf_conv_user, other_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse(
                "facture_proforma:facture-proforma-pdf-fr", args=[pf_conv_with_lines.id]
            )
            + f"?company_id={other_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_pdf_not_found(self, pf_conv_user, pf_conv_company):
        """Test PDF fails for non-existent facture pro forma."""

        _create_pf_membership(pf_conv_user, pf_conv_company)

        client_api = APIClient()
        client_api.force_authenticate(user=pf_conv_user)

        url = (
            reverse("facture_proforma:facture-proforma-pdf-fr", args=[99999])
            + f"?company_id={pf_conv_company.id}"
        )
        response = client_api.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_pdf_allows_draft(self, pf_conv_user, pf_conv_company, pf_conv_with_lines):
        """Draft pro forma PDFs are generated with a watermark."""

        _create_pf_membership(pf_conv_user, pf_conv_company)
        pf_conv_with_lines.statut = "Brouillon"
        pf_conv_with_lines.save(update_fields=["statut"])

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

    def test_pdf_sans_remise_type(
        self, pf_conv_user, pf_conv_company, pf_conv_with_lines
    ):
        """Test PDF generation with sans_remise type."""

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


# -----------------------------------------------------------------------------
# Bulk Delete Tests
# -----------------------------------------------------------------------------
@pytest.mark.django_db
class TestBulkDeleteFactureProFormaAPI:
    def setup_method(self):
        self.user = CustomUser.objects.create_user(
            email="bulk_pf@example.com", password="pass"
        )
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.user)

        self.company = Company.objects.create(raison_sociale="BulkPFCo", ICE="BDPFC01")
        caissier_role, _ = Role.objects.get_or_create(name="Caissier")
        Membership.objects.create(
            user=self.user, company=self.company, role=caissier_role
        )

        self.ville = Ville.objects.create(nom="BulkPFVille", company=self.company)
        self.mode_paiement = ModePaiement.objects.create(
            nom="BulkPFPay", company=self.company
        )
        self.client_obj = Client.objects.create(
            code_client="BDPF001",
            client_type="PM",
            raison_sociale="BulkPF Client",
            ville=self.ville,
            company=self.company,
        )
        self.pf1 = FactureProForma.objects.create(
            numero_facture="BKPF/01",
            client=self.client_obj,
            date_facture="2025-01-01",
            mode_paiement=self.mode_paiement,
            statut="Brouillon",
            created_by_user=self.user,
            remise=Decimal("0.00"),
            remise_type="Pourcentage",
        )
        self.pf2 = FactureProForma.objects.create(
            numero_facture="BKPF/02",
            client=self.client_obj,
            date_facture="2025-01-02",
            mode_paiement=self.mode_paiement,
            statut="Brouillon",
            created_by_user=self.user,
            remise=Decimal("0.00"),
            remise_type="Pourcentage",
        )

    def test_bulk_delete_success(self):
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        response = self.api_client.delete(
            url, {"ids": [self.pf1.id, self.pf2.id]}, format="json"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not FactureProForma.objects.filter(
            pk__in=[self.pf1.id, self.pf2.id]
        ).exists()

    def test_bulk_delete_single_record(self):
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        response = self.api_client.delete(url, {"ids": [self.pf1.id]}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not FactureProForma.objects.filter(pk=self.pf1.id).exists()
        assert FactureProForma.objects.filter(pk=self.pf2.id).exists()

    def test_bulk_delete_empty_ids_returns_400(self):
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        response = self.api_client.delete(url, {"ids": []}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_delete_missing_ids_field_returns_400(self):
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        response = self.api_client.delete(url, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_delete_unauthenticated_returns_401(self):
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        anon = APIClient()
        response = anon.delete(url, {"ids": [self.pf1.id]}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_bulk_delete_wrong_company_returns_403(self):
        other_company = Company.objects.create(raison_sociale="OtherCo", ICE="OTHPF1")
        other_ville = Ville.objects.create(nom="OtherPFVille", company=other_company)
        other_mode = ModePaiement.objects.create(
            nom="OtherPFPay", company=other_company
        )
        other_client = Client.objects.create(
            code_client="OTHPF01",
            client_type="PM",
            raison_sociale="Other PF Client",
            ville=other_ville,
            company=other_company,
        )
        other_pf = FactureProForma.objects.create(
            numero_facture="OTHER/PF01",
            client=other_client,
            date_facture="2025-01-01",
            mode_paiement=other_mode,
            statut="Brouillon",
            created_by_user=self.user,
            remise=Decimal("0.00"),
            remise_type="Pourcentage",
        )
        url = reverse("facture_proforma:facture-proforma-bulk-delete")
        response = self.api_client.delete(url, {"ids": [other_pf.id]}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
