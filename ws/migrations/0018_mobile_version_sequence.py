import json
from pathlib import Path

from django.db import migrations


def reconstruct_mobile_versions(apps, schema_editor):
    data_dir = Path(__file__).parent / "data"
    history = json.loads((data_dir / "0018_mobile_version_sequence.json").read_text(encoding="utf-8"))
    previous = {
        release["date"]: release
        for release in json.loads((data_dir / "0017_mobile_changelog_history.json").read_text(encoding="utf-8"))
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
        # Only renumber generated history. Keep administrator-written notes,
        # custom versions and publication choices, plus all web/shared entries.
        if old and entry.version == old["version"] and all(
            getattr(entry, field) == ("\n".join(old[field]) if field.startswith("changes_") else old[field])
            for field in ("title_fr", "title_en", "changes_fr", "changes_en")
        ):
            entries.filter(pk=entry.pk).update(version=release["version"])

    maintenance = apps.get_model("ws", "WsMaintenanceState").objects.using(schema_editor.connection.alias)
    maintenance.filter(version_mobile__in=("3.8.26", "3.8.27")).update(version_mobile=history[-1]["version"])


class Migration(migrations.Migration):
    dependencies = [("ws", "0017_independent_mobile_history")]
    operations = [migrations.RunPython(reconstruct_mobile_versions, migrations.RunPython.noop)]
