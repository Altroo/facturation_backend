from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from re import match
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Protocol
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


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
        assert isinstance(response.data, list)
        assert any(d["id"] == self.doc.id for d in response.data)

        item = next(d for d in response.data if d["id"] == self.doc.id)
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
