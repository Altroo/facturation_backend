"""Record the release; announce its version after frontend deployment."""

from django.db import migrations


def record_release(apps, schema_editor):
    apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias).update_or_create(
        date="2026-11-16", platform="web",
        defaults={
            "version": "3.8.34",
            "title_fr": "Traductions PDF préparées en arrière-plan",
            "title_en": "PDF translations prepared in the background",
            "changes_fr": "Traduction automatique des désignations, unités, remarques, termes de paiement et libellés à leur ajout ou modification, sans attendre la traduction lors de l’enregistrement.\nTraductions conservées en base de données et réutilisées directement lors de l’ouverture des PDF.\nTraitement Celery des contenus existants, avec reprise des erreurs et priorité aux documents demandés.\nIndicateur de chargement pendant la préparation des PDF depuis les listes et les pages de détail.",
            "changes_en": "Automatically translate descriptions, units, remarks, payment terms and labels when added or edited without waiting for translation during saves.\nStore translations in the database and reuse them directly when opening PDFs.\nCelery backfill for existing content with failure recovery and priority for requested documents.\nShow loading feedback while preparing PDFs from lists and detail pages.",
            "is_published": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("ws", "0019_logistics_feedback_release_3_8_33"),
        ("ai_assistant", "0002_pdftexttranslation_priority"),
    ]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
