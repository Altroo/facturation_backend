"""Data migration: recalculate totals so TVA is computed on HT après remise."""

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations

BATCH_SIZE = 500


def _recalc(doc, Line, fk_field):
    """Inline recalc_totals logic for data migrations."""
    lines_data = []
    raw_total_ht = Decimal("0")

    for line in Line.objects.filter(**{fk_field: doc}).select_related("article"):
        prix_vente = line.prix_vente or Decimal("0")
        qty = line.quantity or Decimal("0")
        line_gross = prix_vente * qty

        remise = line.remise or Decimal("0")
        remise_type = line.remise_type or ""

        if remise > 0 and remise_type == "Pourcentage":
            line_discount = (line_gross * remise) / Decimal("100")
        elif remise > 0 and remise_type == "Fixe":
            line_discount = remise
        else:
            line_discount = Decimal("0")

        line_net_ht = max(Decimal("0"), line_gross - line_discount)
        raw_total_ht += line_net_ht

        tva_pct = Decimal(str(line.article.tva or 0))
        lines_data.append((line_net_ht, tva_pct))

    doc_remise = doc.remise or Decimal("0")
    doc_remise_type = doc.remise_type or ""

    if doc_remise > 0 and doc_remise_type == "Pourcentage":
        final_ht = raw_total_ht * (Decimal("1") - doc_remise / Decimal("100"))
    elif doc_remise > 0 and doc_remise_type == "Fixe":
        final_ht = max(Decimal("0"), raw_total_ht - doc_remise)
    else:
        final_ht = raw_total_ht

    ratio = final_ht / raw_total_ht if raw_total_ht > 0 else Decimal("0")
    final_tva = Decimal("0")
    for line_net_ht, tva_pct in lines_data:
        final_tva += (line_net_ht * ratio * tva_pct) / Decimal("100")

    final_ttc = final_ht + final_tva

    doc.total_ht = raw_total_ht.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    doc.total_tva = final_tva.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    doc.total_ttc = final_ttc.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    doc.total_ttc_apres_remise = final_ttc.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def recalculate_totals(apps, schema_editor):
    Devi = apps.get_model("devi", "Devi")
    DeviLine = apps.get_model("devi", "DeviLine")

    doc_ids = list(DeviLine.objects.values_list("devis_id", flat=True).distinct())
    for i in range(0, len(doc_ids), BATCH_SIZE):
        batch_ids = doc_ids[i : i + BATCH_SIZE]
        docs = list(Devi.objects.filter(pk__in=batch_ids))
        for doc in docs:
            _recalc(doc, DeviLine, "devis")
        Devi.objects.bulk_update(
            docs,
            ["total_ht", "total_tva", "total_ttc", "total_ttc_apres_remise"],
            batch_size=BATCH_SIZE,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("devi", "0022_quantity_to_decimal"),
    ]

    operations = [
        migrations.RunPython(recalculate_totals, migrations.RunPython.noop),
    ]
