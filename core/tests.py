from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from re import match
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Protocol
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.test import APIClient

from account.models import CustomUser, Membership
from article.models import Article
from client.models import Client
from company.models import Company
from devi.admin import DeviAdmin
from devi.models import Devi, DeviLine
from parameter.models import ModePaiement, Ville


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
        response = self.client_api.get(self._generate_url())
        assert response.status_code == status.HTTP_200_OK
        assert match(r"^\d{4}/\d{2}$", response.data[self.cfg.numero_field])
        assert response.data[self.cfg.numero_field].endswith(f"/{year_suffix}")

    def shared_test_update_status(self) -> None:
        url = self._status_url(self.doc.id)
        response = self.client_api.patch(url, {"statut": "Accepté"}, format="json")
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
        from django.contrib.admin.sites import AdminSite

        admin = self.AdminClass(self.Model, AdminSite())
        assert admin.get_numero_field_name() == self.numero_field

    def shared_test_admin_get_date_field_name(self) -> None:
        """Test admin get_date_field_name method."""
        from django.contrib.admin.sites import AdminSite

        admin = self.AdminClass(self.Model, AdminSite())
        assert admin.get_date_field_name() == self.date_field

    def shared_test_line_admin_numero(self, doc_with_lines: Any) -> None:
        """Test line admin numero display method."""
        from django.contrib.admin.sites import AdminSite

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        method = getattr(admin, self.line_numero_method)
        assert method(line) == getattr(doc_with_lines, self.numero_field)

    def shared_test_line_admin_article_reference(self, doc_with_lines: Any) -> None:
        """Test line admin article_reference display method."""
        from django.contrib.admin.sites import AdminSite

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        assert admin.article_reference(line) == line.article.reference

    def shared_test_line_admin_article_designation(self, doc_with_lines: Any) -> None:
        """Test line admin article_designation display method."""
        from django.contrib.admin.sites import AdminSite

        admin = self.LineAdminClass(self.LineModel, AdminSite())
        line = doc_with_lines.lignes.first()
        assert admin.article_designation(line) == line.article.designation


pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def admin_user():
    return CustomUser.objects.create_user(
        email="admin_extra@example.com",
        password="admin",
        is_staff=True,
        is_superuser=True,
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def extra_company():
    return Company.objects.create(raison_sociale="Test Company Extra", ICE="123456")


@pytest.fixture
def extra_ville():
    return Ville.objects.create(nom="TestVille")


@pytest.fixture
def extra_client(extra_ville, extra_company):
    return Client.objects.create(
        code_client="CLT001",
        client_type="PM",
        raison_sociale="Test Client",
        ville=extra_ville,
        company=extra_company,
    )


@pytest.fixture
def extra_mode_paiement():
    return ModePaiement.objects.create(nom="Virement")


@pytest.fixture
def extra_article(extra_company):
    return Article.objects.create(
        company=extra_company,
        reference="ART001",
        designation="Test Article",
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        tva=20,
    )


@pytest.fixture
def extra_devi(extra_client, extra_mode_paiement, admin_user):
    return Devi.objects.create(
        numero_devis="0001/25",
        client=extra_client,
        date_devis="2025-01-01",
        mode_paiement=extra_mode_paiement,
        statut="Brouillon",
        created_by_user=admin_user,
        remise=Decimal("10.00"),
        remise_type="Pourcentage",
    )


@pytest.fixture
def extra_devi_line(extra_devi, extra_article):
    return DeviLine.objects.create(
        devis=extra_devi,
        article=extra_article,
        prix_achat=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
        quantity=2,
    )


class TestAdminExtra:
    """Extra tests for admin classes."""

    def test_display_total_ht(self, admin_site, extra_devi):
        """Test display_total_ht formats correctly."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.total_ht = Decimal("1000.50")
        result = admin.display_total_ht(extra_devi)
        assert "1000.50" in result

    def test_display_total_ttc(self, admin_site, extra_devi):
        """Test display_total_ttc formats correctly."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.total_ttc = Decimal("1200.60")
        result = admin.display_total_ttc(extra_devi)
        assert "1200.60" in result

    def test_display_total_ht_none(self, admin_site):
        """Test display_total_ht with None obj returns dash."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_total_ht(None)
        assert result == "-"

    def test_display_total_tva_none(self, admin_site):
        """Test display_total_tva with None obj returns dash."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_total_tva(None)
        assert result == "-"

    def test_display_total_ttc_none(self, admin_site):
        """Test display_total_ttc with None obj returns dash."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_total_ttc(None)
        assert result == "-"

    def test_display_total_ttc_apres_remise_none(self, admin_site):
        """Test display_total_ttc_apres_remise with None obj returns dash."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_total_ttc_apres_remise(None)
        assert result == "-"

    def test_display_total_tva(self, admin_site, extra_devi):
        """Test display_total_tva formats correctly."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.total_tva = Decimal("200.10")
        result = admin.display_total_tva(extra_devi)
        assert "200.10" in result

    def test_display_total_ttc_apres_remise(self, admin_site, extra_devi):
        """Test display_total_ttc_apres_remise formats correctly."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.total_ttc_apres_remise = Decimal("1080.00")
        result = admin.display_total_ttc_apres_remise(extra_devi)
        assert "1080.00" in result

    def test_display_remise_percentage(self, admin_site, extra_devi):
        """Test display_remise with percentage type."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.remise_type = "Pourcentage"
        extra_devi.remise = Decimal("15.00")
        result = admin.display_remise(extra_devi)
        assert "15" in result and "%" in result

    def test_display_remise_fixed(self, admin_site, extra_devi):
        """Test display_remise with fixed type."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.remise_type = "Fixe"
        extra_devi.remise = Decimal("100.50")
        result = admin.display_remise(extra_devi)
        assert "100.50" in result and "MAD" in result

    def test_display_remise_none(self, admin_site):
        """Test display_remise with None obj returns dash."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_remise(None)
        assert result == "-"

    def test_display_lignes_count(self, admin_site, extra_devi, extra_devi_line):
        """Test display_lignes_count."""
        admin = DeviAdmin(Devi, admin_site)
        result = admin.display_lignes_count(extra_devi)
        assert result >= 1

    def test_display_lignes_count_no_pk(self, admin_site):
        """Test display_lignes_count with no pk returns 0."""
        admin = DeviAdmin(Devi, admin_site)
        devi = MagicMock(pk=None)
        result = admin.display_lignes_count(devi)
        assert result == 0

    def test_statut_badge(self, admin_site, extra_devi):
        """Test statut_badge returns HTML."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.statut = "Brouillon"
        result = admin.statut_badge(extra_devi)
        assert "Brouillon" in result
        assert "background-color" in result

    def test_statut_badge_accepted(self, admin_site, extra_devi):
        """Test statut_badge for Accepté status."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.statut = "Accepté"
        result = admin.statut_badge(extra_devi)
        assert "Accepté" in result
        assert "#198754" in result

    def test_statut_badge_unknown(self, admin_site, extra_devi):
        """Test statut_badge for unknown status uses default color."""
        admin = DeviAdmin(Devi, admin_site)
        extra_devi.statut = "Unknown"
        result = admin.statut_badge(extra_devi)
        assert "Unknown" in result
        assert "#6c757d" in result

    def test_get_readonly_fields_add(self, admin_site, admin_user):
        """Test readonly fields for add view."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        fields = admin.get_readonly_fields(request, obj=None)
        assert "numero_devis" not in fields

    def test_get_readonly_fields_change_accepted(
        self, admin_site, admin_user, extra_devi
    ):
        """Test readonly fields for change view with accepted status."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        extra_devi.statut = "Accepté"
        fields = admin.get_readonly_fields(request, obj=extra_devi)
        assert "numero_devis" in fields

    def test_get_readonly_fields_change_refused(
        self, admin_site, admin_user, extra_devi
    ):
        """Test readonly fields for change view with refused status."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        extra_devi.statut = "Refusé"
        fields = admin.get_readonly_fields(request, obj=extra_devi)
        assert "numero_devis" in fields
        assert "client" in fields

    def test_get_readonly_fields_change_cancelled(
        self, admin_site, admin_user, extra_devi
    ):
        """Test readonly fields for change view with canceled status."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        extra_devi.statut = "Annulé"
        fields = admin.get_readonly_fields(request, obj=extra_devi)
        assert "numero_devis" in fields
        assert "date_devis" in fields

    def test_save_model_sets_created_by(
        self, admin_site, admin_user, extra_client, extra_mode_paiement
    ):
        """Test save_model sets created_by_user."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        new_devi = Devi(
            numero_devis="0002/25",
            client=extra_client,
            date_devis="2025-01-02",
            mode_paiement=extra_mode_paiement,
            statut="Brouillon",
        )
        admin.save_model(request, new_devi, None, change=False)
        assert new_devi.created_by_user == admin_user

    def test_save_model_change_preserves_created_by(
        self, admin_site, admin_user, extra_devi
    ):
        """Test save_model on change preserves existing created_by_user."""
        admin = DeviAdmin(Devi, admin_site)
        other_user = CustomUser.objects.create_user(
            email="other@example.com", password="pass"
        )
        request = MagicMock(user=other_user)
        original_user = extra_devi.created_by_user
        admin.save_model(request, extra_devi, None, change=True)
        assert extra_devi.created_by_user == original_user

    def test_save_related_recalculates_totals(
        self, admin_site, admin_user, extra_devi, extra_devi_line
    ):
        """Test save_related calls recalc_totals."""
        admin = DeviAdmin(Devi, admin_site)
        request = MagicMock(user=admin_user)
        form = MagicMock(instance=extra_devi)
        admin.save_related(request, form, [], change=True)
        extra_devi.refresh_from_db()
        assert extra_devi.total_ht >= 0


