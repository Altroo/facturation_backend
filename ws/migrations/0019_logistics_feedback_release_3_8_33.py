"""Record the logistics corrections; announce the version after frontend deployment."""

from django.db import migrations

RELEASE = {
    "date": "2026-11-12",
    "version": "3.8.33",
    "title_fr": "Corrections logistiques et listes personnalisables",
    "title_en": "Logistics corrections and editable lists",
    "changes_fr": [
        "Références des dossiers au format COM, saisie des dates conservée et création d’article dans une fenêtre sans perdre le formulaire.",
        "Prix d’achat repris de l’article, quantités sans zéros inutiles et origine et nature préremplies à partir de l’emplacement et de la marque.",
        "Incoterms, origines et natures de marchandise gérés dans des listes avec ajout, modification et suppression. Une valeur déjà utilisée ne peut pas être supprimée, y compris dans les listes de paramètres existantes.",
        "Incoterms 2020 et catalogue des fournisseurs et marques CASA DI LUSSO intégrés avec les corrections Marazzi Group, Iris Ceramica Group et Delta Light.",
        "Validation directe de la proforma, erreurs de pièces jointes visibles près du champ et en haut du formulaire, avec défilement automatique.",
        "Période de validité du titre d’importation avec dates du et au. Les demandes comptables des deux étapes de paiement incluent les PDF de proforma et du titre d’importation.",
        "Étapes de paiement actualisées en temps réel après validation comptable et alertes de délai après 24 heures révolues.",
        "Transit et clôture en MAD, retrait de la phase et de la TVA, frais facultatifs par virement et en espèces, et montant d’achat en MAD renseigné par le comptable.",
        "Totaux avec et sans espèces, justificatifs bancaires regroupés dans les pièces jointes, bon de réception et archive des documents par étape sur les dossiers clôturés.",
        "Marque obligatoire pour les articles. Des prix d’achat et de vente identiques, notamment 1 676,80, sont acceptés avec les contrôles de devise et de TVA.",
    ],
    "changes_en": [
        "COM dossier references, retained typed dates, and article creation in a dialog without losing form entries.",
        "Purchase prices filled from articles, quantities without unnecessary zeros, and origin and nature defaults from the warehouse and brand.",
        "Editable Incoterm, goods origin and goods nature lists with add, edit and delete controls. Values already in use cannot be deleted, including existing parameter lists.",
        "Seeded Incoterms 2020 and the CASA DI LUSSO supplier and brand catalog with the corrected Marazzi Group, Iris Ceramica Group and Delta Light associations.",
        "Direct proforma validation and attachment errors shown beside the field and at the top of the form with automatic scrolling.",
        "Import title validity start and end dates. Both accounting payment requests include the proforma and import title PDF attachments.",
        "Payment steps update in real time after accounting validation, and delay alerts wait for a full 24 hours.",
        "Transit and closure costs in MAD, phase and VAT removed, optional bank transfer and cash expenses, and a manually converted purchase amount entered by accounting.",
        "Totals with and without cash, bank proofs in attachments, goods receipt attachments, and a document archive by step for closed dossiers.",
        "Required article brands. Equal purchase and sale prices, including 1,676.80, are accepted with currency and VAT checks.",
    ],
}


def record_release(apps, schema_editor):
    entries = apps.get_model("ws", "ChangelogEntry").objects.using(
        schema_editor.connection.alias
    )
    defaults = {
        key: value
        for key, value in RELEASE.items()
        if key not in ("date", "changes_fr", "changes_en")
    }
    defaults.update(
        {field: "\n".join(RELEASE[field]) for field in ("changes_fr", "changes_en")}
    )
    entry, created = entries.get_or_create(
        date=RELEASE["date"],
        platform="web",
        defaults={**defaults, "is_published": True},
    )
    if created:
        return
    changes = {}
    for field in ("changes_fr", "changes_en"):
        existing = getattr(entry, field).splitlines()
        additions = [line for line in RELEASE[field] if line not in existing]
        if additions:
            changes[field] = "\n".join([*existing, *additions])
    if not entry.version or tuple(map(int, entry.version.split("."))) < (3, 8, 33):
        changes.update(
            {key: RELEASE[key] for key in ("version", "title_fr", "title_en")}
        )
    if changes:
        entries.filter(pk=entry.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [
        ("ws", "0018_mobile_version_sequence"),
        ("logistique", "0027_managed_parameters_and_supplier_catalog"),
    ]
    operations = [migrations.RunPython(record_release, migrations.RunPython.noop)]
