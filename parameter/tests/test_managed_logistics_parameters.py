from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from article.models import Article
from bon_de_livraison.models import BonDeLivraison
from client.models import Client
from company.models import Company
from logistique.models import LogisticsOrder, LogisticsSupplier
from parameter.models import (
    Incoterm,
    OrigineMarchandise,
    NatureMarchandise,
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)

pytestmark = pytest.mark.django_db
KINDS = [
    ("incoterm", Incoterm),
    ("origine_marchandise", OrigineMarchandise),
    ("nature_marchandise", NatureMarchandise),
]


@pytest.fixture
def context(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    company = Company.objects.create(raison_sociale="CASA DI LUSSO", ICE="PARAM-CASA")
    other = Company.objects.create(
        raison_sociale="IMMOBILIERE NECTAR", ICE="PARAM-OTHER"
    )
    user = CustomUser.objects.create_user(
        email="parameters@example.invalid", password="test-only"
    )
    membership = Membership.objects.create(
        company=company, user=user, role=Role.objects.get_or_create(name="Caissier")[0]
    )
    api = APIClient()
    api.force_authenticate(user)
    return SimpleNamespace(
        company=company, other=other, user=user, membership=membership, api=api
    )


@pytest.mark.parametrize("kind,model", KINDS)
@pytest.mark.parametrize("role", ["Caissier", "Logistique"])
def test_add_edit_delete_unused_and_duplicate_names(context, kind, model, role):
    ctx = context
    ctx.membership.role = Role.objects.get_or_create(name=role)[0]
    ctx.membership.save()
    url = f"/api/parameter/{kind}/"
    created = ctx.api.post(url, {"company": ctx.company.pk, "nom": "AAA"})
    assert created.status_code == 201, created.data
    item_id = created.data["id"]
    duplicate = ctx.api.post(url, {"company": ctx.company.pk, "nom": "aaa"})
    assert duplicate.status_code == 400
    changed = ctx.api.put(f"{url}{item_id}/", {"company": ctx.company.pk, "nom": "BBB"})
    assert changed.status_code == 200, changed.data
    assert ctx.api.get(url, {"company_id": ctx.company.pk}).data[0]["nom"] == "BBB"
    assert ctx.api.delete(f"{url}{item_id}/").status_code == 204
    assert not model.objects.filter(pk=item_id).exists()


@pytest.mark.parametrize("kind,model", KINDS)
def test_used_dossier_parameter_cannot_be_deleted_after_rename(context, kind, model):
    ctx = context
    item = model.objects.create(company=ctx.company, nom="AAA")
    order = LogisticsOrder.objects.create(
        company=ctx.company, numero_commande="COM001/26", **{kind: "AAA"}
    )
    assert getattr(order, f"{kind}_record_id") == item.pk
    with pytest.raises(ProtectedError):
        item.delete()
    url = f"/api/parameter/{kind}/{item.pk}/"
    response = ctx.api.delete(url)
    assert response.status_code == 400, response.data
    assert "déjà utilisé" in str(response.data)
    assert (
        ctx.api.put(url, {"company": ctx.company.pk, "nom": "BBB"}).status_code == 200
    )
    order.save(update_fields=["date_updated"])
    order.refresh_from_db()
    assert getattr(order, kind) == "AAA"
    assert getattr(order, f"{kind}_record_id") == item.pk
    assert ctx.api.delete(url).status_code == 400


@pytest.mark.parametrize("kind,model", KINDS)
def test_old_history_and_closed_dossiers_retain_parameter(context, kind, model):
    ctx = context
    order = LogisticsOrder.objects.create(
        company=ctx.company, numero_commande="COM001/26", **{kind: "AAA"}
    )
    original = model.objects.get(pk=getattr(order, f"{kind}_record_id"))
    setattr(order, kind, "BBB")
    order.save()
    order.refresh_from_db()
    assert getattr(order, f"{kind}_record_id") != original.pk
    assert ctx.api.delete(f"/api/parameter/{kind}/{original.pk}/").status_code == 400
    assert order.history.filter(**{f"{kind}_record_id": original.pk}).exists()


@pytest.mark.parametrize("kind,model", KINDS)
def test_company_isolation_and_read_only_role(context, kind, model):
    ctx = context
    foreign = model.objects.create(company=ctx.other, nom="Private")
    own = model.objects.create(company=ctx.company, nom="Own")
    url = f"/api/parameter/{kind}/"
    assert ctx.api.get(url, {"company_id": ctx.other.pk}).data == []
    assert ctx.api.delete(f"{url}{foreign.pk}/").status_code == 404
    assert (
        ctx.api.post(url, {"company": ctx.other.pk, "nom": "Forbidden"}).status_code
        == 403
    )
    assert (
        ctx.api.put(
            f"{url}{own.pk}/", {"company": ctx.other.pk, "nom": "Moved"}
        ).status_code
        == 403
    )
    ctx.membership.role = Role.objects.get_or_create(name="Comptable")[0]
    ctx.membership.save()
    assert (
        ctx.api.post(url, {"company": ctx.company.pk, "nom": "Forbidden"}).status_code
        == 403
    )
    assert ctx.api.delete(f"{url}{own.pk}/").status_code == 403
    assert ctx.api.get(url, {"company_id": ctx.company.pk}).status_code == 200


@pytest.mark.parametrize(
    "kind,model,field",
    [
        ("marque", Marque, "marque"),
        ("categorie", Categorie, "categorie"),
        ("unite", Unite, "unite"),
        ("emplacement", Emplacement, "emplacement"),
    ],
)
def test_article_selections_cannot_be_cleared_by_parameter_deletion(
    context, kind, model, field
):
    ctx = context
    item = model.objects.create(company=ctx.company, nom="Used")
    article = Article.objects.create(
        company=ctx.company,
        reference="PARAM-ARTICLE",
        designation="Test",
        **{field: item},
    )
    response = ctx.api.delete(f"/api/parameter/{kind}/{item.pk}/")
    assert response.status_code == 400, response.data
    article.refresh_from_db()
    assert getattr(article, f"{field}_id") == item.pk


@pytest.mark.parametrize(
    "kind,model",
    [("ville", Ville), ("mode_paiement", ModePaiement), ("livre_par", LivrePar)],
)
def test_other_saved_selections_cannot_be_cleared(context, kind, model):
    ctx = context
    item = model.objects.create(company=ctx.company, nom="Used")
    client = Client.objects.create(
        company=ctx.company,
        code_client="PARAM-CLIENT",
        client_type="PP",
        **({"ville": item} if kind == "ville" else {}),
    )
    if kind != "ville":
        document = BonDeLivraison.objects.create(
            company=ctx.company,
            client=client,
            numero_bon_livraison="PARAM-BL",
            date_bon_livraison=timezone.localdate(),
            **{kind: item},
        )
    assert ctx.api.delete(f"/api/parameter/{kind}/{item.pk}/").status_code == 400
    if kind == "ville":
        client.refresh_from_db()
        assert client.ville_id == item.pk
    else:
        document.refresh_from_db()
        assert getattr(document, f"{kind}_id") == item.pk


def test_catalog_is_scoped_corrected_idempotent_and_preserves_used_records(context):
    ctx = context
    alias = Marque.objects.create(
        company=ctx.company, nom="SapienStone", email="keep@example.invalid"
    )
    supplier = LogisticsSupplier.objects.create(
        company=ctx.company, nom="Delta Light Group", email="supplier@example.invalid"
    )
    retired = Marque.objects.create(company=ctx.company, nom="Hatria")
    marazzi = LogisticsSupplier.objects.create(company=ctx.company, nom="Marazzi Group")
    marazzi.marques.add(retired)
    article = Article.objects.create(
        company=ctx.company, reference="KEEP", designation="Existing", marque=retired
    )
    order = LogisticsOrder.objects.create(
        company=ctx.other,
        numero_commande="PRIVATE",
        incoterm="Custom old",
        origine_marchandise="Old origin",
        nature_marchandise="Old nature",
    )
    LogisticsOrder.objects.filter(pk=order.pk).update(
        incoterm_record=None,
        origine_marchandise_record=None,
        nature_marchandise_record=None,
    )
    migration = import_module(
        "logistique.migrations.0027_managed_parameters_and_supplier_catalog"
    )
    with connection.schema_editor() as editor:
        migration.seed_catalog(apps, editor)
        migration.seed_catalog(apps, editor)
    assert set(
        Incoterm.objects.filter(company=ctx.company).values_list("nom", flat=True)
    ) == set(migration.INCOTERMS)
    assert (
        Marque.objects.filter(company=ctx.company).count() == 28
    )  # 27 approved brands plus the preserved used brand.
    assert not Marque.objects.filter(company=ctx.other).exists()
    assert not LogisticsSupplier.objects.filter(company=ctx.other).exists()
    alias.refresh_from_db()
    assert alias.nom == "Sapienstone" and alias.email == "keep@example.invalid"
    supplier.refresh_from_db()
    assert (
        supplier.nom == "Delta Light" and supplier.email == "supplier@example.invalid"
    )
    assert set(supplier.marques.values_list("nom", flat=True)) == {
        "Delta Light",
        "AQForm",
        "LEDsGO",
    }
    assert set(marazzi.marques.values_list("nom", flat=True)) == {"Marazzi", "Ragno"}
    article.refresh_from_db()
    assert article.marque_id == retired.pk
    order.refresh_from_db()
    assert order.incoterm == "Custom old" and order.incoterm_record_id
    assert (
        order.origine_marchandise == "Old origin"
        and order.origine_marchandise_record_id
    )
    assert (
        order.nature_marchandise == "Old nature" and order.nature_marchandise_record_id
    )
