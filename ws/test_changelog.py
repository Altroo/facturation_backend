from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ChangelogEntry
from .serializers import ChangelogEntrySerializer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def empty_changelog():
    ChangelogEntry.objects.all().delete()


def entry(**kwargs):
    values = dict(
        date=timezone.localdate(),
        title_fr="Travail partagé",
        title_en="Shared work",
        changes_fr="  Une nouveauté.\n\nUne amélioration. ",
        changes_en=" A new feature.\n\nAn improvement. ",
        is_published=True,
    )
    return ChangelogEntry.objects.create(**(values | kwargs))


def test_authenticated_members_get_complete_bilingual_published_history_only():
    today = timezone.localdate()
    entry(date=today - timedelta(days=3))
    newest = entry(version="1.0.0")
    entry(date=today - timedelta(days=1), is_published=False, title_fr="DRAFT SECRET")
    entry(date=today + timedelta(days=1), title_fr="FUTURE SECRET")
    client = APIClient()
    client.force_authenticate(
        get_user_model().objects.create_user(
            email="changelog@example.com", password="test-only"
        )
    )
    response = client.get("/api/ws/changelog/")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert len(response.data) == 2
    assert response.data[0]["id"] == newest.pk
    assert response.data[0]["version"] == "1.0.0"
    assert response.data[1]["version"] == ""
    assert response.data[0]["changes_fr"] == ["Une nouveauté.", "Une amélioration."]
    assert response.data[0]["changes_en"] == ["A new feature.", "An improvement."]
    assert "SECRET" not in str(response.data)
    assert client.post("/api/ws/changelog/", {}).status_code == 405


def test_history_requires_authentication():
    assert APIClient().get("/api/ws/changelog/").status_code in (401, 403)


@pytest.mark.parametrize("platform", [None, "web", "mobile"])
def test_platform_filter_includes_shared_entries_only(platform):
    web = entry(platform="web")
    mobile = entry(platform="mobile")
    shared = entry(platform="both")
    entry(platform="mobile", date=timezone.localdate() + timedelta(days=1))
    entry(platform="both", date=timezone.localdate() - timedelta(days=1), is_published=False)
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user(email="platform@example.com", password="test-only"))
    response = client.get("/api/ws/changelog/", {"platform": platform} if platform else {})
    assert response.status_code == 200
    expected = mobile if platform == "mobile" else web
    assert [item["id"] for item in response.data] == [shared.pk, expected.pk]
    assert response.data[0]["platform"] == "both"


def test_unknown_platform_is_rejected_instead_of_exposing_all_entries():
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user(email="invalid-platform@example.com", password="test-only"))
    assert client.get("/api/ws/changelog/", {"platform": "both"}).status_code == 400
    assert client.get("/api/ws/changelog/", {"platform": "android"}).status_code == 400


def test_releases_can_share_a_date_across_platforms_but_not_within_one_platform():
    web = entry()
    assert web.platform == "web"
    entry(platform="mobile").full_clean()
    duplicate = ChangelogEntry(date=web.date, platform="web")
    with pytest.raises(ValidationError):
        duplicate.full_clean()


@pytest.mark.django_db(transaction=True)
def test_platform_migration_preserves_existing_history_as_web():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    previous = [("ws", "0012_handled_errors_release_3_8_6")]
    current = [("ws", "0015_align_mobile_changelog_versions")]
    executor = MigrationExecutor(connection)
    executor.migrate(previous)
    try:
        old_entry = executor.loader.project_state(previous).apps.get_model("ws", "ChangelogEntry")
        old_entry.objects.create(
            date="2026-10-26", version="1.2.0", title_fr="Titre conservé",
            title_en="Preserved title", changes_fr="Texte conservé", changes_en="Preserved text",
            is_published=True,
        )
    finally:
        MigrationExecutor(connection).migrate(current)
    preserved = ChangelogEntry.objects.get(date="2026-10-26", platform="web")
    assert preserved.platform == "web"
    assert preserved.title_fr == "Titre conservé"
    assert preserved.changes_en == "Preserved text"
    assert preserved.version == "1.2.0"
    assert preserved.is_published


def test_mobile_history_is_bilingual_idempotent_and_preserves_web_and_admin_edits():
    from importlib import import_module
    from django.apps import apps
    from django.db import connection

    web = entry(date="2026-10-26", title_fr="Texte web conservé")
    seed = import_module("ws.migrations.0014_seed_mobile_changelog_history")
    seed.seed_mobile_changelog(apps, connection.schema_editor())
    rows = ChangelogEntry.objects.filter(platform="mobile")
    assert rows.count() == 7
    assert {str(row.date) for row in rows} == {
        "2026-10-16", "2026-10-20", "2026-10-21", "2026-10-22",
        "2026-10-23", "2026-10-24", "2026-10-26",
    }
    for row in rows:
        row.full_clean()
        assert len(row.changes_fr.splitlines()) == len(row.changes_en.splitlines())
    versions = [tuple(map(int, row.version.split("."))) for row in rows.order_by("date")]
    assert versions == sorted(versions)
    assert len(set(versions)) > 1
    edited = rows.first()
    edited.title_fr = "Titre mobile conservé"
    edited.is_published = False
    edited.save()
    seed.seed_mobile_changelog(apps, connection.schema_editor())
    edited.refresh_from_db()
    web.refresh_from_db()
    assert edited.title_fr == "Titre mobile conservé"
    assert not edited.is_published
    assert web.title_fr == "Texte web conservé"
    assert ChangelogEntry.objects.count() == 8


