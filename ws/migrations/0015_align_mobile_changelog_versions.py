import json
from pathlib import Path

from django.db import migrations


def align_mobile_versions(apps, schema_editor):
    history = json.loads(
        (Path(__file__).parent / "data" / "0014_mobile_changelog_history.json").read_text(encoding="utf-8")
    )
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias)
    for entry in history:
        # Repair only the stale native package version copied by the first seed.
        # Web/shared entries, edited versions and all release text stay intact.
        entries.filter(date=entry["date"], platform="mobile", version="3.8.4").update(version=entry["version"])


class Migration(migrations.Migration):
    dependencies = [("ws", "0014_seed_mobile_changelog_history")]
    operations = [migrations.RunPython(align_mobile_versions, migrations.RunPython.noop)]
