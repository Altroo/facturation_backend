"""Record the existing-dossier supplier workflow and payment-method corrections."""

from django.db import migrations


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(schema_editor.connection.alias)
    entry = entries.filter(date="2026-10-16").first()
    if not entry:
        return
    additions = {
        "changes_fr": [
            "Les dossiers encore en attente de contrôle fournisseur peuvent reprendre le parcours validé, en conservant leurs documents et leur historique. Les quantités et les prix sont confirmés depuis la proforma fournisseur.",
            "La méthode du paiement réellement effectué peut être choisie par le comptable ; la banque et la devise restent reprises du dossier.",
            "Les références client et projet ainsi que le bloc de proforma de vente ont été retirés des écrans de suivi concernés.",
        ],
        "changes_en": [
            "Dossiers still awaiting supplier review can adopt the approved workflow while preserving their documents and history. Quantities and purchase prices are confirmed from the supplier pro forma.",
            "Accountants can select the actual payment method; bank and currency remain derived from the dossier.",
            "Client and project columns and the sales pro forma block have been removed from the relevant tracking screens.",
        ],
    }
    changes = {}
    for field, lines in additions.items():
        existing = getattr(entry, field).splitlines()
        merged = [*existing, *(line for line in lines if line not in existing)]
        if merged != existing:
            changes[field] = "\n".join(merged)
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 4):
        changes["version"] = "3.8.4"
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("ws", "0009_dossier_buttons_release_3_8_3")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
