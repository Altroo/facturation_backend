"""Supplier CRUD, company isolation, dossier links and server-side grid behavior."""

from datetime import datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from account.models import CustomUser, Membership, Role
from company.models import Company
from logistique.models import LogisticsOrder, LogisticsSupplier, LogisticsChangeRequest
from logistique.suppliers import ensure_supplier

pytestmark = pytest.mark.django_db
URL = "/api/logistique/fournisseurs/"


@pytest.fixture
def suppliers():
    company = Company.objects.create(
        raison_sociale="Supplier grid", ICE="SUPPLIER-GRID"
    )
    other = Company.objects.create(
        raison_sociale="Private company", ICE="SUPPLIER-OTHER"
    )
    user = CustomUser.objects.create_user(
        email="supplier-grid@example.invalid", password="test-only"
    )
    membership = Membership.objects.create(
        company=company, user=user, role=Role.objects.get_or_create(name="Lecture")[0]
    )
    client = APIClient()
    client.force_authenticate(user)
    rows = [
        ("Alpha", "alpha@example.invalid", [1, 5, 32]),
        ("beta", "beta@example.invalid", [15]),
        ("Gamma", "", [1, 60, 91]),
        ("Delta", "delta@example.invalid", [20]),
        ("Epsilon", "epsilon@example.invalid", [25]),
        ("Zeta", "zeta@example.invalid", []),
    ]
    for name, email, days in rows:
        supplier = LogisticsSupplier.objects.create(
            company=company, nom=name, email=email
        )
        LogisticsSupplier.objects.filter(pk=supplier.pk).update(
            date_updated=timezone.make_aware(datetime(2026, 1, 10))
        )
        for day in days:
            order = LogisticsOrder.objects.create(
                company=company,
                numero_commande=f"QA-{LogisticsOrder.objects.count()}",
                fournisseur_record=supplier,
                fournisseur=name,
                fournisseur_email=email,
            )
            moment = timezone.make_aware(datetime(2026, 1, 1)) + timedelta(days=day - 1)
            LogisticsOrder.objects.filter(pk=order.pk).update(date_updated=moment)
    LogisticsSupplier.objects.create(company=other, nom="PRIVATE SUPPLIER")
    return SimpleNamespace(
        client=client, company=company, other=other, user=user, membership=membership
    )


def request(ctx, **params):
    return ctx.client.get(URL, {"company_id": ctx.company.pk, **params})


def allow(ctx, role="Caissier"):
    ctx.membership.role = Role.objects.get_or_create(name=role)[0]
    ctx.membership.save()
    ctx.user.role_cache = {}


def detail(ctx, supplier):
    return f"{URL}{supplier.pk}/?company_id={ctx.company.pk}"


def test_array_and_pagination_include_suppliers_without_dossiers(suppliers):
    data = request(suppliers).data
    assert len(data) == 6
    assert next(row for row in data if row["nom"] == "Zeta")["total_dossiers"] == 0
    first = request(suppliers, pagination="true", page_size=2)
    second = request(suppliers, pagination="true", page_size=2, page=2)
    assert first.status_code == second.status_code == 200
    assert first.data["count"] == second.data["count"] == 6
    assert first.data["next"] and second.data["previous"]
    assert [r["nom"] for r in first.data["results"]] == ["Alpha", "beta"]
    assert all("PRIVATE" not in str(row) for row in data)
    assert all(
        row["fournisseur"] == row["nom"] and row["fournisseur_email"] == row["email"]
        for row in data
    )


@pytest.mark.parametrize(
    "field", ["nom", "email", "total_dossiers", "derniere_activite"]
)
@pytest.mark.parametrize("descending", [False, True])
def test_all_column_sorts_apply_before_pagination(suppliers, field, descending):
    rows = []
    for page in (1, 2, 3):
        response = request(
            suppliers,
            pagination="true",
            page_size=2,
            page=page,
            ordering=("-" if descending else "") + field,
        )
        assert response.status_code == 200
        assert response.data["count"] == 6
        rows.extend(response.data["results"])
    values = [
        row[field].casefold() if isinstance(row[field], str) else row[field]
        for row in rows
    ]
    assert values == sorted(values, reverse=descending)
    assert len({row["id"] for row in rows}) == 6
    assert next(row for row in rows if row["nom"] == "Alpha")["total_dossiers"] == 3


def test_or_filters_preserve_search_and_company_scope(suppliers):
    import json

    response = request(suppliers, pagination="true", filter_logic="or", filter_groups=json.dumps([
        {"nom": "Alpha"}, {"total_dossiers__lt": 1},
    ]))
    assert response.status_code == 200
    assert {row["nom"] for row in response.data["results"]} == {"Alpha", "Zeta"}
    response = request(suppliers, search="Zeta", filter_logic="or", filter_groups=json.dumps([
        {"nom": "Alpha"}, {"total_dossiers__lt": 1},
    ]))
    assert [row["nom"] for row in response.data] == ["Zeta"]


