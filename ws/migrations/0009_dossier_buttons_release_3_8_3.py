"""Record the historical logistics action-button correction."""

from django.db import migrations


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    )
    entry = entries.filter(date="2026-10-16").first()
    if not entry:
        return
    additions = {
        "changes_fr": "Boutons des dossiers logistiques harmonisés avec les actions habituelles de l’application, y compris pour les dossiers historiques.",
        "changes_en": "Logistics dossier buttons now follow the standard application action style, including historical dossiers.",
    }
    changes = {}
    for field, line in additions.items():
        existing = getattr(entry, field).splitlines()
        if line not in existing:
            changes[field] = "\n".join([*existing, line])
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 3):
        changes["version"] = "3.8.3"
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("ws", "0008_supplier_mobile_release_3_8_2")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
