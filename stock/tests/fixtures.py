from datetime import date
from decimal import Decimal
from typing import TypedDict

import pytest

from account.models import CustomUser
from article.models import Article
from client.models import Client
from company.models import Company
from facture_proforma.models import FactureProForma, FactureProFormaLine
from parameter.models import Emplacement, Ville
from stock.models import StockBalance


class StockContext(TypedDict):
    user: CustomUser
    company: Company
    emplacement: Emplacement
    client: Client
    article: Article
    balance: StockBalance
    proforma: FactureProForma
    proforma_line: FactureProFormaLine


@pytest.fixture
def stock_context() -> StockContext:
    user = CustomUser.objects.create_user(email="stock@example.com", password="pass")
    company = Company.objects.create(
        raison_sociale="Stock Company",
        ICE="STOCK-COMPANY",
        stock_management_enabled=True,
        inventory_management_enabled=True,
    )
    emplacement = Emplacement.objects.create(company=company, nom="Dépôt")
    ville = Ville.objects.create(company=company, nom="Casablanca")
    client = Client.objects.create(
        company=company,
        ville=ville,
        code_client="STOCK-CLIENT",
        client_type="PM",
        raison_sociale="Client stock",
    )
    article = Article.objects.create(
        company=company,
        emplacement=emplacement,
        reference="STOCK-001",
        designation="Produit stocké",
        type_article="Produit",
        stock_minimum=Decimal("2.000"),
    )
    balance = StockBalance.objects.create(
        company=company,
        article=article,
        emplacement=emplacement,
        physical_quantity=Decimal("4.000"),
    )
    proforma = FactureProForma.objects.create(
        company=company,
        client=client,
        numero_facture="PF-STOCK-001",
        date_facture=date(2026, 9, 10),
        statut="Envoyé",
        fournisseur="Fournisseur stock",
        created_by_user=user,
    )
    proforma_line = FactureProFormaLine.objects.create(
        facture_pro_forma=proforma,
        article=article,
        quantity=Decimal("6.000"),
        prix_achat=Decimal("10.00"),
        prix_vente=Decimal("15.00"),
    )
    return {
        "user": user,
        "company": company,
        "emplacement": emplacement,
        "client": client,
        "article": article,
        "balance": balance,
        "proforma": proforma,
        "proforma_line": proforma_line,
    }
