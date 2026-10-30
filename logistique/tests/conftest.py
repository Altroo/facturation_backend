from types import SimpleNamespace

import pytest

from account.models import CustomUser, Membership, Role
from article.models import Article
from company.models import Company
from logistique.tests.helpers import authenticated
from parameter.models import Emplacement, Marque
from stock.models import StockBalance


@pytest.fixture
def purchase_context(settings, tmp_path):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MEDIA_ROOT = tmp_path
    company = Company.objects.create(
        raison_sociale="Supplier workflow", ICE="SUP-001", stock_management_enabled=True
    )
    foreign = Company.objects.create(raison_sociale="Other company", ICE="SUP-002")

    def member(email, role, owner=company):
        user = CustomUser.objects.create_user(email=email, password="test-only")
        Membership.objects.create(
            user=user, company=owner, role=Role.objects.get_or_create(name=role)[0]
        )
        return user

    creator = member("creator@example.invalid", "Logistique")
    responsible = member("responsible@example.invalid", "Logistique")
    accountant = member("accountant@example.invalid", "Comptable")
    reader = member("reader@example.invalid", "Lecture")
    outsider = member("outsider@example.invalid", "Logistique", foreign)
    location = Emplacement.objects.create(company=company, nom="Dépôt principal")
    foreign_location = Emplacement.objects.create(
        company=foreign, nom="Other warehouse"
    )
    brand = Marque.objects.create(
        company=company, nom="Supplier brand", email="supplier@example.invalid"
    )
    article = Article.objects.create(
        company=company,
        reference="SUP-ARTICLE",
        designation="Article fournisseur",
        type_article="produit",
        emplacement=location,
        prix_achat="5.00",
        prix_vente="9.00",
        tva=0,
    )
    foreign_article = Article.objects.create(
        company=foreign,
        reference="FOREIGN",
        designation="Private article",
        type_article="produit",
        emplacement=foreign_location,
        prix_achat=1,
        prix_vente=2,
        tva=0,
    )
    balance = StockBalance.objects.create(
        company=company, article=article, emplacement=location
    )
    return SimpleNamespace(
        company=company,
        foreign=foreign,
        creator=creator,
        responsible=responsible,
        accountant=accountant,
        reader=reader,
        outsider=outsider,
        location=location,
        foreign_location=foreign_location,
        brand=brand,
        article=article,
        foreign_article=foreign_article,
        balance=balance,
        api=authenticated(creator),
    )
