"""Assistant reads supplier-only dossiers without weakening company isolation."""

import json
import re
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from article.models import Article
from logistique.models import LogisticsOrder, LogisticsOrderLine
from parameter.models import Emplacement
from stock.models import StockReceipt, StockReceiptLine

from . import operations
from .tests import assert_code, executor, setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def supplier_records(setup):
    article = Article.objects.get(company=setup.a, reference="SYNTH-ITEM")
    location = Emplacement.objects.create(company=setup.a, nom="Supplier warehouse")
    foreign_location = Emplacement.objects.create(
        company=setup.b, nom="PRIVATE_WAREHOUSE"
    )
    foreign_article = Article.objects.create(
        company=setup.b,
        reference="PRIVATE_PRODUCT",
        designation="PRIVATE_DESIGNATION",
        prix_achat=1,
        prix_vente=2,
        tva=0,
    )
    order = LogisticsOrder.objects.create(
        company=setup.a,
        workflow_version=2,
        numero_commande="PURCHASE-ONLY",
        fournisseur="Supplier purchase",
        created_by_user=setup.user,
        statut="Proforma",
        statut_commande_lancement="Terminée",
    )
    line = LogisticsOrderLine.objects.create(
        commande=order,
        article=article,
        expected_emplacement=location,
        quantity=3,
        prix_achat=80,
    )
    foreign_order = LogisticsOrder.objects.create(
        company=setup.b,
        workflow_version=2,
        numero_commande="PRIVATE_ORDER",
        fournisseur="PRIVATE_SUPPLIER",
        created_by_user=setup.other,
    )
    return SimpleNamespace(
        order=order,
        line=line,
        article=article,
        location=location,
        foreign_order=foreign_order,
        foreign_article=foreign_article,
        foreign_location=foreign_location,
    )


def test_supplier_only_dossier_search_detail_are_read_only(setup, supplier_records):
    records = supplier_records
    ex = executor(setup)
    with CaptureQueriesContext(connection) as queries:
        listed = operations.search(ex, "logistics_order")
        detailed = operations.detail(ex, "logistics_order", records.order.pk)
    assert [item["id"] for item in listed["items"]] == [records.order.pk]
    (item,) = detailed["items"]
    assert item["lines"][0]["reference"] == records.article.reference
    assert item["lines"][0]["client"] in (None, "")
    assert item["lines"][0]["quantity"] == "3.000"
    assert "PRIVATE_" not in json.dumps([listed, detailed])
    assert not any(
        re.match(r"\s*(INSERT|UPDATE|DELETE|ALTER|CREATE)\b", entry["sql"], re.I)
        for entry in queries
    )


def test_foreign_supplier_dossier_cannot_be_opened(setup, supplier_records):
    assert_code(
        "NOT_FOUND",
        lambda: operations.detail(
            executor(setup), "logistics_order", supplier_records.foreign_order.pk
        ),
    )


@pytest.mark.parametrize(
    "invalid_link", ["article", "expected_emplacement", "client", "workflow_version"]
)
def test_supplier_null_sales_links_do_not_allow_cross_company_data(
    setup, supplier_records, invalid_link
):
    records = supplier_records
    if invalid_link == "article":
        records.line.article = records.foreign_article
    elif invalid_link == "expected_emplacement":
        records.line.expected_emplacement = records.foreign_location
    elif invalid_link == "client":
        records.line.client = setup.restricted.client
    else:
        records.order.workflow_version = 1
        records.order.save()
    records.line.save()
    assert operations.search(executor(setup), "logistics_order")["items"] == []
    assert_code(
        "NOT_FOUND",
        lambda: operations.detail(executor(setup), "logistics_order", records.order.pk),
    )


def test_stock_receipt_with_supplier_only_lines_can_be_read(setup, supplier_records):
    records = supplier_records
    receipt = StockReceipt.objects.create(
        company=setup.a,
        logistics_order=records.order,
        reference="SUPPLIER-RECEIPT",
        created_by=setup.user,
    )
    StockReceiptLine.objects.create(
        receipt=receipt,
        logistics_line=records.line,
        article=records.article,
        emplacement=records.location,
        quantity=1,
    )
    result = operations.detail(executor(setup), "stock_receipt", receipt.pk)
    assert result["items"][0]["lines"][0]["reference"] == records.article.reference
