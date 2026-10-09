"""Backfill retrospective versions for previously unversioned history.

Product milestones from both Git histories: billing v1 (2026-01-22),
logistics v2 (2026-07-04), integrated stock v3 (2026-09-19).
New capabilities advance minor; other development dates advance patch.
These labels are reconstructed, not historical release tags. See the audit
in docs/changelog-history-sources.json for exact dates and commit evidence.
Do not announce Maintenance.version before the matching frontend is healthy.
"""

import json
from pathlib import Path

from django.db import migrations


def number_history(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    )
    history = json.loads(
        (Path(__file__).parent / "data" / "0004_changelog_history.json").read_text(
            encoding="utf-8"
        )
    )
    for entry in history:
        old_versions = ["", "0.1.0"] if entry["date"] == "2026-10-09" else [""]
        entries.filter(date=entry["date"], version__in=old_versions).update(
            version=entry["version"]
        )


class Migration(migrations.Migration):
    dependencies = [("ws", "0004_seed_changelog_history")]
    operations = [migrations.RunPython(number_history, migrations.RunPython.noop)]
