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
from .filters import FactureClientFilter
from .models import FactureClient, FactureClientLine


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
