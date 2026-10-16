"""Record the supplier logistics release without replacing same-day notes.

The matching frontend must be healthy before announcing this version through
WsMaintenanceState. This migration only records the bilingual changelog.
"""

from django.db import migrations


RELEASE = {
    "date": "2026-10-16",
    "version": "3.8.0",
    "title_fr": "Achats fournisseurs et suivi logistique",
    "title_en": "Supplier purchases and logistics tracking",
    "changes_fr": [
        "Création de dossiers d’achat fournisseur indépendants des proformas de vente, avec contrôle des articles, quantités et prix d’achat.",
        "Sept conditions d’achat avec échéances de paiement calculées automatiquement, suivi des avances, des soldes et des justificatifs bancaires.",
        "Lecture automatique du titre d’importation pour préremplir ses informations, à vérifier avant enregistrement.",
        "Suivi de la préparation fournisseur, de l’expédition, du transit et des réceptions partielles ou complètes.",
        "Contacts fournisseurs avec adresse e-mail et historique détaillé des modifications, paiements et réceptions.",
        "Formulaires logistiques harmonisés avec l’application : champs de date, typographie, boutons et affichage mobile.",
        "Retrait du formulaire temporaire de validation des champs après sauvegarde des réponses. Les dossiers existants conservent leur fonctionnement.",
        "Amélioration de la gestion des sessions expirées et des connexions en temps réel."
    ],
    "changes_en": [
        "Create supplier purchase dossiers independently of sales proformas, with checks on items, quantities and purchase prices.",
        "Seven purchase terms with automatically calculated payment installments, advance and balance tracking, and bank payment documents.",
        "Automatically read import titles to prefill their details for review before saving.",
        "Track supplier preparation, shipment, transit, and partial or complete goods receipts.",
        "Supplier contacts with email addresses and a detailed history of changes, payments and receipts.",
        "Logistics forms now follow the application’s design for date fields, typography, buttons and mobile layouts.",
        "Removed the temporary field review form after backing up its responses. Existing dossiers keep their established workflow.",
        "Improved expired-session handling and real-time connections."
    ]
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
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 0):
        updates.update({key: RELEASE[key] for key in ("version", "title_fr", "title_en")})
    if updates:
        entries.filter(pk=entry.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("ws", "0005_number_changelog_history")]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
