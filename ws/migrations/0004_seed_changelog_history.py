import json
from pathlib import Path

from django.db import migrations


def seed_changelog(apps, schema_editor):
    entry_model = apps.get_model("ws", "ChangelogEntry")
    entries = json.loads(
        (Path(__file__).parent / "data" / "0004_changelog_history.json").read_text(
            encoding="utf-8"
        )
    )
    for entry in entries:
        date = entry["date"]
        defaults = {
            **{key: value for key, value in entry.items() if key != "date"},
            "changes_fr": "\n".join(entry["changes_fr"]),
            "changes_en": "\n".join(entry["changes_en"]),
            "is_published": True,
        }
        entry_model.objects.using(schema_editor.connection.alias).get_or_create(
            date=date, defaults=defaults
        )


class Migration(migrations.Migration):
    dependencies = [("ws", "0003_changelogentry_wsmaintenancestate_version")]
    operations = [migrations.RunPython(seed_changelog, migrations.RunPython.noop)]