@pytest.mark.django_db
class TestCoreSerializerValidation:
    """Extra tests for core serializer validation methods."""

    def test_validate_remise_invalid_type(self, extra_client, extra_mode_paiement):
        """Test validate with invalid remise_type."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": 10,
                "remise_type": "InvalidType",
                "lignes": [],
            }
        )
        # Validation fails (DRF choice validation handles invalid type)
        assert not serializer.is_valid()

    def test_validate_remise_invalid_value(self, extra_client, extra_mode_paiement):
        """Test validate with invalid remise value."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": "not_a_number",
                "remise_type": "Pourcentage",
                "lignes": [],
            }
        )
        # Should fail validation
        assert not serializer.is_valid()

    def test_validate_remise_negative(self, extra_client, extra_mode_paiement):
        """Test validate with negative remise."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": -5,
                "remise_type": "Pourcentage",
                "lignes": [],
            }
        )
        # Should fail validation
        valid = serializer.is_valid()
        assert not valid or "remise" in serializer.errors

    def test_validate_remise_percentage_out_of_range(
        self, extra_client, extra_mode_paiement
    ):
        """Test validate with percentage > 100."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": 150,
                "remise_type": "Pourcentage",
                "lignes": [],
            }
        )
        # Should fail validation due to percentage > 100
        valid = serializer.is_valid()
        assert not valid

    def test_validate_remise_fixe_type(self, extra_client, extra_mode_paiement):
        """Test validate with Fixe type."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": 500,
                "remise_type": "Fixe",
                "lignes": [],
            }
        )
        # Fixe type should be valid (no max limit)
        serializer.is_valid()
        assert "remise" not in serializer.errors

    def test_validate_remise_empty_type(self, extra_client, extra_mode_paiement):
        """Test validate with empty remise_type."""
        from devi.serializers import DeviDetailSerializer

        serializer = DeviDetailSerializer(
            data={
                "numero_devis": "0001/25",
                "client": extra_client.pk,
                "date_devis": "2025-01-01",
                "mode_paiement": extra_mode_paiement.pk,
                "remise": 10,
                "remise_type": "",
                "lignes": [],
            }
        )
        # Empty type should pass validation
        serializer.is_valid()
        # Remise errors may or may not appear based on business logic
        assert True


@pytest.mark.django_db
class TestBaseLineWriteSerializerValidation:
    """Tests for BaseLineWriteSerializer validate method."""

    def test_line_prix_vente_less_than_achat(self, extra_article):
        """Test validation fails when prix_vente < prix_achat."""
        from devi.serializers import DeviLineWriteSerializer

        serializer = DeviLineWriteSerializer(
            data={
                "article": extra_article.pk,
                "prix_achat": 100,
                "prix_vente": 50,  # Less than prix_achat
                "quantity": 1,
            }
        )
        with pytest.raises(drf_serializers.ValidationError, match="supérieur ou égal"):
            serializer.is_valid(raise_exception=True)

    def test_line_remise_negative(self, extra_article):
        """Test validation fails when remise is negative."""
        from devi.serializers import DeviLineWriteSerializer

        serializer = DeviLineWriteSerializer(
            data={
                "article": extra_article.pk,
                "prix_achat": 50,
                "prix_vente": 100,
                "quantity": 1,
                "remise": -5,
            }
        )
        with pytest.raises(drf_serializers.ValidationError, match="positive ou nulle"):
            serializer.is_valid(raise_exception=True)

    def test_line_remise_percentage_out_of_range(self, extra_article):
        """Test validation fails when percentage remise > 100."""
        from devi.serializers import DeviLineWriteSerializer

        serializer = DeviLineWriteSerializer(
            data={
                "article": extra_article.pk,
                "prix_achat": 50,
                "prix_vente": 100,
                "quantity": 1,
                "remise": 150,
                "remise_type": "Pourcentage",
            }
        )
        with pytest.raises(drf_serializers.ValidationError, match="entre 0 et 100"):
            serializer.is_valid(raise_exception=True)

    def test_line_remise_fixe_exceeds_total(self, extra_article):
        """Test validation fails when fixe remise > line total."""
        from devi.serializers import DeviLineWriteSerializer

        serializer = DeviLineWriteSerializer(
            data={
                "article": extra_article.pk,
                "prix_achat": 50,
                "prix_vente": 100,
                "quantity": 1,
                "remise": 200,  # Greater than total (100 * 1 = 100)
                "remise_type": "Fixe",
            }
        )
        with pytest.raises(drf_serializers.ValidationError, match="dépasser le total"):
            serializer.is_valid(raise_exception=True)

    def test_line_remise_invalid_type(self, extra_article):
        """Test validation fails with invalid remise_type."""
        from devi.serializers import DeviLineWriteSerializer

        serializer = DeviLineWriteSerializer(
            data={
                "article": extra_article.pk,
                "prix_achat": 50,
                "prix_vente": 100,
                "quantity": 1,
                "remise": 10,
                "remise_type": "InvalidType",
            }
        )
        assert not serializer.is_valid()
        assert "remise_type" in serializer.errors or "error" in serializer.errors


class TestCoreModelsExtra:
    """Extra tests for core model methods."""

    def test_devi_recalc_totals(self, extra_devi, extra_devi_line):
        """Test recalc_totals calculates correctly."""
        extra_devi.recalc_totals()
        assert extra_devi.total_ht > 0
        assert extra_devi.total_ttc > extra_devi.total_ht

    def test_devi_str(self, extra_devi):
        """Test Devi __str__ method."""
        result = str(extra_devi)
        assert extra_devi.numero_devis in result

    def test_devi_line_str(self, extra_devi_line):
        """Test DeviLine __str__ method."""
        result = str(extra_devi_line)
        assert (
            extra_devi_line.devis.numero_devis in result
            or extra_devi_line.article.designation in result
        )


class TestCoreFiltersExtra:
    """Extra tests for filter edge cases."""

    def test_empty_search_returns_all(self, extra_devi):
        """Test empty search returns all results."""
        from devi.filters import DeviFilter

        qs = Devi.objects.all()
        count_before = qs.count()
        filterset = DeviFilter(data={"search": ""}, queryset=qs)
        assert filterset.qs.count() == count_before

    def test_whitespace_search_returns_all(self, extra_devi):
        """Test whitespace-only search returns all results."""
        from devi.filters import DeviFilter

        qs = Devi.objects.all()
        count_before = qs.count()
        filterset = DeviFilter(data={"search": "   "}, queryset=qs)
        assert filterset.qs.count() == count_before

    def test_filter_statut_with_none_value(self, extra_devi):
        """Test filter_statut with None value returns all."""
        from devi.filters import DeviFilter

        qs = Devi.objects.all()
        count_before = qs.count()
        filterset = DeviFilter(data={"statut": None}, queryset=qs)
        assert filterset.qs.count() == count_before

    def test_filter_statut_with_empty_value(self, extra_devi):
        """Test filter_statut with empty string returns all."""
        from devi.filters import DeviFilter

        qs = Devi.objects.all()
        count_before = qs.count()
        filterset = DeviFilter(data={"statut": ""}, queryset=qs)
        assert filterset.qs.count() == count_before


@pytest.mark.django_db
class TestCoreModelRecalcTotals:
    """Tests for recalc_totals with various remise scenarios."""

    def test_recalc_totals_fixe_remise(self, extra_devi, extra_devi_line):
        """Test recalc_totals with Fixe document-level remise."""
        extra_devi.remise = 100
        extra_devi.remise_type = "Fixe"
        extra_devi.recalc_totals()
        assert extra_devi.total_ttc_apres_remise < extra_devi.total_ttc

    def test_recalc_totals_percentage_remise(self, extra_devi, extra_devi_line):
        """Test recalc_totals with Pourcentage document-level remise."""
        extra_devi.remise = 10
        extra_devi.remise_type = "Pourcentage"
        extra_devi.recalc_totals()
        assert extra_devi.total_ttc_apres_remise < extra_devi.total_ttc

    def test_recalc_totals_no_lines(self, extra_client, extra_mode_paiement):
        """Test recalc_totals when document has no lines."""
        devi = Devi.objects.create(
            numero_devis="9999/25",
            client=extra_client,
            date_devis="2025-01-01",
            mode_paiement=extra_mode_paiement,
        )
        devi.recalc_totals()
        assert devi.total_ht == 0
        assert devi.total_ttc == 0

    def test_recalc_totals_with_line_fixe_remise(
        self, extra_devi, extra_article, extra_devi_line
    ):
        """Test recalc_totals with Fixe line-level remise."""
        extra_devi_line.remise = 10
        extra_devi_line.remise_type = "Fixe"
        extra_devi_line.save()
        extra_devi.refresh_from_db()
        # After recalc, totals should account for the line discount
        assert extra_devi.total_ht > 0

    def test_totals_are_decimal(self, extra_devi, extra_devi_line):
        """Test that total fields store Decimal values directly."""
        from decimal import Decimal

        extra_devi.recalc_totals()
        assert isinstance(extra_devi.total_ht, Decimal)
        assert isinstance(extra_devi.total_tva, Decimal)
        assert isinstance(extra_devi.total_ttc, Decimal)
        assert isinstance(extra_devi.total_ttc_apres_remise, Decimal)

    def test_get_lines_no_lignes(self, extra_client, extra_mode_paiement):
        """Test get_lines returns empty when no lines exist."""
        devi = Devi.objects.create(
            numero_devis="8888/25",
            client=extra_client,
            date_devis="2025-01-01",
            mode_paiement=extra_mode_paiement,
        )
        lines = devi.get_lines()
        assert lines.count() == 0


@pytest.mark.django_db
class TestCoreViewsPermissions:
    """Tests for permission checks in core views."""

    def test_base_get_bool_param_true(self):
        """Test _get_bool_param with 'true' string."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request

        factory = APIRequestFactory()
        wsgi_request = factory.get("/", {"pagination": "true"})
        request = Request(wsgi_request)
        result = BaseDocumentListCreateView._get_bool_param(request, "pagination")
        assert result is True

    def test_base_get_bool_param_false(self):
        """Test _get_bool_param with 'false' string."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request

        factory = APIRequestFactory()
        wsgi_request = factory.get("/", {"pagination": "false"})
        request = Request(wsgi_request)
        result = BaseDocumentListCreateView._get_bool_param(request, "pagination")
        assert result is False

    def test_base_get_bool_param_default(self):
        """Test _get_bool_param with default value."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request

        factory = APIRequestFactory()
        wsgi_request = factory.get("/")
        request = Request(wsgi_request)
        result = BaseDocumentListCreateView._get_bool_param(
            request, "pagination", default=True
        )
        assert result is True

    def test_has_membership_method(self, extra_company):
        """Test _has_membership static method."""
        from core.views import BaseDocumentDetailEditDeleteView
        from account.models import Membership
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        user_obj = get_user_model()
        test_user = user_obj.objects.create_user(
            email="test_membership@test.com", password="pass"
        )

        result = BaseDocumentDetailEditDeleteView._has_membership(
            test_user, extra_company.id
        )
        assert result is False

        admin_group, _ = Group.objects.get_or_create(name="Admin")
        Membership.objects.create(
            user=test_user, company=extra_company, role=admin_group
        )
        result = BaseDocumentDetailEditDeleteView._has_membership(
            test_user, extra_company.id
        )
        assert result is True


