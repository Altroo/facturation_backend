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
def test_mobile_history_is_separate_while_web_keeps_its_shared_entries(platform):
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
    assert [item["id"] for item in response.data] == ([mobile.pk] if platform == "mobile" else [shared.pk, expected.pk])
    assert response.data[0]["platform"] == ("mobile" if platform == "mobile" else "both")


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
    current = [("ws", "0018_mobile_version_sequence")]
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
            WsMaintenanceState.objects.create(maintenance=False, version="0.2.0", version_mobile="1.2.3")
            layer.return_value.group_send.assert_not_called()
        layer.return_value.group_send.assert_awaited_once_with(
            "maintenance",
            {
                "type": "receive_group_message",
                "message": {
                    "type": "MAINTENANCE",
                    "maintenance": False,
                    "version": "0.2.0",
                    "version_mobile": "1.2.3",
                },
            },
        )
    response = APIClient().get("/api/ws/maintenance/")
    assert response.data == {"maintenance": False, "version": "0.2.0", "version_mobile": "1.2.3"}
    assert response["Cache-Control"] == "no-store"


def test_independent_mobile_history_uses_native_versions_and_preserves_admin_changes():
    import json
    from importlib import import_module
    from pathlib import Path
    from django.apps import apps
    from django.db import connection
    from .models import WsMaintenanceState

    history = json.loads((Path(__file__).parent / "migrations/data/0017_mobile_changelog_history.json").read_text())
    editor = connection.schema_editor()
    import_module("ws.migrations.0014_seed_mobile_changelog_history").seed_mobile_changelog(apps, editor)
    rebuild = import_module("ws.migrations.0017_independent_mobile_history").seed_independent_mobile_history
    web = entry(date=history[-1]["date"], version="9.9.9")
    maintenance = WsMaintenanceState.objects.create(version="9.9.9")
    edited = ChangelogEntry.objects.get(date=history[2]["date"], platform="mobile")
    edited.title_fr = "Notes personnalisées"
    edited.is_published = False
    edited.save()
    rebuild(apps, editor)
    rebuild(apps, editor)
    for release in history:
        row = ChangelogEntry.objects.get(date=release["date"], platform="mobile")
        if row.pk == edited.pk:
            assert row.title_fr == "Notes personnalisées"
            assert not row.is_published
        else:
            assert row.version == release["version"]
            assert row.changes_fr == "\n".join(release["changes_fr"])
    web.refresh_from_db()
    maintenance.refresh_from_db()
    assert web.version == maintenance.version == "9.9.9"
    assert maintenance.version_mobile == history[-1]["version"]
    maintenance.version_mobile = "8.8.8"
    maintenance.save()
    rebuild(apps, editor)
    maintenance.refresh_from_db()
    assert maintenance.version_mobile == "8.8.8"


def test_reconstructed_mobile_sequence_uses_native_batches_and_leaves_web_unchanged():
    import json
    from importlib import import_module
    from pathlib import Path
    from django.apps import apps
    from django.db import connection
    from .models import WsMaintenanceState

    data_dir = Path(__file__).parent / "migrations/data"
    previous = json.loads((data_dir / "0017_mobile_changelog_history.json").read_text())
    history = json.loads((data_dir / "0018_mobile_version_sequence.json").read_text())
    for release in previous:
        entry(
            **{
                **release,
                "changes_fr": "\n".join(release["changes_fr"]),
                "changes_en": "\n".join(release["changes_en"]),
                "platform": "mobile",
            }
        )
    web = entry(date=history[-1]["date"], version="9.9.9", title_fr="Notes web conservées")
    shared = entry(date=history[-1]["date"], version="9.9.8", platform="both")
    maintenance = WsMaintenanceState.objects.create(version="9.9.9", version_mobile="3.8.26")
    editor = connection.schema_editor()
    rebuild = import_module("ws.migrations.0018_mobile_version_sequence").reconstruct_mobile_versions
    rebuild(apps, editor)
    rebuild(apps, editor)
    versions = list(ChangelogEntry.objects.filter(platform="mobile").order_by("date").values_list("version", flat=True))
    assert versions == ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0", "1.6.1"]
    for release in history:
        row = ChangelogEntry.objects.get(date=release["date"], platform="mobile")
        row.full_clean()
        assert row.changes_fr == "\n".join(release["changes_fr"])
        assert row.changes_en == "\n".join(release["changes_en"])
    web.refresh_from_db()
    shared.refresh_from_db()
    maintenance.refresh_from_db()
    assert web.version == maintenance.version == "9.9.9"
    assert shared.version == "9.9.8"
    assert web.title_fr == "Notes web conservées"
    assert maintenance.version_mobile == history[-1]["version"]


