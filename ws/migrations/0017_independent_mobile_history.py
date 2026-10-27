import json
from pathlib import Path

from django.db import migrations


def seed_independent_mobile_history(apps, schema_editor):
    data_dir = Path(__file__).parent / "data"
    history = json.loads((data_dir / "0017_mobile_changelog_history.json").read_text(encoding="utf-8"))
    previous = {
        entry["date"]: entry
        for entry in json.loads((data_dir / "0014_mobile_changelog_history.json").read_text(encoding="utf-8"))
    }
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias)
    for release in history:
        values = {
            **{key: value for key, value in release.items() if key != "date"},
            "changes_fr": "\n".join(release["changes_fr"]),
            "changes_en": "\n".join(release["changes_en"]),
        }
        entry, created = entries.get_or_create(
            date=release["date"], platform="mobile", defaults={**values, "is_published": True}
        )
        if created:
            continue
        old = previous.get(release["date"])
        # Replace only the old generated notes, preserving administrator edits,
        # publication choices, and all web/shared history.
        if old and entry.version in (old["version"], "3.8.4") and all(
            getattr(entry, field) == ("\n".join(old[field]) if field.startswith("changes_") else old[field])
            for field in ("title_fr", "title_en", "changes_fr", "changes_en")
        ):
            entries.filter(pk=entry.pk).update(**values)

    maintenance = apps.get_model("ws", "WsMaintenanceState").objects.using(schema_editor.connection.alias)
    maintenance.filter(version_mobile="0.1.0").update(version_mobile="3.8.26")


class Migration(migrations.Migration):
    dependencies = [("ws", "0016_mobile_release_version")]
    operations = [migrations.RunPython(seed_independent_mobile_history, migrations.RunPython.noop)]
