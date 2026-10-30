import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import Membership, Role
from article.models import Article
from company.models import Company
from logistique.models import LogisticsOrder, LogisticsOrderLine
from parameter.models import Emplacement
from stock.models import InventorySession, StockBalance, StockMovement, StockReceipt, StockReceiptLine

pytestmark = pytest.mark.django_db


@pytest.fixture
def lists(stock_context):
    ctx = stock_context
    user, company, location = ctx["user"], ctx["company"], ctx["emplacement"]
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(user=user, company=company, role=role)
    client = APIClient()
    client.force_authenticate(user)
    balances = [ctx["balance"]]
    for reference, physical, reserved in (("STOCK-002", 1, 0), ("STOCK-003", 0, 3)):
        article = Article.objects.create(company=company, emplacement=location, reference=reference, designation=reference, type_article="Produit", stock_minimum=2)
        balances.append(StockBalance.objects.create(company=company, article=article, emplacement=location, physical_quantity=physical, reserved_quantity=reserved))
    movements = [StockMovement.objects.create(balance=ctx["balance"], movement_type="adjustment", quantity=quantity, balance_after=10 + quantity, note=note, actor=user)
                 for quantity, note in ((5, "Opening"), (-1, "Correction"), (2, ""))]
    other_location = Emplacement.objects.create(company=company, nom="Autre dépôt")
    receipts, inventories = [], []
    for index, status in enumerate(("draft", "validated", "cancelled")):
        order = LogisticsOrder.objects.create(company=company, numero_commande=f"LOG-{index}", fournisseur="Supplier")
        receipt = StockReceipt.objects.create(company=company, logistics_order=order, status=status, reference=f"REC-{index}", note="" if index == 0 else "Note", created_by=user)
        for article in (ctx["article"], balances[1].article):
            line = LogisticsOrderLine.objects.create(commande=order, article=article, quantity=5, prix_achat=1, prix_vente=2)
            StockReceiptLine.objects.create(receipt=receipt, logistics_line=line, article=article, emplacement=location, quantity=1)
        receipts.append(receipt)
        inventories.append(InventorySession.objects.create(company=company, emplacement=location if index == 0 else other_location, status=status, reference=f"INV-{index}", created_by=user))
    # A foreign-company record must never enter a grouped filter result.
    foreign = Company.objects.create(raison_sociale="Foreign", ICE="FOREIGN-STOCK-FILTER")
    foreign_location = Emplacement.objects.create(company=foreign, nom="Foreign")
    foreign_article = Article.objects.create(company=foreign, emplacement=foreign_location, reference="STOCK-001-FOREIGN", designation="Foreign", type_article="Produit")
    StockBalance.objects.create(company=foreign, article=foreign_article, emplacement=foreign_location, physical_quantity=0)
    return {**ctx, "client_api": client, "balances": balances, "movements": movements, "receipts": receipts, "inventories": inventories, "other_location": other_location}


def get_list(ctx, endpoint, **params):
    return ctx["client_api"].get(f"/api/stock/{endpoint}/", {"company_id": ctx["company"].pk, "page_size": 50, **params})


@pytest.mark.parametrize("endpoint,ordering,collection,expected", [
    ("balances", "physical_quantity", "balances", [2, 1, 0]),
    ("movements", "quantity", "movements", [1, 2, 0]),
    ("receipts", "reference", "receipts", [0, 1, 2]),
    ("inventories", "reference", "inventories", [0, 1, 2]),
])
def test_ordering_is_applied_before_pagination(lists, endpoint, ordering, collection, expected):
    for descending in (False, True):
        response = get_list(lists, endpoint, ordering=("-" if descending else "") + ordering)
        assert response.status_code == 200, response.data
        indexes = list(reversed(expected)) if descending else expected
        assert [row["id"] for row in response.data["results"]] == [lists[collection][index].pk for index in indexes]
        pages = [get_list(lists, endpoint, ordering=("-" if descending else "") + ordering, page_size=1, page=page) for page in range(1, 4)]
        assert [page.data["results"][0]["id"] for page in pages] == [lists[collection][index].pk for index in indexes]


