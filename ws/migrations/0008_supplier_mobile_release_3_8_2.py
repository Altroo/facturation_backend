"""Record the supplier detail layout correction after the directory release."""

from django.db import migrations


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    )
    entry = entries.filter(date="2026-10-16").first()
    if not entry:
        return
    additions = {
        "changes_fr": "Fiche fournisseur adaptée aux petits écrans : le nom et l’e-mail restent lisibles, avec chaque valeur sous son libellé.",
        "changes_en": "Supplier details now fit small screens: the name and email stay readable, with each value below its label.",
    }
    changes = {}
    for field, line in additions.items():
        existing = getattr(entry, field).splitlines()
        if line not in existing:
            changes[field] = "\n".join([*existing, line])
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 2):
        changes["version"] = "3.8.2"
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("ws", "0007_supplier_grid_release_3_8_1")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
