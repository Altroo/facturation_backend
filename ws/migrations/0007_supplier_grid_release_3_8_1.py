"""Record the supplier directory correction without replacing same-day notes.

The matching frontend must be healthy before announcing this version through
WsMaintenanceState. This migration only records the bilingual changelog.
"""

from django.db import migrations

RELEASE = {
    "date": "2026-10-16",
    "version": "3.8.1",
    "title_fr": "Achats fournisseurs et suivi logistique",
    "title_en": "Supplier purchases and logistics tracking",
    "changes_fr": [
        "Répertoire fournisseurs avec ajout, consultation, modification et suppression depuis les pages habituelles de l’application. Tableau avec recherche, filtres, pagination et tri sur tous les résultats. Les fournisseurs liés à des dossiers sont protégés contre la suppression."
    ],
    "changes_en": [
        "Supplier directory with add, view, edit and delete using standard application pages. The table supports search, filters, pagination and sorting across all results. Suppliers linked to dossiers cannot be deleted."
    ],
}


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    )
    defaults = {
        **{key: value for key, value in RELEASE.items() if key != "date"},
        "changes_fr": "\n".join(RELEASE["changes_fr"]),
        "changes_en": "\n".join(RELEASE["changes_en"]),
        "is_published": True,
    }
    entry, created = entries.get_or_create(date=RELEASE["date"], defaults=defaults)
    if created:
        return
    updates = {}
    for field in ("changes_fr", "changes_en"):
        existing = getattr(entry, field).splitlines()
        additions = [line for line in RELEASE[field] if line not in existing]
        if additions:
            updates[field] = "\n".join([*existing, *additions])
    # Preserve titles and versions already edited for this or a later release.
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 1):
        updates.update(
            {key: RELEASE[key] for key in ("version", "title_fr", "title_en")}
        )
    if updates:
        entries.filter(pk=entry.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("ws", "0006_logistics_release_3_8_0")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