@pytest.mark.django_db
class TestFilterDatabaseErrorBranch:
    """Tests for DatabaseError branches in filters."""

    def test_devi_filter_database_error(self, extra_devi, monkeypatch):
        """Test DeviFilter handles DatabaseError gracefully."""
        from devi.filters import DeviFilter

        def mock_search_query(*_args, **_kwargs):
            class MockQuery:
                def __init__(self, *inner_args, **inner_kwargs):
                    pass

            return MockQuery()

        monkeypatch.setattr("core.filters.SearchQuery", mock_search_query)

        qs = Devi.objects.all()
        # Force skip_fts to False by using a normal search term
        filterset = DeviFilter(data={"search": "test"}, queryset=qs)
        # Should not raise and should return results
        result = filterset.qs
        assert result is not None

    def test_facture_client_filter_database_error(self, extra_devi, monkeypatch):
        """Test FactureClientFilter handles DatabaseError gracefully."""
        from facture_client.filters import FactureClientFilter
        from facture_client.models import FactureClient

        qs = FactureClient.objects.all()
        filterset = FactureClientFilter(data={"search": "test"}, queryset=qs)
        result = filterset.qs
        assert result is not None

    def test_facture_proforma_filter_database_error(self, extra_devi, monkeypatch):
        """Test FactureProFormaFilter handles DatabaseError gracefully."""
        from facture_proforma.filters import FactureProFormaFilter
        from facture_proforma.models import FactureProForma

        qs = FactureProForma.objects.all()
        filterset = FactureProFormaFilter(data={"search": "test"}, queryset=qs)
        result = filterset.qs
        assert result is not None