def test_align_mobile_versions_repairs_legacy_seed_without_overwriting_other_releases():
    import json
    from importlib import import_module
    from pathlib import Path
    from django.apps import apps
    from django.db import connection

    history = json.loads((Path(__file__).parent / "migrations/data/0014_mobile_changelog_history.json").read_text())
    web = entry(date=history[-1]["date"], version="3.8.4", platform="web")
    shared = entry(date=history[-1]["date"], version="3.8.4", platform="both")
    seed = import_module("ws.migrations.0014_seed_mobile_changelog_history")
    repair = import_module("ws.migrations.0015_align_mobile_changelog_versions")
    editor = connection.schema_editor()
    seed.seed_mobile_changelog(apps, editor)
    mobile = ChangelogEntry.objects.filter(platform="mobile")
    mobile.update(version="3.8.4")
    edited = mobile.order_by("date").first()
    edited.version = "9.9.9"
    edited.save()
    latest = mobile.get(date=history[-1]["date"])
    latest.title_fr = "Texte personnalisé"
    latest.is_published = False
    latest.save()
    repair.align_mobile_versions(apps, editor)
    repair.align_mobile_versions(apps, editor)
    for release in history:
        row = mobile.get(date=release["date"])
        assert row.version == ("9.9.9" if row.pk == edited.pk else release["version"])
    web.refresh_from_db()
    shared.refresh_from_db()
    latest.refresh_from_db()
    assert web.version == shared.version == "3.8.4"
    assert latest.title_fr == "Texte personnalisé"
    assert not latest.is_published


def test_publication_requires_both_languages():
    draft = entry(title_en="", changes_en=" ", is_published=False)
    draft.full_clean()
    draft.is_published = True
    with pytest.raises(ValidationError):
        draft.full_clean()


@pytest.mark.parametrize("version", ["1", "01.0.0", "1.0.0-beta", "1.0.0\\n"])
def test_invalid_versions_are_rejected(version):
    with pytest.raises(ValidationError):
        entry(version=version).full_clean()


def test_complete_history_is_bilingual_idempotent_and_preserves_edits():
    import json
    from importlib import import_module
    from pathlib import Path
    from django.apps import apps
    from django.db import connection

    seed = import_module("ws.migrations.0004_seed_changelog_history")
    editor = connection.schema_editor()
    seed.seed_changelog(apps, editor)
    rows = list(ChangelogEntry.objects.order_by("date"))
    assert len(rows) == 150
    assert str(rows[0].date) == "2025-10-24"
    assert str(rows[-1].date) == "2026-10-09"
    source = json.loads(
        (Path(__file__).parents[1] / "docs/changelog-history-sources.json").read_text()
    )
    assert {commit["date"] for commit in source["commits"]} == {
        str(row.date) for row in rows
    }
    assert len(source["commits"]) == 995
    for row in rows:
        row.full_clean()
        assert len(row.changes_fr.splitlines()) == len(row.changes_en.splitlines())
        assert row.version
    versions = [tuple(map(int, row.version.split("."))) for row in rows]
    assert versions == sorted(set(versions))
    assert rows[-1].version == "3.6.0"
    assert ChangelogEntry.objects.get(date="2026-01-22").version == "1.0.0"
    assert ChangelogEntry.objects.get(date="2026-06-18").version.startswith("1.")
    assert ChangelogEntry.objects.get(date="2026-07-04").version == "2.0.0"
    assert ChangelogEntry.objects.get(date="2026-09-19").version == "3.0.0"
    assert len(source["versioning"]["subsequent_feature_dates"]) == 6
    first = rows[0]
    first.title_fr = "Titre conservé"
    first.is_published = False
    first.save()
    seed.seed_changelog(apps, editor)
    first.refresh_from_db()
    assert first.title_fr == "Titre conservé"
    assert not first.is_published
    assert ChangelogEntry.objects.count() == 150


def test_maintenance_version_bootstrap_and_broadcast(
    django_capture_on_commit_callbacks,
):
    from unittest.mock import AsyncMock, patch
    from .models import WsMaintenanceState

    with patch("ws.models.get_channel_layer") as layer:
        layer.return_value.group_send = AsyncMock()
        with django_capture_on_commit_callbacks(execute=True):
            WsMaintenanceState.objects.create(maintenance=False, version="0.2.0")
            layer.return_value.group_send.assert_not_called()
        layer.return_value.group_send.assert_awaited_once_with(
            "maintenance",
            {
                "type": "receive_group_message",
                "message": {
                    "type": "MAINTENANCE",
                    "maintenance": False,
                    "version": "0.2.0",
                },
            },
        )
    response = APIClient().get("/api/ws/maintenance/")
    assert response.data == {"maintenance": False, "version": "0.2.0"}
    assert response["Cache-Control"] == "no-store"