def test_search_and_text_filters(suppliers):
    searched = request(suppliers, pagination="true", search="Alpha alpha@")
    assert searched.data["count"] == 1
    assert searched.data["results"][0]["total_dossiers"] == 3
    empty = request(suppliers, pagination="true", email__isempty="true")
    assert empty.data["count"] == 1 and empty.data["results"][0]["nom"] == "Gamma"
    assert (
        request(suppliers, pagination="true", nom__istartswith="ALP").data["count"] == 1
    )


def test_numeric_and_latest_activity_filters(suppliers):
    counts = request(suppliers, pagination="true", total_dossiers__gte=2)
    assert counts.status_code == 200 and counts.data["count"] == 2
    assert {row["nom"] for row in counts.data["results"]} == {"Alpha", "Gamma"}
    latest = request(
        suppliers, pagination="true", derniere_activite_before="2026-01-31"
    )
    assert latest.status_code == 200 and latest.data["count"] == 4
    recent = request(suppliers, pagination="true", derniere_activite_after="2026-03-01")
    assert (
        recent.data["count"] == 1 and recent.data["results"][0]["total_dossiers"] == 3
    )


@pytest.mark.parametrize(
    "params",
    [{"total_dossiers__gte": "invalid"}, {"derniere_activite_after": "invalid"}],
)
def test_bad_filter_values_return_validation_errors(suppliers, params):
    assert request(suppliers, pagination="true", **params).status_code == 400


def test_access_and_ordering_whitelist(suppliers):
    ctx = suppliers
    assert ctx.client.get(URL, {"company_id": ctx.other.pk}).status_code == 403
    assert ctx.client.get(URL).status_code == 404
    assert APIClient().get(URL, {"company_id": ctx.company.pk}).status_code in (
        401,
        403,
    )
    invalid = request(ctx, pagination="true", ordering="created_by_user__email")
    assert invalid.status_code == 200 and invalid.data["count"] == 6


@pytest.mark.parametrize("role", ["Caissier", "Commercial", "Logistique"])
def test_create_view_edit_and_unused_supplier_deletion(suppliers, role):
    ctx = suppliers
    allow(ctx, role)
    response = ctx.client.post(
        URL + f"?company_id={ctx.company.pk}",
        {"nom": "  New supplier  ", "email": "new@example.invalid"},
    )
    assert response.status_code == 201, response.data
    supplier = LogisticsSupplier.objects.get(pk=response.data["id"])
    assert supplier.nom == "New supplier" and response.data["total_dossiers"] == 0
    assert ctx.client.get(detail(ctx, supplier)).data["nom"] == "New supplier"
    response = ctx.client.put(
        detail(ctx, supplier), {"nom": "Renamed", "email": ""}, format="json"
    )
    assert (
        response.status_code == 200
        and response.data["nom"] == "Renamed"
        and response.data["email"] == ""
    )
    assert supplier.history.count() == 2
    deleted = ctx.client.delete(detail(ctx, supplier))
    assert deleted.status_code == (204 if role == "Caissier" else 403)


def test_duplicate_invalid_email_and_empty_name(suppliers):
    ctx = suppliers
    allow(ctx)
    for data in [
        {"nom": " alpha "},
        {"nom": ""},
        {"nom": "  "},
        {"nom": "Supplier", "email": "wrong"},
    ]:
        assert (
            ctx.client.post(URL + f"?company_id={ctx.company.pk}", data).status_code
            == 400
        )


def test_reader_cannot_write_and_foreign_company_cannot_be_used(suppliers):
    ctx = suppliers
    supplier = LogisticsSupplier.objects.filter(company=ctx.company).first()
    url = detail(ctx, supplier)
    assert (
        ctx.client.post(
            URL + f"?company_id={ctx.company.pk}", {"nom": "Blocked"}
        ).status_code
        == 403
    )
    assert ctx.client.patch(url, {"nom": "Blocked"}).status_code == 403
    assert ctx.client.delete(url).status_code == 403
    allow(ctx)
    assert (
        ctx.client.patch(url, {"company": ctx.other.pk, "nom": "Moved"}).status_code
        == 400
    )
    foreign = LogisticsSupplier.objects.get(company=ctx.other)
    assert ctx.client.get(detail(ctx, foreign)).status_code == 404
    assert ctx.client.patch(detail(ctx, foreign), {"nom": "Stolen"}).status_code == 404
    assert ctx.client.delete(detail(ctx, foreign)).status_code == 404
    assert (
        ctx.client.get(f"{URL}{foreign.pk}/?company_id={ctx.other.pk}").status_code
        == 403
    )
    supplier.refresh_from_db()
    assert supplier.company_id == ctx.company.pk


