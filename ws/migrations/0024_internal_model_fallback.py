from django.db import migrations


def record_release(apps, schema_editor):
    entry, _ = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    ).get_or_create(
        date="2026-11-20",
        platform="web",
        defaults={
            "version": "3.8.38",
            "title_fr": "Traduction et correction avec les modèles internes",
            "title_en": "Internal fallback for translation and editing",
            "changes_fr": (
                "Lorsque Groq atteint sa limite, les modèles internes prennent le relais "
                "pour la traduction, la correction et la reformulation professionnelle.\n"
                "Les traductions PDF bloquées par un quota reprennent. Si la préparation "
                "prend plus de 45 secondes, elle se poursuit en arrière-plan.\n"
                "Les délais d’attente s’affichent en heures, minutes et secondes."
            ),
            "changes_en": (
                "When Groq reaches its quota, internal models handle translation, spelling "
                "and grammar correction, and professional rewriting.\n"
                "PDF translations held by quota limits resume. Preparation continues "
                "in the background if the wait exceeds 45 seconds.\n"
                "Retry delays appear in hours, minutes, and seconds."
            ),
            "is_published": False,
        },
    )
    if entry.version != "3.8.38":
        raise ValueError("Another changelog entry already exists for this release date")


class Migration(migrations.Migration):
    dependencies = [("ws", "0023_direct_french_pdf_release")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