@pytest.mark.parametrize("endpoint,first,second,expected", [
    ("balances", {"physical_quantity__lt": "2"}, {"article_reference__icontains": "STOCK-001"}, 3),
    ("movements", {"quantity__lt": "0"}, {"note__icontains": "Opening"}, 2),
    ("receipts", {"status": "draft"}, {"reference__icontains": "REC-2"}, 2),
    ("inventories", {"status": "draft"}, {"reference__icontains": "INV-2"}, 2),
])
def test_filter_rows_are_ored_without_losing_company_scope(lists, endpoint, first, second, expected):
    response = get_list(lists, endpoint, filter_logic="or", filter_groups=json.dumps([first, second]))
    assert response.status_code == 200, response.data
    assert response.data["count"] == expected
    response = get_list(lists, endpoint, **first, **second)
    assert response.status_code == 200, response.data
    assert response.data["count"] == 0


def test_computed_stock_state_can_be_used_inside_or_groups(lists):
    response = get_list(lists, "balances", filter_logic="or", filter_groups=json.dumps([{"stock_state": "minimum"}, {"stock_state": "a_approvisionner"}]))
    assert response.status_code == 200, response.data
    assert {row["id"] for row in response.data["results"]} == {balance.pk for balance in lists["balances"][1:]}
    response = get_list(lists, "balances", stock_states="minimum,a_approvisionner")
    assert response.status_code == 200
    assert response.data["count"] == 2


def test_receipt_quick_filters_use_the_correct_relationship_and_return_unique_rows(lists):
    receipt = lists["receipts"][1]
    response = get_list(lists, "receipts", statuses="validated", logistics_order_ids=str(receipt.logistics_order_id), emplacement_ids=str(lists["emplacement"].pk))
    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["results"]] == [receipt.pk]


def test_inventory_quick_filters_are_not_ignored(lists):
    response = get_list(lists, "inventories", statuses="validated,cancelled", emplacement_ids=str(lists["other_location"].pk))
    assert response.status_code == 200, response.data
    assert {row["id"] for row in response.data["results"]} == {row.pk for row in lists["inventories"][1:]}
    response = get_list(lists, "inventories", statuses="validated", emplacement_ids=str(lists["emplacement"].pk))
    assert response.status_code == 200
    assert response.data["count"] == 0


def test_advanced_empty_text_and_numeric_filters(lists):
    response = get_list(lists, "movements", note__isempty="true", quantity__isempty="false")
    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["results"]] == [lists["movements"][2].pk]


def test_date_bounds_remain_one_or_group_and_include_the_complete_final_day(lists):
    with timezone.override("Europe/Paris"):
        tz = ZoneInfo("Europe/Paris")
        dates = [datetime(2026, 10, 25, 23, 59, 59, 999999, tzinfo=tz), datetime(2026, 10, 26, 0, 0, tzinfo=tz), datetime(2026, 10, 20, 12, tzinfo=tz)]
        for movement, created in zip(lists["movements"], dates, strict=True):
            StockMovement.objects.filter(pk=movement.pk).update(date_created=created)
        response = get_list(lists, "movements", filter_logic="or", filter_groups=json.dumps([
            {"date_created_after": "2026-10-25", "date_created_before": "2026-10-25"}, {"note": "Correction"},
        ]))
        assert response.status_code == 200, response.data
        assert {row["id"] for row in response.data["results"]} == {row.pk for row in lists["movements"][:2]}


@pytest.mark.parametrize("params", [
    {"quantity__gt": "not-a-number"}, {"quantity__lt": "NaN"},
    {"date_created_after": "2026-99-99"},
    {"filter_logic": "or", "filter_groups": "invalid"},
    {"filter_logic": "or", "filter_groups": "[]"},
    {"filter_logic": "or", "filter_groups": '[{"company_id": "999"}]'},
    {"filter_logic": "or", "filter_groups": '[{"quantity__gt": []}]'},
])
def test_invalid_filters_return_400_instead_of_server_errors_or_widened_results(lists, params):
    response = get_list(lists, "movements", **params)
    assert response.status_code == 400, response.data


def test_global_search_stays_an_and_constraint_on_filter_groups(lists):
    response = get_list(lists, "movements", search="Correction", filter_logic="or", filter_groups=json.dumps([{"quantity__lt": "0"}, {"quantity__gt": "0"}]))
    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["results"]] == [lists["movements"][1].pk]
