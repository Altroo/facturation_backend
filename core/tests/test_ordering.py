from decimal import Decimal

import pytest
from django.apps import apps
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from client.models import Client
from company.models import Company
from core.ordering import _fields, apply_list_ordering
from parameter.models import Emplacement, Ville
from stock.models import StockBalance

pytestmark = pytest.mark.django_db


@pytest.fixture
def context():
    user = CustomUser.objects.create_user(
        email="ordering@example.test", password="test"
    )
    company = Company.objects.create(raison_sociale="Ordering", ICE="ORDER")
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(user=user, company=company, role=role)
    api = APIClient()
    api.force_authenticate(user)
    return api, company


def test_ordering_precedes_pagination_and_preserves_company_and_filters(context):
    api, company = context
    other = Company.objects.create(raison_sociale="Other", ICE="OTHER")
    for index, name in enumerate(
        ["Zulu", "Bravo", "Echo", "alpha", "Delta", "Charlie", "Foxtrot"]
    ):
        Client.objects.create(
            company=company,
            code_client=f"C{index}",
            client_type="PM",
            raison_sociale=name,
        )
    Client.objects.create(
        company=other, code_client="X", client_type="PM", raison_sociale="AAA foreign"
    )
    Client.objects.create(
        company=company,
        code_client="A",
        client_type="PM",
        raison_sociale="AAA archived",
        archived=True,
    )
    params = {
        "company_id": company.pk,
        "pagination": "true",
        "page_size": 5,
        "archived": "false",
    }

    def names(ordering, page=1):
        response = api.get(
            "/api/client/", {**params, "ordering": ordering, "page": page}
        )
        assert response.status_code == 200, response.data
        assert response.data["count"] == 7
        return [row["raison_sociale"] for row in response.data["results"]]

    ascending = names("raison_sociale") + names("raison_sociale", 2)
    assert ascending == [
        "alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
        "Zulu",
    ]
    assert names("-raison_sociale") + names("-raison_sociale", 2) == ascending[::-1]


def test_related_names_numeric_values_ties_and_nulls(context):
    _, company = context
    zulu = Ville.objects.create(company=company, nom="Zulu")
    alpha = Ville.objects.create(company=company, nom="Alpha")
    rows = [
        Client.objects.create(
            company=company, code_client=str(i), client_type="PM", ville=city
        )
        for i, city in enumerate([zulu, None, alpha, alpha])
    ]
    qs = Client.objects.filter(company=company)
    assert list(apply_list_ordering(qs, {"ordering": "ville_name"})) == [
        rows[2],
        rows[3],
        rows[0],
        rows[1],
    ]
    assert list(apply_list_ordering(qs, {"ordering": "-ville_name"})) == [
        rows[0],
        rows[3],
        rows[2],
        rows[1],
    ]
    for i, price in enumerate([100, 2, 10]):
        Article.objects.create(
            company=company, reference=str(i), designation=str(i), prix_vente=price
        )
    assert list(
        apply_list_ordering(
            Article.objects.all(), {"ordering": "prix_vente"}
        ).values_list("prix_vente", flat=True)
    ) == [2, 10, 100]


def test_computed_available_stock_matches_displayed_quantity(context):
    _, company = context
    company.stock_management_enabled = True
    company.save()
    location = Emplacement.objects.create(company=company, nom="Depot")
    balances = []
    for i, (physical, reserved) in enumerate([(100, 99), (3, 0), (10, 5)]):
        article = Article.objects.create(
            company=company,
            reference=f"P{i}",
            designation=f"P{i}",
            type_article="Produit",
            emplacement=location,
        )
        balances.append(
            StockBalance.objects.create(
                company=company,
                article=article,
                emplacement=location,
                physical_quantity=physical,
                reserved_quantity=reserved,
            )
        )
    assert (
        list(
            apply_list_ordering(
                StockBalance.objects.all(), {"ordering": "available_quantity"}
            )
        )
        == balances
    )
    assert [
        row.pk
        for row in apply_list_ordering(
            Article.objects.all(), {"ordering": "-available_quantity"}
        )
    ] == [row.article_id for row in balances[::-1]]


@pytest.mark.parametrize(
    "model",
    [
        "accounts.CustomUser",
        "company.Company",
        "client.Client",
        "article.Article",
        "reglement.Reglement",
        "stock.StockMovement",
        "stock.StockReceipt",
        "stock.InventorySession",
        "stock.StockBalance",
        "logistique.LogisticsOrder",
        "devi.Devi",
        "facture_proforma.FactureProForma",
        "facture_client.FactureClient",
        "facture_avoir.FactureAvoir",
        "bon_de_livraison.BonDeLivraison",
    ],
)
def test_every_public_ordering_expression_executes(model):
    qs = apps.get_model(model).objects.all()
    _, fields = _fields(qs, "")
    extra = {
        "article.Article": ["available_quantity"],
        "facture_client.FactureClient": [
            "nombre_paiements",
            "total_paye",
            "reste_a_payer",
            "statut_paiement",
        ],
        "logistique.LogisticsOrder": [
            "clients_display",
            "projects_display",
            "statut_global",
        ],
    }.get(model, [])
    assert fields
    for field in [*fields, *extra]:
        for prefix in ["", "-"]:
            list(apply_list_ordering(qs, {"ordering": prefix + field})[:2])


@pytest.mark.parametrize(
    "ordering",
    [
        "password",
        "company__ICE",
        "-password",
        "raison_sociale,-id",
        "id; DROP TABLE client",
        "-",
    ],
)
def test_unsupported_ordering_preserves_default(context, ordering):
    _, company = context
    qs = Client.objects.filter(company=company).order_by("-id")
    assert str(apply_list_ordering(qs, {"ordering": ordering}).query) == str(qs.query)