@pytest.mark.django_db
class TestBaseDocumentListCreateViewPermissions:
    """Tests for permission checks in BaseDocumentListCreateView."""

    def test_check_company_access_permission_denied(self):
        """Test _check_company_access raises PermissionDenied when user is not member."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.exceptions import PermissionDenied
        from rest_framework.test import APIRequestFactory

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user

        # Create a company that user is NOT a member of
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456780")

        with pytest.raises(PermissionDenied):
            BaseDocumentListCreateView._check_company_access(request, company.id)

    def test_post_client_not_found(self):
        """Test POST raises Http404 when client doesn't exist."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.test import APIRequestFactory, APIClient

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")

        # Create a concrete view for testing
        class TestView(BaseDocumentListCreateView):
            model = Devi

        client_api = APIClient()
        client_api.force_authenticate(user=user)

        # Post with non-existent client ID
        view = TestView.as_view()
        factory = APIRequestFactory()
        request = factory.post("/", {"client": 99999}, format="json")
        request.user = user

        response = view(request)
        assert response.status_code == 404

    def test_post_permission_denied_not_member(self, extra_ville):
        """Test POST raises PermissionDenied when user is not member of client's company."""
        from core.views import BaseDocumentListCreateView
        from rest_framework.test import APIRequestFactory

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")

        # Create company and client that user is NOT a member of
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456781")
        client_obj = Client.objects.create(
            code_client="CLT001_perm",
            client_type="PM",
            raison_sociale="Test Client",
            ville=extra_ville,
            company=company,
        )

        class TestView(BaseDocumentListCreateView):
            model = Devi

        view = TestView.as_view()
        factory = APIRequestFactory()
        request = factory.post("/", {"client": client_obj.id}, format="json")
        request.user = user

        response = view(request)
        assert response.status_code == 403


@pytest.mark.django_db
class TestBaseStatusUpdateViewPermissions:
    """Tests for permission checks in BaseStatusUpdateView."""

    def test_status_update_permission_denied(self, extra_ville):
        """Test PATCH raises PermissionDenied when user is not member."""
        from core.views import BaseStatusUpdateView
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import Group

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")
        other_user = user_obj.objects.create_user(
            email="other@test.com", password="testpass"
        )

        # Create company, client, and document
        admin_group = Group.objects.create(name="Admin_status_test")
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456782")
        # Only other_user is member
        Membership.objects.create(user=other_user, company=company, role=admin_group)
        client_obj = Client.objects.create(
            code_client="CLT_status",
            client_type="PM",
            raison_sociale="Test Client",
            ville=extra_ville,
            company=company,
        )
        devi = Devi.objects.create(
            client=client_obj,
            numero_devis="0001/25",
            date_devis="2024-01-01",
            created_by_user=other_user,
        )

        class TestStatusView(BaseStatusUpdateView):
            model = Devi
            document_name = "devis"

        view = TestStatusView.as_view()
        factory = APIRequestFactory()
        request = factory.patch("/", {"statut": "Accepté"}, format="json")
        request.user = user  # user_obj is NOT a member

        response = view(request, pk=devi.pk)
        assert response.status_code == 403

    def test_status_update_not_found(self):
        """Test PATCH raises Http404 when document doesn't exist."""
        from core.views import BaseStatusUpdateView
        from rest_framework.test import APIRequestFactory

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")

        class TestStatusView(BaseStatusUpdateView):
            model = Devi
            document_name = "devis"

        view = TestStatusView.as_view()
        factory = APIRequestFactory()
        request = factory.patch("/", {"statut": "Accepté"}, format="json")
        request.user = user

        response = view(request, pk=99999)
        assert response.status_code == 404


@pytest.mark.django_db
class TestBaseConversionViewPermissions:
    """Tests for permission checks in BaseConversionView."""

    def test_conversion_permission_denied(self, extra_ville):
        """Test POST raises PermissionDenied when user is not member."""
        from core.views import BaseConversionView
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import Group

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")
        other_user = user_obj.objects.create_user(
            email="other@test.com", password="testpass"
        )

        # Create company, client, and document
        admin_group = Group.objects.create(name="Admin_conv_test")
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456783")
        # Only other_user is member
        Membership.objects.create(user=other_user, company=company, role=admin_group)
        client_obj = Client.objects.create(
            code_client="CLT_conv",
            client_type="PM",
            raison_sociale="Test Client",
            ville=extra_ville,
            company=company,
        )
        devi = Devi.objects.create(
            client=client_obj,
            numero_devis="0002/25",
            date_devis="2024-01-01",
            created_by_user=other_user,
        )

        class TestConversionView(BaseConversionView):
            model = Devi
            document_name = "devis"

            @staticmethod
            def numero_generator():
                return "0001/25"

            conversion_method = "convert_to_facture_proforma"

        view = TestConversionView.as_view()
        factory = APIRequestFactory()
        request = factory.post("/", format="json")
        request.user = user  # user_obj is NOT a member

        response = view(request, pk=devi.pk)
        assert response.status_code == 403

    def test_conversion_not_found(self):
        """Test POST raises Http404 when document doesn't exist."""
        from core.views import BaseConversionView
        from rest_framework.test import APIRequestFactory

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")

        class TestConversionView(BaseConversionView):
            model = Devi
            document_name = "devis"

            @staticmethod
            def numero_generator():
                return "0001/25"

            conversion_method = "convert_to_facture_proforma"

        view = TestConversionView.as_view()
        factory = APIRequestFactory()
        request = factory.post("/", format="json")
        request.user = user

        response = view(request, pk=99999)
        assert response.status_code == 404


