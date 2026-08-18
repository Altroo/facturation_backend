import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


GLOBAL_STATUS_BY_LEGACY_STAGE = {
    "Réception commande": "À lancer",
    "Commande fournisseur": "En cours",
    "Proforma": "En attente externe",
    "Titre d'Importation": "En cours",
    "Validation": "En cours",
    "Paiement demandé": "En attente externe",
    "Paiement effectué": "En cours",
    "SWIFT / Draft LC": "En cours",
    "Envoi SWIFT / Draft LC": "En cours",
    "Production": "En attente externe",
    "Expédition": "En cours",
    "Documents originaux": "En attente externe",
    "Transit": "En cours",
    "Dédouanement": "En cours",
    "Réception locale": "En cours",
    "Livraison client": "En cours",
    "Clôture": "Clôturé",
    "Annulé": "Annulé",
}


def initialize_new_workflow_fields(apps, schema_editor):
    LogisticsOrder = apps.get_model("logistique", "LogisticsOrder")
    HistoricalLogisticsOrder = apps.get_model(
        "logistique", "HistoricalLogisticsOrder"
    )

    for legacy_status, global_status in GLOBAL_STATUS_BY_LEGACY_STAGE.items():
        launch_status = (
            "À lancer" if legacy_status == "Réception commande" else "Terminée"
        )
        LogisticsOrder.objects.filter(statut=legacy_status).update(
            statut_global=global_status,
            statut_commande_lancement=launch_status,
        )
        HistoricalLogisticsOrder.objects.filter(statut=legacy_status).update(
            statut_global=global_status,
            statut_commande_lancement=launch_status,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("logistique", "0002_logisticsorderline_project_reference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="prochaine_relance_proforma",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="proforma_demandee_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="proforma_demandee_par",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="statut_commande_lancement",
            field=models.CharField(
                choices=[
                    ("À lancer", "À lancer"),
                    ("En cours", "En cours"),
                    ("En attente proforma", "En attente proforma"),
                    ("Bloquée", "Bloquée"),
                    ("Terminée", "Terminée"),
                ],
                db_index=True,
                default="À lancer",
                max_length=24,
                verbose_name="Statut commande et lancement",
            ),
        ),
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="statut_global",
            field=models.CharField(
                choices=[
                    ("Brouillon", "Brouillon"),
                    ("À lancer", "À lancer"),
                    ("En cours", "En cours"),
                    ("En attente externe", "En attente externe"),
                    ("Bloqué", "Bloqué"),
                    ("En retard", "En retard"),
                    ("À clôturer", "À clôturer"),
                    ("Clôturé", "Clôturé"),
                    ("Annulé", "Annulé"),
                    ("Rouvert", "Rouvert"),
                ],
                db_index=True,
                default="À lancer",
                max_length=24,
                verbose_name="Statut global",
            ),
        ),
        migrations.AddField(
            model_name="logisticsorder",
            name="prochaine_relance_proforma",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="logisticsorder",
            name="proforma_demandee_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="logisticsorder",
            name="proforma_demandee_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="demandes_proforma_logistique_enregistrees",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="logisticsorder",
            name="statut_commande_lancement",
            field=models.CharField(
                choices=[
                    ("À lancer", "À lancer"),
                    ("En cours", "En cours"),
                    ("En attente proforma", "En attente proforma"),
                    ("Bloquée", "Bloquée"),
                    ("Terminée", "Terminée"),
                ],
                db_index=True,
                default="À lancer",
                max_length=24,
                verbose_name="Statut commande et lancement",
            ),
        ),
        migrations.AddField(
            model_name="logisticsorder",
            name="statut_global",
            field=models.CharField(
                choices=[
                    ("Brouillon", "Brouillon"),
                    ("À lancer", "À lancer"),
                    ("En cours", "En cours"),
                    ("En attente externe", "En attente externe"),
                    ("Bloqué", "Bloqué"),
                    ("En retard", "En retard"),
                    ("À clôturer", "À clôturer"),
                    ("Clôturé", "Clôturé"),
                    ("Annulé", "Annulé"),
                    ("Rouvert", "Rouvert"),
                ],
                db_index=True,
                default="À lancer",
                max_length=24,
                verbose_name="Statut global",
            ),
        ),
        migrations.RunPython(initialize_new_workflow_fields, migrations.RunPython.noop),
    ]
