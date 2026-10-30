from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from re import match
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Protocol
from urllib.parse import quote

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from parameter.models import ModePaiement, Ville


def _create_core_membership(user, company):
    """Helper to create membership with Caissier role."""
    caissier_role, _ = Role.objects.get_or_create(
        name="Caissier",
    )
    return Membership.objects.create(
        user=user,
        company=company,
        role=caissier_role,
        can_change_document_status=True,
    )


def is_numeric_or_none(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        try:
            Decimal(value)
            return True
        except (InvalidOperation, ValueError):
            return False
    return False


def assert_numeric_equal(actual: Any, expected: float, tol: float = 1e-9) -> None:
    if actual is None:
        assert False, f"Expected numeric value {expected}, got None"
    if isinstance(actual, Decimal):
        actual_f = float(actual)
    elif isinstance(actual, str):
        actual_f = float(Decimal(actual))
    else:
        actual_f = float(actual)
    assert abs(actual_f - float(expected)) <= tol


class _HasId(Protocol):
    id: int


class _HasRefreshFromDb(Protocol):
    def refresh_from_db(self) -> None: ...


@dataclass(frozen=True)
class DocConfig:
    list_create_url_name: str
    detail_url_name: str
    status_update_url_name: str
    generate_numero_url_name: str

    numero_field: str
    date_field: str
    req_field: str
    fk_mode_paiement_field: str
    lignes_field: str = "lignes"

    line_fk_article_field: str = "article"
    line_prix_achat_field: str = "prix_achat"
    line_prix_vente_field: str = "prix_vente"
    line_quantity_field: str = "quantity"
    line_remise_field: str = "remise"
    line_remise_type_field: str = "remise_type"

    line_parent_fk_attr: str = ""

    convert_to_facture_client_url_name: Optional[str] = None
    convert_to_facture_proforma_url_name: Optional[str] = None

    convert_to_facture_client_method: Optional[str] = None
    convert_to_facture_proforma_method: Optional[str] = None


class SharedDocumentAPITestsMixin:
    """
    This mixin must *define* all shared_test_* methods used by child test modules,
    otherwise PyCharm will flag calls as unresolved.
    """

    cfg: DocConfig
    Model: Any
    LineModel: Any

    # Provided by child setup_method (typed to satisfy inspections)
    user: Any
    client_api: APIClient
    company: _HasId
    client_obj: _HasId
    mode_paiement: _HasId
    article: Any
    doc: _HasId | _HasRefreshFromDb
    doc_line: Any

    # --- Common setup method ---
    def base_setup_method(
        self,
        numero_value: str = "0002/25",
        date_value: str = "2024-06-01",
        req_value: str = "REQ-001",
    ) -> None:
        """
        Common setup method that can be called by child classes.
        Sets up user, company, client, article, and basic document.
        Child classes should call this and then customize as needed.
        """
        self.user = CustomUser.objects.create_user(
            email="user@dev.com", password="pass", first_name="Test", last_name="User"
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        self.company = Company.objects.create(
            raison_sociale="TestCompany", ICE="ICE-1234"
        )
        self.ville = Ville.objects.create(nom="TestVille", company=self.company)
        _create_core_membership(self.user, self.company)

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
        self.mode_paiement = ModePaiement.objects.create(
            nom="Bank Transfer", company=self.company
        )

        self.article = Article.objects.create(
            company=self.company,
            reference="ART-001",
            designation="Test Article",
            prix_achat=100.00,
            prix_vente=120.00,
            type_article="Produit",
        )

        # Create document (must be implemented by child or manually)
        # This is a template - child classes will create their specific doc type

    # --- URL helpers ---
    def _list_create_url(self) -> str:
        return reverse(self.cfg.list_create_url_name)

    def _detail_url(self, pk: int) -> str:
        return reverse(self.cfg.detail_url_name, args=[pk])

    def _status_url(self, pk: int) -> str:
        return reverse(self.cfg.status_update_url_name, args=[pk])

    def _generate_url(self) -> str:
        return reverse(self.cfg.generate_numero_url_name)

    def _convert_client_url(self, pk: int) -> str:
        assert self.cfg.convert_to_facture_client_url_name
        return reverse(self.cfg.convert_to_facture_client_url_name, args=[pk])

    def _convert_proforma_url(self, pk: int) -> str:
        assert self.cfg.convert_to_facture_proforma_url_name
        return reverse(self.cfg.convert_to_facture_proforma_url_name, args=[pk])

    # --- payload helpers ---
    def _base_payload(
        self, *, numero: str, date_str: str, req: str, include_mode: bool = True
    ) -> dict:
        payload = {
            self.cfg.numero_field: numero,
            "client": self.client_obj.id,
            self.cfg.date_field: date_str,
            self.cfg.req_field: req,
            "remarque": "New remark",
            "remise": 0.00,
            "remise_type": "Pourcentage",
        }
        if include_mode:
            payload[self.cfg.fk_mode_paiement_field] = self.mode_paiement.id
        return payload

    def _line_payload(
        self,
        *,
        article_id: int,
        prix_achat: float,
        prix_vente: float,
        quantity: int,
        remise: float = 0.0,
        remise_type: str = "Pourcentage",
        line_id: Optional[int] = None,
    ) -> dict:
        d = {
            self.cfg.line_fk_article_field: article_id,
            self.cfg.line_prix_achat_field: prix_achat,
            self.cfg.line_prix_vente_field: prix_vente,
            self.cfg.line_quantity_field: quantity,
            self.cfg.line_remise_field: remise,
            self.cfg.line_remise_type_field: remise_type,
        }
        if line_id is not None:
            d["id"] = line_id
        return d

    @staticmethod
    def _assert_totals_present_numeric_or_none(data: Mapping[str, Any]) -> None:
        for key in ("total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"):
            assert key in data
            assert is_numeric_or_none(data.get(key))

    # --- shared_test_* surface (must match what child tests call) ---
    def shared_test_list_requires_company_id(self) -> None:
        url = self._list_create_url()
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def shared_test_list(self) -> None:
        url = self._list_create_url() + f"?company_id={self.company.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK

        # Handle both list response and dict with 'results' key
        if isinstance(response.data, list):
            data_list = response.data
        elif isinstance(response.data, dict) and "results" in response.data:
            data_list = response.data["results"]
        else:
            raise AssertionError(f"Unexpected response format: {type(response.data)}")

        assert isinstance(data_list, list)
        assert any(d["id"] == self.doc.id for d in data_list)

        item = next(d for d in data_list if d["id"] == self.doc.id)
        assert "client_name" in item
        assert "mode_paiement_name" in item
        assert "created_by_user_name" in item
        assert "lignes_count" in item
        assert "remise" in item
        assert "remise_type" in item
        self._assert_totals_present_numeric_or_none(item)

    def shared_test_list_with_pagination(self) -> None:
        url = self._list_create_url() + f"?company_id={self.company.id}&pagination=true"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "count" in response.data
        results = response.data.get("results") or []
        assert isinstance(results, list)

    def shared_test_create_basic(self) -> None:
        url = self._list_create_url()
        payload = self._base_payload(
            numero="0003/25", date_str="2024-06-02", req="REQ-002"
        )
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data[self.cfg.numero_field] == payload[self.cfg.numero_field]
        assert response.data.get("created_by_user") == self.user.id
        self._assert_totals_present_numeric_or_none(response.data)

    def shared_test_create_with_lignes(self) -> None:
        url = self._list_create_url()
        payload = self._base_payload(
            numero="0004/25", date_str="2024-06-05", req="REQ-010"
        )
        payload[self.cfg.lignes_field] = [
            self._line_payload(
                article_id=self.article.id,
                prix_achat=150.0,
                prix_vente=200.0,
                quantity=1,
                remise=0.0,
                remise_type="Pourcentage",
            )
        ]
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert isinstance(response.data.get(self.cfg.lignes_field), list)
        assert len(response.data[self.cfg.lignes_field]) == 1
        self._assert_totals_present_numeric_or_none(response.data)

    def shared_test_get_detail(self) -> None:
        url = self._detail_url(self.doc.id)
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data[self.cfg.numero_field] == getattr(
            self.doc, self.cfg.numero_field
        )
        self._assert_totals_present_numeric_or_none(response.data)

    def shared_test_create_without_client_fails(self) -> None:
        url = self._list_create_url()
        payload = self._base_payload(
            numero="0005/25", date_str="2024-06-06", req="REQ-011"
        )
        payload["client"] = None
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
        )

    def shared_test_create_invalid_numero_format(self) -> None:
        url = self._list_create_url()
        payload = self._base_payload(
            numero="INVALID", date_str="2024-06-02", req="REQ-002"
        )
        response = self.client_api.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def shared_test_get_detail_unauthorized(self) -> None:
        other_user = get_user_model().objects.create_user(
            email="other@dev.com", password="pass"
        )
        client = APIClient()
        client.force_authenticate(user=other_user)
        url = self._detail_url(self.doc.id)
        response = client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def shared_test_update_basic(self) -> None:
        url = self._detail_url(self.doc.id)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload["remarque"] = "Updated remark"
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        self.doc.refresh_from_db()
        assert getattr(self.doc, "remarque", None) == "Updated remark"

    def shared_test_update_with_lignes_upsert(self) -> None:
        url = self._detail_url(self.doc.id)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload[self.cfg.lignes_field] = [
            self._line_payload(
                article_id=self.article.id,
                prix_achat=110.0,
                prix_vente=120.0,
                quantity=5,
                remise=5.0,
                remise_type="Pourcentage",
                line_id=getattr(self.doc_line, "id", None),
            )
        ]
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

    def shared_test_update_delete_missing_lines(self) -> None:
        url = self._detail_url(self.doc.id)
        payload = self._base_payload(
            numero="0002/25", date_str="2024-06-03", req="REQ-001"
        )
        payload[self.cfg.lignes_field] = []
        response = self.client_api.put(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

    def shared_test_delete(self) -> None:
        url = self._detail_url(self.doc.id)
        response = self.client_api.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def shared_test_filter_by_statut(self) -> None:
        url = (
            self._list_create_url() + f"?company_id={self.company.id}&statut=Brouillon"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK

    def shared_test_search_by_numero(self) -> None:
        numero = getattr(self.doc, self.cfg.numero_field)
        url = (
            self._list_create_url()
            + f"?company_id={self.company.id}&search={quote(numero, safe='')}"
        )
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK

    def shared_test_generate_numero(self) -> None:
        year_suffix = f"{datetime.now().year % 100:02d}"
        url = self._generate_url() + f"?company_id={self.company.id}"
        response = self.client_api.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert match(r"^\d{4}/\d{2}$", response.data[self.cfg.numero_field])
        assert response.data[self.cfg.numero_field].endswith(f"/{year_suffix}")

    def shared_test_update_status(self) -> None:
        url = self._status_url(self.doc.id)
        # Valid transition: Brouillon -> Envoyé
        response = self.client_api.patch(url, {"statut": "Envoyé"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def shared_test_update_status_invalid(self) -> None:
        url = self._status_url(self.doc.id)
        response = self.client_api.patch(
            url, {"statut": "InvalidStatus"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def shared_test_convert_to_facture_client(self, monkeypatch: Any) -> None:
        assert self.cfg.convert_to_facture_client_method
        url = self._convert_client_url(self.doc.id)

        monkeypatch.setattr(
            self.Model,
            self.cfg.convert_to_facture_client_method,
            lambda *_a, **_k: SimpleNamespace(id=999),
        )

        response = self.client_api.post(url, format="json")
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert "id" in response.data

    def shared_test_convert_to_facture_proforma(self, monkeypatch: Any) -> None:
        assert self.cfg.convert_to_facture_proforma_method
        url = self._convert_proforma_url(self.doc.id)

        monkeypatch.setattr(
            self.Model,
            self.cfg.convert_to_facture_proforma_method,
            lambda *_a, **_k: SimpleNamespace(id=999),
        )

        response = self.client_api.post(url, format="json")
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert "id" in response.data


class SharedDocumentFilterTestsMixin:
    FilterClass: Any
    doc1: Any
    doc2: Any
    client_a: _HasId

    def base_filter_setup_method(self) -> None:
        """
        Common setup method for filter tests.
        Sets up user, company, two clients, and two documents.
        """
        user_object = get_user_model()
        self.user = user_object.objects.create_user(
            email="filter@dev.com", password="p"
        )

        self.company = Company.objects.create(raison_sociale="FilterCo", ICE="ICEFILT")
        self.ville = Ville.objects.create(nom="SearchVille", company=self.company)
        _create_core_membership(self.user, self.company)

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
        self.mode = ModePaiement.objects.create(nom="Cash", company=self.company)

    def shared_test_global_search_matches_numero_and_client_and_req(
        self, *, numero_field: str, client_label: str, req_value: str
    ) -> None:
        filt = self.FilterClass(
            {"search": getattr(self.doc1, numero_field)},
            queryset=type(self.doc1).objects.all(),
        )
        assert self.doc1 in filt.qs
        assert self.doc2 not in filt.qs

        filt_client = self.FilterClass(
            {"search": client_label}, queryset=type(self.doc1).objects.all()
        )
        assert self.doc1 in filt_client.qs

        filt_req = self.FilterClass(
            {"search": req_value}, queryset=type(self.doc1).objects.all()
        )
        assert self.doc2 in filt_req.qs

    def shared_test_filter_statut_case_insensitive_and_trim(self) -> None:
        filt = self.FilterClass(
            {"statut": "brouillon"}, queryset=type(self.doc1).objects.all()
        )
        assert self.doc1 in filt.qs
        filt_accept = self.FilterClass(
            {"statut": " accepté "}, queryset=type(self.doc1).objects.all()
        )
        assert self.doc2 in filt_accept.qs

    def shared_test_client_id_filter(self) -> None:
        filt = self.FilterClass(
            {"client_id": self.client_a.id}, queryset=type(self.doc1).objects.all()
        )
        assert list(filt.qs) == [self.doc1]

    def shared_test_empty_search_returns_queryset_unchanged(self) -> None:
        base_qs = type(self.doc1).objects.all()
        filt = self.FilterClass({"search": "   "}, queryset=base_qs)
        assert set(filt.qs) == set(base_qs)

    def shared_test_filter_statut_empty_returns_all(self) -> None:
        """Test filter_statut with empty value returns all results."""
        qs = type(self.doc1).objects.all()
        count_before = qs.count()
        filterset = self.FilterClass(data={"statut": ""}, queryset=qs)
        assert filterset.qs.count() == count_before

    def shared_test_filter_statut_none_returns_all(self) -> None:
        """Test filter_statut with None value returns all results."""
        qs = type(self.doc1).objects.all()
        count_before = qs.count()
        filterset = self.FilterClass(data={"statut": None}, queryset=qs)
        assert filterset.qs.count() == count_before

    def shared_test_search_with_tsquery_metacharacters(self) -> None:
        """Test search skips FTS when tsquery metacharacters are present."""
        qs = type(self.doc1).objects.all()
        # Search with metacharacters like :*?&|!()<>
        filterset = self.FilterClass(data={"search": "test:*"}, queryset=qs)
        # Should not raise and should use fallback
        assert filterset.qs is not None

    def shared_test_search_with_special_chars_fallback(self) -> None:
        """Test search uses fallback with special characters."""
        qs = type(self.doc1).objects.all()
        filterset = self.FilterClass(data={"search": "test&value"}, queryset=qs)
        assert filterset.qs is not None

    def shared_test_search_with_pipe_metachar(self) -> None:
        """Test search with pipe metacharacter uses fallback."""
        qs = type(self.doc1).objects.all()
        filterset = self.FilterClass(data={"search": "A|B"}, queryset=qs)
        assert filterset.qs is not None

    def shared_test_search_with_parentheses_metachar(self) -> None:
        """Test search with parentheses metacharacter uses fallback."""
        qs = type(self.doc1).objects.all()
        filterset = self.FilterClass(data={"search": "(test)"}, queryset=qs)
        assert filterset.qs is not None


class SharedDocumentModelTestsMixin:
    """Shared tests for document model methods.

    Subclasses must define:
    - doc_with_lines: fixture or property returning a document with lines
    - doc_obj: fixture or property returning a document without lines
    - numero_field: str name of the numero field (e.g., 'numero_devis', 'numero_facture')
    """

    doc_with_lines: Any
    doc_obj: Any
    numero_field: str = "numero_facture"

    @staticmethod
    def shared_test_recalc_totals(doc_with_lines: Any) -> None:
        """Test recalc_totals computes correct totals."""
        doc_with_lines.recalc_totals()
        assert doc_with_lines.total_ht > 0

    @staticmethod
    def shared_test_lignes_count(doc_with_lines: Any) -> None:
        """Test lignes relationship."""
        assert doc_with_lines.lignes.count() == 1

    def shared_test_str_representation(self, doc_obj: Any) -> None:
        """Test string representation."""
        assert str(doc_obj) == getattr(doc_obj, self.numero_field)


class SharedDocumentAdminTestsMixin:
    """Shared tests for document admin methods.

    Subclasses must define:
    - AdminClass: the admin class to test
    - LineAdminClass: the line admin class to test
    - Model: the document model
    - LineModel: the document line model
    - numero_field: str name of the numero field
    - date_field: str name of the date field
    - line_numero_method: str name of the line admin's numero display method
    """

    AdminClass: Any
    LineAdminClass: Any
    Model: Any
    LineModel: Any
    numero_field: str = "numero_facture"
    date_field: str = "date_facture"
    line_numero_method: str = "numero_facture"

    def shared_test_admin_get_numero_field_name(self) -> None:
        """Test admin get_numero_field_name method."""

        admin = self.AdminClass(self.Model, AdminSite())
        assert admin.get_numero_field_name() == self.numero_field

    def shared_test_admin_get_date_field_name(self) -> None:
        """Test admin get_date_field_name method."""

        admin = self.AdminClass(self.Model, AdminSite())
        assert admin.get_date_field_name() == self.date_field

    def shared_test_line_admin_numero(self, doc_with_lines: Any) -> None:
        """Test line admin numero display method."""

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        method = getattr(admin, self.line_numero_method)
        assert method(line) == getattr(doc_with_lines, self.numero_field)

    def shared_test_line_admin_article_reference(self, doc_with_lines: Any) -> None:
        """Test line admin article_reference display method."""

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        assert admin.article_reference(line) == line.article.reference

    def shared_test_line_admin_article_designation(self, doc_with_lines: Any) -> None:
        """Test line admin article_designation display method."""

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        assert admin.article_designation(line) == line.article.designation
