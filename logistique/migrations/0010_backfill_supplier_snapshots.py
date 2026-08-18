from django.db import migrations


def backfill_supplier_snapshots(apps, schema_editor):
    LogisticsOrder = apps.get_model("logistique", "LogisticsOrder")
    LogisticsOrderProforma = apps.get_model("logistique", "LogisticsOrderProforma")
    FactureProForma = apps.get_model("facture_proforma", "FactureProForma")

    for order in LogisticsOrder.objects.all().iterator():
        source_ids = list(
            LogisticsOrderProforma.objects.filter(commande_id=order.pk)
            .values_list("proforma_id", flat=True)
            .distinct()[:2]
        )
        if len(source_ids) != 1:
            continue
        source = (
            FactureProForma.objects.filter(pk=source_ids[0])
            .values("fournisseur", "fournisseur_email")
            .first()
        )
        if not source:
            continue
        updates = {}
        if not order.fournisseur and source["fournisseur"]:
            updates["fournisseur"] = source["fournisseur"]
        if not order.fournisseur_email and source["fournisseur_email"]:
            updates["fournisseur_email"] = source["fournisseur_email"]
        if updates:
            LogisticsOrder.objects.filter(pk=order.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("facture_proforma", "0025_alter_factureproforma_fournisseur_and_more"),
        (
            "logistique",
            "0009_historicallogisticsorder_demande_paiement_email_file_token_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(backfill_supplier_snapshots, migrations.RunPython.noop),
    ]
