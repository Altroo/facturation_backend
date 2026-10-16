"""Publish clear update and AI failure feedback without changing business data."""
from django.db import migrations


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias)
    entry = entries.filter(date="2026-10-16").first()
    if not entry:
        return
    additions = {
        "changes_fr": "Les erreurs de mise à jour et de l’assistant IA sont expliquées à l’écran. Une confirmation échouée reste ouverte et n’est jamais indiquée comme réussie ; les requêtes et réponses invalides sont traitées sans interrompre la page.",
        "changes_en": "Update and AI assistant errors are explained on screen. Failed confirmations remain open and are never marked successful; failed requests and invalid responses are handled without interrupting the page.",
    }
    changes = {}
    for field, line in additions.items():
        existing = getattr(entry, field).splitlines()
        if line not in existing:
            changes[field] = "\n".join([*existing, line])
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 6):
        changes["version"] = "3.8.6"
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("ws", "0011_logistics_history_dates_release_3_8_5")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
