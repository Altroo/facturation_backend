import json
from pathlib import Path

from django.db import migrations


def seed_mobile_changelog(apps, schema_editor):
    entries = json.loads(
        (Path(__file__).parent / "data" / "0014_mobile_changelog_history.json").read_text(encoding="utf-8")
    )
    model = apps.get_model("ws", "ChangelogEntry")
    for entry in entries:
        # Daily notes follow native commits within the shared web release sequence.
        # The evidence is recorded in docs/mobile-changelog-history-sources.json.
        model.objects.using(schema_editor.connection.alias).get_or_create(
            date=entry["date"],
            platform="mobile",
            defaults={
                **{key: value for key, value in entry.items() if key != "date"},
                "changes_fr": "\n".join(entry["changes_fr"]),
                "changes_en": "\n".join(entry["changes_en"]),
                "is_published": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("ws", "0013_changelog_platform")]
    operations = [migrations.RunPython(seed_mobile_changelog, migrations.RunPython.noop)]
