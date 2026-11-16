"""Publish offline PDF translation improvements after frontend deployment."""

from django.db import migrations


def record_release(apps, schema_editor):
    apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias).update_or_create(
        date="2026-11-16", platform="web",
        defaults={
            "version": "3.8.35",
            "title_fr": "Traductions PDF hors ligne et plus rapides",
            "title_en": "Faster offline PDF translations",
            "changes_fr": "Traduction locale plus rapide des contenus PDF en français, anglais et néerlandais.\nNoms, références, montants et retours à la ligne conservés.\nTraitement asynchrone lors des ajouts et modifications et reprise des contenus existants, avec priorité aux PDF demandés.\nUne traduction invalide ne bloque plus les autres champs du lot. Les vérifications de disponibilité ne créent plus de tâches en double.\nIndicateur de chargement pendant la préparation des PDF depuis les listes et les pages de détail.",
            "changes_en": "Faster local translation of PDF content in French, English and Dutch.\nPreserve names, references, amounts and line breaks.\nPrepare added and edited content asynchronously and backfill existing content, prioritizing requested PDFs.\nAn invalid translation no longer blocks other fields in its batch. Readiness checks no longer create duplicate tasks.\nShow loading feedback while preparing PDFs from lists and detail pages.",
            "is_published": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("ws", "0020_background_pdf_translations_3_8_34")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
