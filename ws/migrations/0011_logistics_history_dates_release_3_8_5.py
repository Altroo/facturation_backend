"""Record dates for historical before/after values without changing dossier data."""
from django.db import migrations


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias)
    entry = entries.filter(date="2026-10-16").first()
    if not entry:
        return
    additions = {
        "changes_fr": "L’historique logistique affiche la date et l’heure de début des valeurs avant et après chaque changement. Les dates manquantes sont signalées sans être estimées.",
        "changes_en": "Logistics history shows when before and after values began, including date and time. Missing dates are identified without estimation.",
    }
    changes = {}
    for field, line in additions.items():
        existing = getattr(entry, field).splitlines()
        if line not in existing:
            changes[field] = "\n".join([*existing, line])
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 5):
        changes["version"] = "3.8.5"
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("ws", "0010_supplier_workflow_compatibility_release_3_8_4")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