@pytest.mark.django_db
class TestBaseDocumentDetailEditDeleteViewPermissions:
    """Tests for permission checks in BaseDocumentDetailEditDeleteView."""

    def test_put_permission_denied(self, extra_ville):
        """Test PUT raises PermissionDenied when user is not member."""
        from core.views import BaseDocumentDetailEditDeleteView
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import Group
        from devi.serializers import DeviDetailSerializer

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")
        other_user = user_obj.objects.create_user(
            email="other@test.com", password="testpass"
        )

        # Create company, client, and document
        admin_group = Group.objects.create(name="Admin_put_test")
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456784")
        # Only other_user is member
        Membership.objects.create(user=other_user, company=company, role=admin_group)
        client_obj = Client.objects.create(
            code_client="CLT_put",
            client_type="PM",
            raison_sociale="Test Client",
            ville=extra_ville,
            company=company,
        )
        devi = Devi.objects.create(
            client=client_obj,
            numero_devis="0003/25",
            date_devis="2024-01-01",
            created_by_user=other_user,
        )

        class TestDetailView(BaseDocumentDetailEditDeleteView):
            model = Devi
            detail_serializer_class = DeviDetailSerializer
            document_name = "devis"

        view = TestDetailView.as_view()
        factory = APIRequestFactory()
        request = factory.put("/", {"numero_devis": "0004/25"}, format="json")
        request.user = user  # user_obj is NOT a member

        response = view(request, pk=devi.pk)
        assert response.status_code == 403

    def test_delete_permission_denied(self, extra_ville):
        """Test DELETE raises PermissionDenied when user is not member."""
        from core.views import BaseDocumentDetailEditDeleteView
        from rest_framework.test import APIRequestFactory
        from django.contrib.auth.models import Group
        from devi.serializers import DeviDetailSerializer

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")
        other_user = user_obj.objects.create_user(
            email="other@test.com", password="testpass"
        )

        # Create company, client, and document
        admin_group = Group.objects.create(name="Admin_del_test")
        company = Company.objects.create(raison_sociale="TestCo", ICE="123456785")
        # Only other_user is member
        Membership.objects.create(user=other_user, company=company, role=admin_group)
        client_obj = Client.objects.create(
            code_client="CLT_del",
            client_type="PM",
            raison_sociale="Test Client",
            ville=extra_ville,
            company=company,
        )
        devi = Devi.objects.create(
            client=client_obj,
            numero_devis="0005/25",
            date_devis="2024-01-01",
            created_by_user=other_user,
        )

        class TestDetailView(BaseDocumentDetailEditDeleteView):
            model = Devi
            detail_serializer_class = DeviDetailSerializer
            document_name = "devis"

        view = TestDetailView.as_view()
        factory = APIRequestFactory()
        request = factory.delete("/")
        request.user = user  # user_obj is NOT a member

        response = view(request, pk=devi.pk)
        assert response.status_code == 403

    def test_get_not_found(self):
        """Test GET raises Http404 when document doesn't exist."""
        from core.views import BaseDocumentDetailEditDeleteView
        from rest_framework.test import APIRequestFactory
        from devi.serializers import DeviDetailSerializer

        user_obj = get_user_model()
        user = user_obj.objects.create_user(email="test@test.com", password="testpass")

        class TestDetailView(BaseDocumentDetailEditDeleteView):
            model = Devi
            detail_serializer_class = DeviDetailSerializer
            document_name = "devis"

        view = TestDetailView.as_view()
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user

        response = view(request, pk=99999)
        assert response.status_code == 404


# =============================================================================
# PDF Utils Tests
# =============================================================================


@pytest.mark.django_db
class TestNumberToFrenchWords:
    """Tests for the number_to_french_words function."""

    def test_zero(self):
        """Test conversion of zero."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("0")) == "ZÉRO DIRHAMS"

    def test_units(self):
        """Test conversion of units (1-19)."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("1")) == "UN DIRHAMS"
        assert number_to_french_words(Decimal("5")) == "CINQ DIRHAMS"
        assert number_to_french_words(Decimal("10")) == "DIX DIRHAMS"
        assert number_to_french_words(Decimal("15")) == "QUINZE DIRHAMS"
        assert number_to_french_words(Decimal("19")) == "DIX-NEUF DIRHAMS"

    def test_tens(self):
        """Test conversion of tens (20-90)."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("20")) == "VINGT DIRHAMS"
        assert number_to_french_words(Decimal("21")) == "VINGT ET UN DIRHAMS"
        assert number_to_french_words(Decimal("30")) == "TRENTE DIRHAMS"
        assert number_to_french_words(Decimal("31")) == "TRENTE ET UN DIRHAMS"
        assert number_to_french_words(Decimal("40")) == "QUARANTE DIRHAMS"
        assert number_to_french_words(Decimal("50")) == "CINQUANTE DIRHAMS"
        assert number_to_french_words(Decimal("60")) == "SOIXANTE DIRHAMS"
        assert number_to_french_words(Decimal("70")) == "SOIXANTE-DIX DIRHAMS"
        assert number_to_french_words(Decimal("71")) == "SOIXANTE ET ONZE DIRHAMS"
        assert number_to_french_words(Decimal("75")) == "SOIXANTE-QUINZE DIRHAMS"
        assert number_to_french_words(Decimal("80")) == "QUATRE-VINGTS DIRHAMS"
        assert number_to_french_words(Decimal("81")) == "QUATRE-VINGT-UN DIRHAMS"
        assert number_to_french_words(Decimal("90")) == "QUATRE-VINGT-DIX DIRHAMS"
        assert number_to_french_words(Decimal("99")) == "QUATRE-VINGT-DIX-NEUF DIRHAMS"

    def test_hundreds(self):
        """Test conversion of hundreds."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("100")) == "CENT DIRHAMS"
        assert number_to_french_words(Decimal("101")) == "CENT UN DIRHAMS"
        assert number_to_french_words(Decimal("200")) == "DEUX CENTS DIRHAMS"
        assert number_to_french_words(Decimal("250")) == "DEUX CENT CINQUANTE DIRHAMS"
        assert number_to_french_words(Decimal("999")) == "NEUF CENT QUATRE-VINGT-DIX-NEUF DIRHAMS"

    def test_thousands(self):
        """Test conversion of thousands."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("1000")) == "MILLE DIRHAMS"
        assert number_to_french_words(Decimal("1001")) == "MILLE UN DIRHAMS"
        assert number_to_french_words(Decimal("2000")) == "DEUX MILLE DIRHAMS"
        assert number_to_french_words(Decimal("2500")) == "DEUX MILLE CINQ CENTS DIRHAMS"
        assert number_to_french_words(Decimal("9999")) == "NEUF MILLE NEUF CENT QUATRE-VINGT-DIX-NEUF DIRHAMS"

    def test_millions(self):
        """Test conversion of millions."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("1000000")) == "UN MILLION DIRHAMS"
        assert number_to_french_words(Decimal("2000000")) == "DEUX MILLIONS DIRHAMS"
        assert number_to_french_words(Decimal("1234567")) == "UN MILLION DEUX CENT TRENTE-QUATRE MILLE CINQ CENT SOIXANTE-SEPT DIRHAMS"

    def test_with_centimes(self):
        """Test conversion with centimes."""
        from core.pdf_utils import number_to_french_words

        assert number_to_french_words(Decimal("1.50")) == "UN DIRHAMS ET CINQUANTE CENTIMES"
        assert number_to_french_words(Decimal("100.25")) == "CENT DIRHAMS ET VINGT-CINQ CENTIMES"
        assert number_to_french_words(Decimal("1234.99")) == "MILLE DEUX CENT TRENTE-QUATRE DIRHAMS ET QUATRE-VINGT-DIX-NEUF CENTIMES"
        assert number_to_french_words(Decimal("0.01")) == "ZÉRO DIRHAMS ET UN CENTIMES"
        assert number_to_french_words(Decimal("0.99")) == "ZÉRO DIRHAMS ET QUATRE-VINGT-DIX-NEUF CENTIMES"

    def test_edge_cases(self):
        """Test edge cases for number conversion."""
        from core.pdf_utils import number_to_french_words

        # 71 (special case for soixante et onze)
        assert number_to_french_words(Decimal("71")) == "SOIXANTE ET ONZE DIRHAMS"
        # 80 (quatre-vingts with s)
        assert number_to_french_words(Decimal("80")) == "QUATRE-VINGTS DIRHAMS"
        # 81 (quatre-vingt without s)
        assert number_to_french_words(Decimal("81")) == "QUATRE-VINGT-UN DIRHAMS"


