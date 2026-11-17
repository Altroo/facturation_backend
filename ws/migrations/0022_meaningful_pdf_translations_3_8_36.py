from django.db import migrations


def record_release(apps, schema_editor):
    apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    ).update_or_create(
        date="2026-11-17",
        platform="web",
        defaults={
            "version": "3.8.36",
            "title_fr": "Traductions professionnelles et mise en page préservée",
            "title_en": "Natural translations with preserved formatting",
            "changes_fr": "Traductions anglais et néerlandais tenant compte du sens et du vocabulaire métier.\nRetours à la ligne, listes à puces, noms, références, dimensions et montants conservés.\nCorrection grammaticale et reformulation professionnelle améliorées.\nPréparation asynchrone des nouveaux contenus et renouvellement progressif des traductions existantes, avec priorité aux PDF demandés.\nIndicateur de chargement et message d’attente clair lorsque le document est encore en préparation.",
            "changes_en": "Meaning-aware English and Dutch translations using business terminology.\nPreserve line breaks, bullet lists, names, references, dimensions and amounts.\nImproved grammar correction and professional rewriting.\nPrepare new content asynchronously and progressively refresh existing translations, prioritizing requested PDFs.\nLoading feedback and a clear queued message while a document is awaiting preparation.",
            "is_published": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("ws", "0021_offline_pdf_translations_3_8_35")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
