from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection

from ws.models import ChangelogEntry, WsMaintenanceState


@pytest.mark.django_db
def test_logistics_release_merges_notes_idempotently_without_announcing_early():
    migration = import_module("ws.migrations.0019_logistics_feedback_release_3_8_33")
    ChangelogEntry.objects.filter(date="2026-11-12").delete()
    entry = ChangelogEntry.objects.create(
        date="2026-11-12",
        platform="web",
        version="3.8.32",
        title_fr="Note existante",
        title_en="Existing note",
        changes_fr="Note manuelle",
        changes_en="Manual note",
        is_published=True,
    )
    mobile = ChangelogEntry.objects.create(
        date="2026-11-12", platform="mobile", version="1.0.0"
    )
    state = WsMaintenanceState.objects.create(
        version="3.8.32", version_mobile="1.0.0", maintenance=False
    )
    with connection.schema_editor() as editor:
        migration.record_release(apps, editor)
        migration.record_release(apps, editor)
    entry.refresh_from_db()
    mobile.refresh_from_db()
    state.refresh_from_db()
    assert entry.version == "3.8.33"
    assert entry.changes_fr.splitlines()[0] == "Note manuelle"
    assert entry.changes_en.splitlines()[0] == "Manual note"
    for field in ("changes_fr", "changes_en"):
        assert (
            len(getattr(entry, field).splitlines()) == len(migration.RELEASE[field]) + 1
        )
    assert state.version == "3.8.32" and not state.maintenance
    assert mobile.version == "1.0.0"