def test_edit_preserves_snapshots_dossier_filter_and_protected_delete(suppliers):
    ctx = suppliers
    allow(ctx)
    supplier = LogisticsSupplier.objects.get(company=ctx.company, nom="Alpha")
    originals = list(
        supplier.dossiers.order_by("pk").values_list(
            "pk", "fournisseur", "fournisseur_email", "date_updated"
        )
    )
    response = ctx.client.patch(
        detail(ctx, supplier),
        {"nom": "Renamed Alpha", "email": "changed@example.invalid"},
    )
    assert response.status_code == 200 and response.data["total_dossiers"] == 3
    assert (
        list(
            supplier.dossiers.order_by("pk").values_list(
                "pk", "fournisseur", "fournisseur_email", "date_updated"
            )
        )
        == originals
    )
    orders = ctx.client.get(
        "/api/logistique/",
        {
            "company_id": ctx.company.pk,
            "fournisseur_record": supplier.pk,
            "pagination": "true",
        },
    )
    assert orders.status_code == 200 and orders.data["count"] == 3
    deleted = ctx.client.delete(detail(ctx, supplier))
    assert deleted.status_code == 400 and "dossiers" in str(deleted.data)
    assert supplier.dossiers.count() == 3


def test_dossier_uses_existing_supplier_and_preserves_link_after_directory_rename(
    suppliers,
):
    from logistique.purchase_views import create_purchase_dossier

    ctx = suppliers
    allow(ctx)
    supplier = LogisticsSupplier.objects.get(company=ctx.company, nom="Alpha")
    order = create_purchase_dossier(
        ctx.company.pk, ctx.user, {"fournisseur_record": supplier.pk}
    )[0]
    assert (
        order.fournisseur_record_id == supplier.pk
        and order.fournisseur_email == supplier.email
    )
    def approval():
        return LogisticsChangeRequest.objects.create(commande=order, etape="dossier", remarque="Correction du contact", demandeur=ctx.user, responsable=ctx.user, statut="approved").pk
    supplier.nom = "Renamed Alpha"
    supplier.save()
    response = ctx.client.post(
        f"/api/logistique/{order.pk}/purchase/",
        {
            "action": "dossier",
            "fournisseur": "Alpha",
            "fournisseur_email": "updated-dossier@example.invalid",
            "correction_id": approval(),
        },
    )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.fournisseur_record_id == supplier.pk
    assert order.fournisseur == "Alpha"
    response = ctx.client.post(
        f"/api/logistique/{order.pk}/purchase/",
        {"action": "dossier", "fournisseur": "Different supplier", "correction_id": approval()},
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.fournisseur_record_id != supplier.pk
    foreign = LogisticsSupplier.objects.get(company=ctx.other)
    response = ctx.client.post(
        f"/api/logistique/{order.pk}/purchase/",
        {"action": "dossier", "fournisseur_record": foreign.pk, "correction_id": approval()},
    )
    assert response.status_code == 400


def test_ensure_supplier_reuses_name_without_replacing_contact_email(suppliers):
    ctx = suppliers
    existing = LogisticsSupplier.objects.get(company=ctx.company, nom="Alpha")
    assert (
        ensure_supplier(ctx.company.pk, "  ALPHA  ", "another@example.invalid").pk
        == existing.pk
    )
    existing.refresh_from_db()
    assert existing.email == "alpha@example.invalid"


def test_backfill_combines_name_variants_and_preserves_brands_and_dossiers():
    from parameter.models import Marque

    company = Company.objects.create(raison_sociale="Backfill", ICE="BACKFILL")
    first = LogisticsOrder.objects.create(
        company=company,
        numero_commande="OLD-1",
        fournisseur=" Alpha ",
        fournisseur_email="old@example.invalid",
    )
    second = LogisticsOrder.objects.create(
        company=company,
        numero_commande="OLD-2",
        fournisseur="ALPHA",
        fournisseur_email="new@example.invalid",
    )
    brand = Marque.objects.create(
        company=company, nom="Contact only", email="contact@example.invalid"
    )
    Marque.objects.create(company=company, nom="Brand only", email="")
    originals = list(
        LogisticsOrder.objects.filter(company=company).values_list(
            "pk", "fournisseur", "fournisseur_email", "date_updated"
        )
    )
    populate = import_module(
        "logistique.migrations.0019_populate_supplier_directory"
    ).populate_suppliers
    populate(apps, SimpleNamespace(connection=connection))
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.fournisseur_record_id == second.fournisseur_record_id
    assert first.fournisseur_record.email == "new@example.invalid"
    assert (
        list(
            LogisticsOrder.objects.filter(company=company).values_list(
                "pk", "fournisseur", "fournisseur_email", "date_updated"
            )
        )
        == originals
    )
    assert LogisticsSupplier.objects.filter(company=company).count() == 2
    assert (
        LogisticsSupplier.objects.get(company=company, nom="Contact only").email
        == brand.email
    )
    assert Marque.objects.filter(company=company).count() == 2


def bulk_url(ctx):
    return f"{URL}bulk_delete/?company_id={ctx.company.pk}"


def test_bulk_delete_unused_suppliers_preserves_brands_and_dossiers(suppliers):
    from parameter.models import Marque

    ctx = suppliers
    allow(ctx)
    first = LogisticsSupplier.objects.create(company=ctx.company, nom="Unused one")
    second = LogisticsSupplier.objects.create(company=ctx.company, nom="Unused two")
    brand = Marque.objects.create(company=ctx.company, nom="Keep brand")
    first.marques.add(brand)
    ids = [first.pk, second.pk]
    orders = list(LogisticsOrder.objects.values_list("pk", "fournisseur_record_id"))

    response = ctx.client.delete(bulk_url(ctx), {"ids": ids}, format="json")

    assert response.status_code == 204, response.data
    assert not LogisticsSupplier.objects.filter(pk__in=ids).exists()
    assert Marque.objects.filter(pk=brand.pk).exists()
    assert list(LogisticsOrder.objects.values_list("pk", "fournisseur_record_id")) == orders
    assert LogisticsSupplier.history.filter(id__in=ids, history_type="-").count() == 2


def test_bulk_delete_with_linked_supplier_keeps_the_entire_selection(suppliers):
    ctx = suppliers
    allow(ctx)
    unused = LogisticsSupplier.objects.get(company=ctx.company, nom="Zeta")
    linked = LogisticsSupplier.objects.get(company=ctx.company, nom="Alpha")
    ids = [unused.pk, linked.pk]
    orders = list(LogisticsOrder.objects.values_list("pk", "fournisseur_record_id"))

    response = ctx.client.delete(bulk_url(ctx), {"ids": ids}, format="json")

    assert response.status_code == 400
    assert LogisticsSupplier.objects.filter(pk__in=ids).count() == 2
    assert list(LogisticsOrder.objects.values_list("pk", "fournisseur_record_id")) == orders
    assert LogisticsSupplier.history.filter(id__in=ids, history_type="-").count() == 0


@pytest.mark.parametrize("also_member", [False, True])
def test_bulk_delete_cannot_cross_the_selected_company(suppliers, also_member):
    ctx = suppliers
    allow(ctx)
    if also_member:
        Membership.objects.create(company=ctx.other, user=ctx.user, role=ctx.membership.role)
    own = LogisticsSupplier.objects.get(company=ctx.company, nom="Zeta")
    foreign = LogisticsSupplier.objects.get(company=ctx.other)
    ids = [own.pk, foreign.pk]

    response = ctx.client.delete(bulk_url(ctx), {"ids": ids}, format="json")

    assert response.status_code == 404
    assert LogisticsSupplier.objects.filter(pk__in=ids).count() == 2


@pytest.mark.parametrize("role", ["Lecture", "Comptable", "Commercial", "Logistique"])
def test_bulk_delete_requires_the_same_permission_as_single_delete(suppliers, role):
    ctx = suppliers
    allow(ctx, role)
    supplier = LogisticsSupplier.objects.get(company=ctx.company, nom="Zeta")
    assert ctx.client.delete(bulk_url(ctx), {"ids": [supplier.pk]}, format="json").status_code == 403
    assert LogisticsSupplier.objects.filter(pk=supplier.pk).exists()


@pytest.mark.parametrize("ids", [None, [], "1", 1, [0], [-1], [True], ["invalid"], ["1.0"], [1, 1]])
def test_bulk_delete_rejects_invalid_ids(suppliers, ids):
    ctx = suppliers
    allow(ctx)
    before = LogisticsSupplier.objects.count()
    response = ctx.client.delete(bulk_url(ctx), {"ids": ids}, format="json")
    assert response.status_code == 400
    assert LogisticsSupplier.objects.count() == before


def test_bulk_delete_requires_authentication_and_company_access(suppliers):
    ctx = suppliers
    allow(ctx)
    supplier = LogisticsSupplier.objects.get(company=ctx.company, nom="Zeta")
    data = {"ids": [supplier.pk]}
    assert APIClient().delete(bulk_url(ctx), data, format="json").status_code in (401, 403)
    assert ctx.client.delete(URL + "bulk_delete/", data, format="json").status_code == 404
    assert ctx.client.delete(f"{URL}bulk_delete/?company_id={ctx.other.pk}", data, format="json").status_code == 403
    assert LogisticsSupplier.objects.filter(pk=supplier.pk).exists()