def test_mobile_renumbering_preserves_custom_notes_versions_and_publication_choices():
    import json
    from importlib import import_module
    from pathlib import Path
    from django.apps import apps
    from django.db import connection
    from .models import WsMaintenanceState

    previous = json.loads((Path(__file__).parent / "migrations/data/0017_mobile_changelog_history.json").read_text())
    for release in previous:
        entry(**{**release, "changes_fr": "\n".join(release["changes_fr"]), "changes_en": "\n".join(release["changes_en"]), "platform": "mobile"})
    edited = ChangelogEntry.objects.get(date=previous[0]["date"], platform="mobile")
    edited.changes_fr = "Texte personnalisé"
    edited.save()
    custom_version = ChangelogEntry.objects.get(date=previous[1]["date"], platform="mobile")
    custom_version.version = "8.0.0"
    custom_version.save()
    unpublished = ChangelogEntry.objects.get(date=previous[2]["date"], platform="mobile")
    unpublished.is_published = False
    unpublished.save()
    maintenance = WsMaintenanceState.objects.create(version="9.9.9", version_mobile="8.0.0")
    rebuild = import_module("ws.migrations.0018_mobile_version_sequence").reconstruct_mobile_versions
    rebuild(apps, connection.schema_editor())
    edited.refresh_from_db()
    custom_version.refresh_from_db()
    unpublished.refresh_from_db()
    maintenance.refresh_from_db()
    assert edited.changes_fr == "Texte personnalisé"
    assert edited.version == previous[0]["version"]
    assert custom_version.version == "8.0.0"
    assert not unpublished.is_published
    assert unpublished.version == "1.2.0"
    assert maintenance.version_mobile == "8.0.0"


def test_mobile_history_source_records_the_stock_fix_without_copying_web_versions():
    import json
    from pathlib import Path

    source = json.loads((Path(__file__).parents[1] / "docs/mobile-changelog-history-sources.json").read_text())
    history = json.loads((Path(__file__).parent / "migrations/data/0018_mobile_version_sequence.json").read_text())
    fixes = next(release for release in source["entries"] if release["date"] == "2026-10-27")
    assert fixes["version"] == history[-1]["version"]
    assert source["entries"][-1]["version"] == source["versioning"]["latest_committed_version"]
    assert fixes["date"] in source["versioning"]["fix_dates"]
    assert any(commit["commit"].startswith("04b3d59") for commit in fixes["native_commits"])
    assert fixes["version"] != fixes["native_commits"][-1]["native_package_version"]
    assert len({entry["version"] for entry in source["entries"]}) == len(source["entries"])


def test_mobile_admin_keeps_histories_separate_and_validates_duplicate_dates():
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory
    from .admin import ChangelogEntryAdmin, MobileChangelogEntryAdmin
    from .models import MobileChangelogEntry

    web = entry()
    mobile = entry(platform="mobile")
    shared = entry(platform="both")
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(email="mobile-admin@example.com", password="test-only")
    site = AdminSite()
    web_admin = ChangelogEntryAdmin(ChangelogEntry, site)
    mobile_admin = MobileChangelogEntryAdmin(MobileChangelogEntry, site)
    assert set(web_admin.get_queryset(request).values_list("pk", flat=True)) == {web.pk, shared.pk}
    assert list(mobile_admin.get_queryset(request).values_list("pk", flat=True)) == [mobile.pk]
    form_class = mobile_admin.get_form(request)
    assert form_class.base_fields["platform"].initial == "mobile"
    values = {
        "date": str(web.date), "version": "1.2.3", "platform": "mobile", "title_fr": "Version mobile",
        "title_en": "Mobile release", "changes_fr": "Amélioration", "changes_en": "Improvement", "is_published": True,
    }
    assert not form_class(data=values).is_valid()
    assert not form_class(data={**values, "platform": "web"}).is_valid()
    form = form_class(data={**values, "date": str(web.date - timedelta(days=1))})
    assert form.is_valid(), form.errors
    obj = form.save(commit=False)
    mobile_admin.save_model(request, obj, form, False)
    assert obj.platform == "mobile"


@pytest.mark.parametrize("version", ["invalid", "1.0", "1.0.0-beta"])
def test_mobile_maintenance_version_uses_release_validation(version):
    from .models import WsMaintenanceState
    with pytest.raises(ValidationError, match="version_mobile"):
        WsMaintenanceState(version="1.2.3", version_mobile=version).full_clean()