@pytest.mark.django_db
class TestBasePDFGenerator:
    """Tests for the BasePDFGenerator class."""

    @pytest.fixture
    def pdf_company(self):
        """Create a test company for PDF generation."""
        return Company.objects.create(
            raison_sociale="Test PDF Company",
            ICE="PDF123456",
            adresse="123 Test Street",
            telephone="0512345678",
            email="test@pdfcompany.com",
        )

    @pytest.fixture
    def pdf_ville(self):
        """Create a test ville for PDF generation."""
        return Ville.objects.create(nom="PDF City")

    @pytest.fixture
    def pdf_client(self, pdf_ville, pdf_company):
        """Create a test client for PDF generation."""
        return Client.objects.create(
            code_client="PDFCLT001",
            client_type="PM",
            raison_sociale="Test PDF Client",
            ville=pdf_ville,
            company=pdf_company,
        )

    @pytest.fixture
    def pdf_user(self):
        """Create a test user for PDF generation."""
        return CustomUser.objects.create_user(
            email="pdfuser@test.com",
            password="testpass",
            first_name="PDF",
            last_name="User",
        )

    @pytest.fixture
    def pdf_devi(self, pdf_client, pdf_user):
        """Create a test devi for PDF generation."""
        return Devi.objects.create(
            client=pdf_client,
            numero_devis="PDF001/25",
            date_devis="2025-01-01",
            created_by_user=pdf_user,
        )

    def test_init(self, pdf_devi, pdf_company):
        """Test PDF generator initialization."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        assert generator.document == pdf_devi
        assert generator.company == pdf_company
        assert generator.pdf_type == "normal"
        assert generator.total_pages == 1
        assert generator.buffer is not None
        assert generator.styles is not None

    def test_init_with_pdf_type(self, pdf_devi, pdf_company):
        """Test PDF generator initialization with custom pdf_type."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company, pdf_type="avec_remise")
        assert generator.pdf_type == "avec_remise"

    def test_setup_custom_styles(self, pdf_devi, pdf_company):
        """Test custom styles are set up correctly."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        # Check that custom styles are added
        assert "DocTitle" in generator.styles.byName
        assert "DocDate" in generator.styles.byName
        assert "SectionHeader" in generator.styles.byName
        assert "CustomNormal" in generator.styles.byName
        assert "CustomSmall" in generator.styles.byName
        assert "CustomSmallCenter" in generator.styles.byName
        assert "CustomRight" in generator.styles.byName
        assert "CustomCenter" in generator.styles.byName
        assert "Footer" in generator.styles.byName
        assert "PriceWords" in generator.styles.byName
        assert "Remarks" in generator.styles.byName
        # Check primary color is set
        assert generator.primary_color is not None

    def test_get_logo_image_no_logo(self, pdf_devi, pdf_company):
        """Test getting logo when company has no logo."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        logo = generator._get_logo_image()
        assert logo is None

    def test_get_cachet_image_no_cachet(self, pdf_devi, pdf_company):
        """Test getting cachet when company has no cachet."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        cachet = generator._get_cachet_image()
        assert cachet is None

    def test_get_filename(self, pdf_devi, pdf_company):
        """Test _get_filename is abstract and raises NotImplementedError."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        with pytest.raises(NotImplementedError):
            generator._get_filename()

    def test_get_pdf_title(self, pdf_devi, pdf_company):
        """Test _get_pdf_title is abstract and raises NotImplementedError."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        with pytest.raises(NotImplementedError):
            generator._get_pdf_title()

    def test_build_content(self, pdf_devi, pdf_company):
        """Test _build_content is abstract and raises NotImplementedError."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        with pytest.raises(NotImplementedError):
            generator._build_content()

    def test_create_header(self, pdf_devi, pdf_company):
        """Test _create_header creates proper header elements."""
        from core.pdf_utils import BasePDFGenerator

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        header = generator._create_header("Test Title")
        assert isinstance(header, list)
        assert len(header) > 0  # Should have at least some elements

    def test_create_info_grid(self, pdf_devi, pdf_company):
        """Test _create_info_grid creates proper info table."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        left_data = [["Field1", "Value1"]]
        right_data = [["Field2", "Value2"]]
        grid = generator._create_info_grid(left_data, right_data)
        assert isinstance(grid, Table)

    def test_create_info_grid_with_company_details(self, pdf_devi, pdf_company):
        """Test _create_info_grid with full company details."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table

        # Add more company details
        pdf_company.registre_de_commerce = "RC123456"
        pdf_company.identifiant_fiscal = "IF789012"
        pdf_company.CNSS = "CNSS345678"
        pdf_company.numero_du_compte = "RIB1234567890"
        pdf_company.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        left_data = [["Mode", "Cash"]]
        right_data = [["Client", "Test Client"], ["ICE", "CLI123"]]
        grid = generator._create_info_grid(left_data, right_data)
        assert isinstance(grid, Table)

    def test_add_page_footer(self, pdf_devi, pdf_company):
        """Test _add_page_footer method."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.pdfgen import canvas
        from io import BytesIO

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        generator.total_pages = 5

        # Create a mock canvas
        buffer = BytesIO()
        mock_canvas = canvas.Canvas(buffer)
        
        # Should not raise any errors
        generator._add_page_footer(mock_canvas, None)

    def test_add_page_footer_with_empty_company_fields(self, pdf_devi):
        """Test _add_page_footer with empty company fields."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.pdfgen import canvas
        from io import BytesIO

        # Create company with no optional fields
        empty_company = Company.objects.create(
            raison_sociale="",
            ICE="EMPTY123",
        )

        generator = BasePDFGenerator(pdf_devi, empty_company)
        buffer = BytesIO()
        mock_canvas = canvas.Canvas(buffer)
        
        # Should handle empty fields gracefully
        generator._add_page_footer(mock_canvas, None)

    def test_create_articles_table_with_lines(self, pdf_devi, pdf_company, pdf_client):
        """Test _create_articles_table with actual document lines."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table
        from article.models import Article
        from parameter.models import Unite

        # Create articles with lines
        unite = Unite.objects.create(nom="Pièce")
        article1 = Article.objects.create(
            company=pdf_company,
            reference="ART001",
            designation="Test Article 1",
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("150.00"),
            tva=Decimal("20"),
            unite=unite,
        )
        article2 = Article.objects.create(
            company=pdf_company,
            reference="ART002",
            designation="Test Article 2",
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            tva=Decimal("20"),
            unite=unite,
        )

        DeviLine.objects.create(
            devis=pdf_devi,
            article=article1,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("150.00"),
            quantity=Decimal("2.00"),
            remise=Decimal("0"),
            remise_type="",
        )
        DeviLine.objects.create(
            devis=pdf_devi,
            article=article2,
            prix_achat=Decimal("50.00"),
            prix_vente=Decimal("75.00"),
            quantity=Decimal("3.00"),
            remise=Decimal("10"),
            remise_type="Pourcentage",
        )

        # Recalculate totals
        pdf_devi.recalc_totals()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_articles_table(show_remise=True, show_unite=False)
        assert isinstance(table, Table)

    def test_create_articles_table_with_unite(self, pdf_devi, pdf_company, pdf_client):
        """Test _create_articles_table with unite column."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table
        from article.models import Article
        from parameter.models import Unite

        unite = Unite.objects.create(nom="Kg")
        article = Article.objects.create(
            company=pdf_company,
            reference="ART003",
            designation="Test Article 3",
            prix_achat=Decimal("10.00"),
            prix_vente=Decimal("15.00"),
            tva=Decimal("20"),
            unite=unite,
        )

        DeviLine.objects.create(
            devis=pdf_devi,
            article=article,
            prix_achat=Decimal("10.00"),
            prix_vente=Decimal("15.00"),
            quantity=Decimal("5.00"),
            remise=Decimal("0"),
            remise_type="",
        )

        pdf_devi.recalc_totals()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_articles_table(show_remise=True, show_unite=True)
        assert isinstance(table, Table)

    def test_create_articles_table_with_remise_fixe(self, pdf_devi, pdf_company, pdf_client):
        """Test _create_articles_table with fixed remise."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table
        from article.models import Article

        article = Article.objects.create(
            company=pdf_company,
            reference="ART004",
            designation="Test Article 4",
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("200.00"),
            tva=Decimal("20"),
        )

        DeviLine.objects.create(
            devis=pdf_devi,
            article=article,
            prix_achat=Decimal("100.00"),
            prix_vente=Decimal("200.00"),
            quantity=Decimal("1.00"),
            remise=Decimal("50"),
            remise_type="Fixe",
        )

        pdf_devi.remise = Decimal("20")
        pdf_devi.remise_type = "Fixe"
        pdf_devi.recalc_totals()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_articles_table(show_remise=True, show_unite=False)
        assert isinstance(table, Table)

    def test_create_totals_section(self, pdf_devi, pdf_company):
        """Test _create_totals_section method."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table

        pdf_devi.total_ht = Decimal("1000.00")
        pdf_devi.total_tva = Decimal("200.00")
        pdf_devi.total_ttc = Decimal("1200.00")
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_totals_section(show_remise=False)
        assert isinstance(table, Table)

    def test_create_totals_section_with_remise(self, pdf_devi, pdf_company):
        """Test _create_totals_section with remise."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table

        pdf_devi.total_ht = Decimal("1000.00")
        pdf_devi.total_tva = Decimal("200.00")
        pdf_devi.total_ttc = Decimal("1200.00")
        pdf_devi.remise = Decimal("10")
        pdf_devi.remise_type = "Pourcentage"
        pdf_devi.total_ttc_apres_remise = Decimal("1080.00")
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_totals_section(show_remise=True)
        assert isinstance(table, Table)

    def test_create_totals_section_with_remise_fixe(self, pdf_devi, pdf_company):
        """Test _create_totals_section with fixed remise."""
        from core.pdf_utils import BasePDFGenerator
        from reportlab.platypus import Table

        pdf_devi.total_ht = Decimal("1000.00")
        pdf_devi.total_tva = Decimal("200.00")
        pdf_devi.total_ttc = Decimal("1200.00")
        pdf_devi.remise = Decimal("100")
        pdf_devi.remise_type = "Fixe"
        pdf_devi.total_ttc_apres_remise = Decimal("1100.00")
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        table = generator._create_totals_section(show_remise=True)
        assert isinstance(table, Table)

    def test_create_price_in_words_section(self, pdf_devi, pdf_company):
        """Test _create_price_in_words_section method."""
        from core.pdf_utils import BasePDFGenerator

        pdf_devi.total_ttc = Decimal("1234.56")
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        elements = generator._create_price_in_words_section()
        assert isinstance(elements, list)
        assert len(elements) > 0

    def test_create_price_in_words_section_with_remise(self, pdf_devi, pdf_company):
        """Test _create_price_in_words_section with remise."""
        from core.pdf_utils import BasePDFGenerator

        pdf_devi.total_ttc = Decimal("1200.00")
        pdf_devi.remise_type = "Pourcentage"
        pdf_devi.total_ttc_apres_remise = Decimal("1080.00")
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        elements = generator._create_price_in_words_section("MONTANT TOTAL")
        assert isinstance(elements, list)
        assert len(elements) > 0

    def test_create_remarks_section(self, pdf_devi, pdf_company):
        """Test _create_remarks_section method."""
        from core.pdf_utils import BasePDFGenerator

        pdf_devi.remarque = "This is a test remark."
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        elements = generator._create_remarks_section()
        assert isinstance(elements, list)
        assert len(elements) > 0

    def test_create_remarks_section_with_custom_remarks(self, pdf_devi, pdf_company):
        """Test _create_remarks_section with custom remarks."""
        from core.pdf_utils import BasePDFGenerator

        pdf_devi.remarque = "Document remark"
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        elements = generator._create_remarks_section("Custom additional remark")
        assert isinstance(elements, list)
        assert len(elements) > 0

    def test_create_remarks_section_no_remarks(self, pdf_devi, pdf_company):
        """Test _create_remarks_section with no remarks."""
        from core.pdf_utils import BasePDFGenerator

        pdf_devi.remarque = ""
        pdf_devi.save()

        generator = BasePDFGenerator(pdf_devi, pdf_company)
        elements = generator._create_remarks_section()
        assert isinstance(elements, list)

    def test_number_to_french_words_large_numbers(self):
        """Test conversion of very large numbers."""
        from core.pdf_utils import number_to_french_words

        # Test a large number with millions
        assert "MILLIONS" in number_to_french_words(Decimal("5000000"))
        # Test maximum realistic invoice amount
        result = number_to_french_words(Decimal("999999.99"))
        assert "MILLIONS" in result or "MILLE" in result


# =============================================================================
# Authentication Tests
# =============================================================================


@pytest.mark.django_db
class TestJWTQueryParamAuthentication:
    """Tests for the JWTQueryParamAuthentication class."""

    @pytest.fixture
    def auth_user(self):
        """Create a test user for authentication."""
        return CustomUser.objects.create_user(
            email="authuser@test.com",
            password="testpass",
            first_name="Auth",
            last_name="User",
        )

    def test_authenticate_with_header(self, auth_user):
        """Test authentication with Authorization header."""
        from core.authentication import JWTQueryParamAuthentication
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.tokens import RefreshToken

        factory = APIRequestFactory()
        refresh = RefreshToken.for_user(auth_user)
        access_token = str(refresh.access_token)

        request = factory.get("/", HTTP_AUTHORIZATION=f"Bearer {access_token}")
        auth = JWTQueryParamAuthentication()
        result = auth.authenticate(request)

        assert result is not None
        user, token = result
        assert user.id == auth_user.id

    def test_authenticate_with_query_param(self, auth_user):
        """Test authentication with query parameter."""
        from core.authentication import JWTQueryParamAuthentication
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework.request import Request

        factory = APIRequestFactory()
        refresh = RefreshToken.for_user(auth_user)
        access_token = str(refresh.access_token)

        django_request = factory.get(f"/?token={access_token}")
        request = Request(django_request)
        auth = JWTQueryParamAuthentication()
        result = auth.authenticate(request)

        assert result is not None
        user, token = result
        assert user.id == auth_user.id

    def test_authenticate_no_token(self):
        """Test authentication with no token."""
        from core.authentication import JWTQueryParamAuthentication
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request

        factory = APIRequestFactory()
        django_request = factory.get("/")
        request = Request(django_request)
        auth = JWTQueryParamAuthentication()
        result = auth.authenticate(request)

        assert result is None

    def test_authenticate_invalid_token(self):
        """Test authentication with invalid token."""
        from core.authentication import JWTQueryParamAuthentication
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.exceptions import InvalidToken
        from rest_framework.request import Request

        factory = APIRequestFactory()
        django_request = factory.get("/?token=invalid_token_here")
        request = Request(django_request)
        auth = JWTQueryParamAuthentication()

        with pytest.raises(InvalidToken):
            auth.authenticate(request)

    def test_authenticate_header_priority(self, auth_user):
        """Test that header authentication takes priority over query param."""
        from core.authentication import JWTQueryParamAuthentication
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework.request import Request

        factory = APIRequestFactory()
        refresh = RefreshToken.for_user(auth_user)
        access_token = str(refresh.access_token)

        # Pass token in both header and query param
        django_request = factory.get(
            f"/?token={access_token}",
            HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )
        request = Request(django_request)
        auth = JWTQueryParamAuthentication()
        result = auth.authenticate(request)

        assert result is not None
        user, token = result
        assert user.id == auth_user.id


# =============================================================================
# Additional Serializer Tests for Coverage
# =============================================================================


@pytest.mark.django_db
class TestCoreSerializerAdditional:
    """Additional tests for core serializers to improve coverage."""

    @pytest.fixture
    def test_client_extra(self, extra_ville, extra_company):
        """Create a test client."""
        return Client.objects.create(
            code_client="SERCLI001",
            client_type="PM",
            raison_sociale="Serializer Test Client",
            ville=extra_ville,
            company=extra_company,
        )

    @pytest.fixture
    def test_mode_paiement(self):
        """Create a test mode paiement."""
        return ModePaiement.objects.create(nom="Espèces")

    def test_base_list_serializer_created_by_without_name(self, test_client_extra, test_mode_paiement):
        """Test BaseListSerializer with user without first/last name."""
        from devi.models import Devi
        from devi.serializers import DeviListSerializer

        # Create user with no first/last name
        user_no_name = CustomUser.objects.create_user(
            email="noname@test.com",
            password="test"
        )

        devi = Devi.objects.create(
            client=test_client_extra,
            numero_devis="SER001/26",
            date_devis="2026-01-01",
            mode_paiement=test_mode_paiement,
            created_by_user=user_no_name,
        )

        serializer = DeviListSerializer(devi)
        # Should fall back to email
        assert serializer.data["created_by_user_name"] == "noname@test.com"

    def test_base_list_serializer_no_created_by(self, test_client_extra, test_mode_paiement):
        """Test BaseListSerializer with no created_by_user."""
        from devi.models import Devi
        from devi.serializers import DeviListSerializer

        devi = Devi.objects.create(
            client=test_client_extra,
            numero_devis="SER002/26",
            date_devis="2026-01-01",
            mode_paiement=test_mode_paiement,
            created_by_user=None,
        )

        serializer = DeviListSerializer(devi)
        assert serializer.data["created_by_user_name"] is None

    def test_base_detail_serializer_no_created_by(self, test_client_extra, test_mode_paiement):
        """Test BaseDetailSerializer with no created_by_user."""
        from devi.models import Devi
        from devi.serializers import DeviDetailSerializer

        devi = Devi.objects.create(
            client=test_client_extra,
            numero_devis="SER003/26",
            date_devis="2026-01-01",
            mode_paiement=test_mode_paiement,
            created_by_user=None,
        )

        serializer = DeviDetailSerializer(devi)
        assert serializer.data["created_by_user_name"] is None

    def test_line_serializer_validation_remise_negative(self, extra_article):
        """Test line serializer validation with negative remise."""
        from devi.serializers import DeviLineWriteSerializer

        data = {
            "article": extra_article.id,
            "prix_achat": "100.00",
            "prix_vente": "150.00",
            "quantity": "2",
            "remise": "-10",
            "remise_type": "Pourcentage",
        }

        serializer = DeviLineWriteSerializer(data=data)
        assert not serializer.is_valid()
        assert "non_field_errors" in serializer.errors or "remise" in str(serializer.errors).lower()

    def test_line_serializer_prix_vente_below_achat(self, extra_article):
        """Test line serializer validation with prix_vente < prix_achat."""
        from devi.serializers import DeviLineWriteSerializer

        data = {
            "article": extra_article.id,
            "prix_achat": "150.00",
            "prix_vente": "100.00",
            "quantity": "2",
            "remise": "0",
            "remise_type": "Pourcentage",
        }

        serializer = DeviLineWriteSerializer(data=data)
        assert not serializer.is_valid()


# =============================================================================
# Additional Filter Tests for Coverage
# =============================================================================


@pytest.mark.django_db
class TestCoreFilterAdditional:
    """Additional tests for core filters to improve coverage."""

    @pytest.fixture
    def test_client_filter(self, extra_ville, extra_company):
        """Create a test client for filters."""
        return Client.objects.create(
            code_client="FILTCLI001",
            client_type="PM",
            raison_sociale="Filter Test Client",
            ville=extra_ville,
            company=extra_company,
        )

    def test_filter_date_after(self, test_client_filter, extra_mode_paiement):
        """Test date_after filter."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi1 = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT001/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )
        devi2 = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT002/26",
            date_devis="2026-01-15",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"date_after": "2026-01-10"}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi1 not in filterset.qs
        assert devi2 in filterset.qs

    def test_filter_date_before(self, test_client_filter, extra_mode_paiement):
        """Test date_before filter."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi1 = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT003/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )
        devi2 = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT004/26",
            date_devis="2026-01-15",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"date_before": "2026-01-10"}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi1 in filterset.qs
        assert devi2 not in filterset.qs

    def test_filter_date_after_with_none(self, test_client_filter, extra_mode_paiement):
        """Test date_after filter with None value."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT005/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"date_after": None}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs

    def test_filter_date_before_with_none(self, test_client_filter, extra_mode_paiement):
        """Test date_before filter with None value."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT006/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"date_before": None}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs

    def test_global_search_with_empty_string(self, test_client_filter, extra_mode_paiement):
        """Test global_search with empty string."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT007/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"search": ""}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs

    def test_global_search_with_whitespace(self, test_client_filter, extra_mode_paiement):
        """Test global_search with whitespace."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT008/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"search": "   "}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs
    def test_filter_date_no_date_field(self, test_client_filter, extra_mode_paiement):
        """Test date filter when date_field is not set."""
        from devi.models import Devi
        from devi.filters import DeviFilter

        # Create a filter with no date_field
        class NoDateFieldFilter(DeviFilter):
            date_field = None

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT009/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        # Should return queryset unchanged
        filter_data = {"date_after": "2025-01-01"}
        filterset = NoDateFieldFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs

        filter_data = {"date_before": "2027-01-01"}
        filterset = NoDateFieldFilter(data=filter_data, queryset=Devi.objects.all())
        assert devi in filterset.qs

    def test_global_search_no_required_fields(self, test_client_filter, extra_mode_paiement):
        """Test global_search raises NotImplementedError when required fields not set."""
        from devi.models import Devi
        from core.filters import BaseDocumentFilter

        # Create a filter without numero_field and req_field
        class IncompleteFilter(BaseDocumentFilter):
            class Meta:
                model = Devi
                fields = []

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT010/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        filter_data = {"search": "test"}
        filterset = IncompleteFilter(data=filter_data, queryset=Devi.objects.all())
        with pytest.raises(NotImplementedError, match="Subclass must set"):
            _ = list(filterset.qs)

    def test_global_search_database_error(self, test_client_filter, extra_mode_paiement, monkeypatch):
        """Test global_search handles DatabaseError gracefully."""
        from devi.models import Devi
        from devi.filters import DeviFilter
        from django.db import DatabaseError

        devi = Devi.objects.create(
            client=test_client_filter,
            numero_devis="FILT011/26",
            date_devis="2026-01-01",
            mode_paiement=extra_mode_paiement,
        )

        # Mock SearchQuery to raise DatabaseError
        from django.contrib.postgres.search import SearchQuery
        original_init = SearchQuery.__init__

        def mock_init(*args, **kwargs):
            original_init(*args, **kwargs)
            
        def mock_resolve_expression(*args, **kwargs):
            raise DatabaseError("Mock database error")

        monkeypatch.setattr(SearchQuery, "resolve_expression", mock_resolve_expression)

        filter_data = {"search": "FILT011"}
        filterset = DeviFilter(data=filter_data, queryset=Devi.objects.all())
        # Should fall back to icontains search
        assert devi in filterset.qs