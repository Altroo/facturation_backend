from django.db import migrations, models

EVENT_ACTION_RENAMES = {
    "Demande de proforma": "Demande de pro forma fournisseur",
    "Contrôle proforma fournisseur": "Contrôle pro forma fournisseur",
    "Correction proforma demandée": "Correction de la pro forma fournisseur demandée",
    "Validation proforma fournisseur": "Validation de la pro forma fournisseur",
    "Refus proforma fournisseur": "Refus de la pro forma fournisseur",
    "Confirmation réception fournisseur": (
        "Confirmation de la réception de la preuve par le fournisseur"
    ),
}


def rename_event_actions(apps, schema_editor):
    LogisticsOrderEvent = apps.get_model("logistique", "LogisticsOrderEvent")
    for old_action, new_action in EVENT_ACTION_RENAMES.items():
        LogisticsOrderEvent.objects.filter(action=old_action).update(action=new_action)


def restore_event_actions(apps, schema_editor):
    LogisticsOrderEvent = apps.get_model("logistique", "LogisticsOrderEvent")
    for old_action, new_action in EVENT_ACTION_RENAMES.items():
        LogisticsOrderEvent.objects.filter(action=new_action).update(action=old_action)


class Migration(migrations.Migration):
    dependencies = [
        ("logistique", "0010_backfill_supplier_snapshots"),
    ]

    operations = [
        migrations.RunPython(rename_event_actions, restore_event_actions),
        migrations.AlterModelOptions(
            name="historicallogisticsorder",
            options={
                "get_latest_by": ("history_date", "history_id"),
                "ordering": ("-history_date", "-history_id"),
                "verbose_name": "Historique dossier logistique",
                "verbose_name_plural": "Historiques dossiers logistiques",
            },
        ),
        migrations.AlterModelOptions(
            name="logisticsorder",
            options={
                "ordering": ("-date_created",),
                "verbose_name": "Dossier logistique",
                "verbose_name_plural": "Dossiers logistiques",
            },
        ),
        migrations.AlterModelOptions(
            name="logisticsorderline",
            options={
                "verbose_name": "Ligne de dossier logistique",
                "verbose_name_plural": "Lignes de dossiers logistiques",
            },
        ),
        migrations.AlterField(
            model_name="historicallogisticsorder",
            name="numero_commande",
            field=models.CharField(
                max_length=24,
                verbose_name="Référence dossier logistique",
            ),
        ),
        migrations.AlterField(
            model_name="logisticsorder",
            name="numero_commande",
            field=models.CharField(
                max_length=24,
                verbose_name="Référence dossier logistique",
            ),
        ),
    ]
