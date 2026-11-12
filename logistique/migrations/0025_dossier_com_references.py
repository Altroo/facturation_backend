import re
from decimal import Decimal
from django.db import migrations
from django.db.models import Case, DecimalField, F, Value, When
from django.db.models.functions import Coalesce


def rename_references(apps, schema_editor):
    Order = apps.get_model("logistique", "LogisticsOrder")
    History = apps.get_model("logistique", "HistoricalLogisticsOrder")
    for order in (
        Order.objects.filter(numero_commande__startswith="LOG")
        .order_by("pk")
        .iterator()
    ):
        match = re.fullmatch(r"LOG(\d+)/(\d{2})", order.numero_commande)
        if not match:
            continue
        number, year = int(match.group(1)), match.group(2)
        reference = f"COM{number:03d}/{year}"
        while (
            Order.objects.filter(company_id=order.company_id, numero_commande=reference)
            .exclude(pk=order.pk)
            .exists()
        ):
            number += 1
            reference = f"COM{number:03d}/{year}"
        Order.objects.filter(pk=order.pk).update(numero_commande=reference)
        History.objects.filter(id=order.pk).update(numero_commande=reference)


def normalize_supplier_costs(apps, schema_editor):
    Order = apps.get_model("logistique", "LogisticsOrder")
    money = DecimalField(max_digits=12, decimal_places=2)
    purchase = Case(
        When(devise="MAD", then=F("cout_achat")),
        default=Coalesce(F("cout_achat_mad"), Value(Decimal("0"))),
        output_field=money,
    )
    transfer = Case(
        When(autres_frais_virement_actif=True, then=F("autres_frais_virement")),
        default=Value(Decimal("0")),
        output_field=money,
    )
    # Preserve the foreign purchase value and all historical cost snapshots.
    Order.objects.filter(workflow_version=2).update(
        cout_total=(
            purchase
            + F("cout_transport")
            + F("frais_transit")
            + F("frais_douane")
            + F("livraison_locale")
            + F("autres_frais")
            + transfer
        )
    )


class Migration(migrations.Migration):
    dependencies = [("logistique", "0024_logistics_workflow_feedback")]
    operations = [
        migrations.RunPython(rename_references, migrations.RunPython.noop),
        migrations.RunPython(normalize_supplier_costs, migrations.RunPython.noop),
    ]
