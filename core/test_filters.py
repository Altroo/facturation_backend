import json
from datetime import UTC, date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from account.filters import UsersFilter
from account.models import CustomUser, Membership, Role
from article.filters import ArticleFilter
from article.models import Article
from client.filters import ClientFilter
from client.models import Client
from company.filters import CompanyFilter
from company.models import Company

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "zone,selected_day,hours",
    [
        ["UTC", "2026-10-21", 24],
        ["Africa/Casablanca", "2026-10-21", 24],
        ["Europe/Paris", "2026-03-29", 23],
        ["Europe/Paris", "2026-10-25", 25],
        ["Africa/Casablanca", "2026-02-15", 25],
        ["Africa/Casablanca", "2026-03-22", 23],
    ],
)
@pytest.mark.parametrize("bounds", ["after", "before", "range"])
@pytest.mark.parametrize(
    "model,filterset,field,attributes",
    [
        (Company, CompanyFilter, "date_created", {"ICE": "DATE"}),
        (CustomUser, UsersFilter, "date_joined", {"email": "joined@example.test"}),
        (CustomUser, UsersFilter, "last_login", {"email": "login@example.test"}),
        (Client, ClientFilter, "date_created", {"code_client": "DATE"}),
        (Article, ArticleFilter, "date_created", {"reference": "DATE"}),
    ],
)
def test_calendar_range_includes_full_final_day(
    zone, selected_day, hours, bounds, model, filterset, field, attributes
):
    with timezone.override(zone):
        if model in (Client, Article):
            attributes = {**attributes, "company": Company.objects.create(ICE="OWNER")}
        record = model.objects.create(**attributes)
        day = date.fromisoformat(selected_day)
        start = timezone.make_aware(datetime.combine(day, time.min))
        end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
        assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=hours)
        data = {}
        if bounds in ("after", "range"):
            data[f"{field}_after"] = selected_day
        if bounds in ("before", "range"):
            data[f"{field}_before"] = selected_day
        moments = [
            start.astimezone(UTC) - timedelta(microseconds=1),
            start,
            timezone.make_aware(datetime.combine(day, time(12))),
            end.astimezone(UTC) - timedelta(microseconds=1),
            end,
        ]
        included = {"after": {1, 2, 3, 4}, "before": {0, 1, 2, 3}, "range": {1, 2, 3}}[
            bounds
        ]
        for index, moment in enumerate(moments):
            model.objects.filter(pk=record.pk).update(**{field: moment})
            filters = filterset(data, queryset=model.objects.filter(pk=record.pk))
            assert filters.is_valid(), filters.errors
            assert filters.qs.exists() is (index in included), (zone, field, moment)


def test_or_keeps_a_date_range_together_with_other_filter_rows():
    company = Company.objects.create(raison_sociale="Range", ICE="RANGE")
    other = Company.objects.create(raison_sociale="Named match", ICE="OTHER")
    outside = Company.objects.create(raison_sociale="Outside", ICE="OUTSIDE")
    with timezone.override("UTC"):
        Company.objects.filter(pk=company.pk).update(
            date_created=timezone.make_aware(datetime(2026, 3, 15, 18))
        )
        Company.objects.filter(pk__in=[other.pk, outside.pk]).update(
            date_created=timezone.make_aware(datetime(2026, 5, 1))
        )
        filters = CompanyFilter(
            {
                "filter_logic": "or",
                "filter_groups": json.dumps(
                    [
                        {
                            "date_created_after": "2026-03-01",
                            "date_created_before": "2026-03-31",
                        },
                        {"raison_sociale": "Named match"},
                    ]
                ),
            },
            queryset=Company.objects.all(),
        )
        assert set(filters.qs.values_list("pk", flat=True)) == {company.pk, other.pk}


def test_or_allows_two_values_for_the_same_field_and_preserves_default_and():
    first = CustomUser.objects.create(
        email="one@example.test", first_name="First", is_active=True
    )
    second = CustomUser.objects.create(
        email="two@example.test", first_name="Second", is_active=False
    )
    CustomUser.objects.create(email="other@example.test", first_name="Other")
    filters = UsersFilter(
        {
            "filter_logic": "or",
            "filter_groups": json.dumps(
                [{"first_name": "First"}, {"first_name": "Second"}]
            ),
        },
        queryset=CustomUser.objects.all(),
    )
    assert set(filters.qs.values_list("pk", flat=True)) == {first.pk, second.pk}
    filters = UsersFilter(
        {"first_name": "First", "is_active": "false"}, queryset=CustomUser.objects.all()
    )
    assert not filters.qs.exists()


def test_or_stays_inside_company_archive_search_and_pagination_constraints():
    company = Company.objects.create(raison_sociale="Allowed", ICE="ALLOWED")
    other = Company.objects.create(raison_sociale="Other", ICE="FOREIGN")
    user = CustomUser.objects.create_user(
        email="filter-owner@example.test", password="test"
    )
    role, _ = Role.objects.get_or_create(name="Caissier")
    Membership.objects.create(company=company, user=user, role=role)
    first = Client.objects.create(
        company=company,
        code_client="ONE",
        raison_sociale="Needle Alpha",
        client_type="PM",
    )
    second = Client.objects.create(
        company=company,
        code_client="TWO",
        raison_sociale="Needle Beta",
        client_type="PM",
    )
    Client.objects.create(
        company=company,
        code_client="THREE",
        raison_sociale="No match",
        client_type="PM",
    )
    Client.objects.create(
        company=company,
        code_client="ONE-ARCHIVED",
        raison_sociale="Needle archived",
        client_type="PM",
        archived=True,
    )
    Client.objects.create(
        company=other,
        code_client="ONE",
        raison_sociale="Needle foreign",
        client_type="PM",
    )
    api = APIClient()
    api.force_authenticate(user)
    params = {
        "company_id": company.pk,
        "archived": "false",
        "search": "Needle",
        "pagination": "true",
        "page_size": 1,
        "filter_logic": "or",
        "filter_groups": json.dumps(
            [{"code_client__istartswith": "ONE"}, {"code_client": "TWO"}]
        ),
    }
    first_page = api.get("/api/client/", params)
    assert first_page.status_code == 200, first_page.data
    assert first_page.data["count"] == 2
    second_page = api.get("/api/client/", {**params, "page": 2})
    assert second_page.status_code == 200, second_page.data
    assert {
        row["id"] for row in first_page.data["results"] + second_page.data["results"]
    } == {first.pk, second.pk}


@pytest.mark.parametrize(
    "groups",
    [
        "bad json",
        "{}",
        "[]",
        "[{}]",
        '[{"unknown": "x"}]',
        '[{"date_created_before": "bad date"}]',
    ],
)
def test_or_rejects_invalid_groups_instead_of_returning_unfiltered_records(groups):
    filters = CompanyFilter(
        {"filter_logic": "or", "filter_groups": groups}, queryset=Company.objects.all()
    )
    with pytest.raises(ValidationError):
        _ = filters.qs
