"""Seed the approved CASA DI LUSSO catalog and link existing dossier selections."""

import json
import re
from pathlib import Path

from django.db import migrations
from django.utils import timezone

INCOTERMS = (
    "EXW",
    "FCA",
    "CPT",
    "CIP",
    "DAP",
    "DPU",
    "DDP",
    "FAS",
    "FOB",
    "CFR",
    "CIF",
)
ALIASES = {
    "Delta Light": ("Delta Light Group",),
    "FMG – Fabbrica Marmi e Graniti": ("FMG Fabbrica Marmi e Graniti",),
    "Steinberg (Stienberg)": ("Steinberg", "Stienberg"),
}
RETIRED_LINKS = {
    "Marazzi Group": ("Hatria", "Daltile et American Olean", "Kerama Marazzi"),
    "Iris Ceramica Group": ("Maximum", "Diesel Living with Iris Ceramica", "StonePeak"),
    "Delta Light": ("LF Illumination, Delray, VLT",),
}


def seed_catalog(apps, schema_editor):
    db = schema_editor.connection.alias
    Company = apps.get_model("company", "Company")
    Brand = apps.get_model("parameter", "Marque")
    Supplier = apps.get_model("logistique", "LogisticsSupplier")
    Order = apps.get_model("logistique", "LogisticsOrder")
    History = apps.get_model("logistique", "HistoricalLogisticsOrder")
    models = {
        field: apps.get_model("parameter", name)
        for field, name in (
            ("incoterm", "Incoterm"),
            ("origine_marchandise", "OrigineMarchandise"),
            ("nature_marchandise", "NatureMarchandise"),
        )
    }

    def obtain(model, company_id, name):
        rows = model.objects.using(db).filter(company_id=company_id)
        item = rows.filter(nom__iexact=name).order_by("pk").first()
        if item is None:
            for alias in ALIASES.get(name, ()):
                item = rows.filter(nom__iexact=alias).order_by("pk").first()
                if item:
                    break
        created = item is None
        if created:
            item = model.objects.using(db).create(company_id=company_id, nom=name)
        elif item.nom != name:
            rows.filter(pk=item.pk).update(nom=name)
            item.nom = name
        else:
            return item
        history = apps.get_model(model._meta.app_label, f"Historical{model.__name__}")
        history_type = "+" if created else "~"
        if (
            not history.objects.using(db)
            .filter(id=item.pk, nom=name, history_type=history_type)
            .exists()
        ):
            values = {
                "id": item.pk,
                "company_id": company_id,
                "nom": name,
                "history_type": history_type,
                "history_date": timezone.now(),
            }
            for field in ("email", "date_created", "date_updated"):
                if hasattr(item, field):
                    values[field] = getattr(item, field)
            history.objects.using(db).create(**values)
        return item

    catalog = json.loads(
        (Path(__file__).parent / "data" / "0027_supplier_catalog.json").read_text()
    )
    for company in Company.objects.using(db).all().iterator():
        if re.sub(r"[^A-Z0-9]", "", company.raison_sociale.upper()) != "CASADILUSSO":
            continue
        for code in INCOTERMS:
            obtain(models["incoterm"], company.pk, code)
        for name, brands in catalog.items():
            supplier = obtain(Supplier, company.pk, name)
            for brand_name in brands:
                brand = obtain(Brand, company.pk, brand_name)
                Supplier.marques.through.objects.using(db).get_or_create(
                    logisticssupplier_id=supplier.pk, marque_id=brand.pk
                )
                obtain(models["nature_marchandise"], company.pk, brand.nom)
            for retired in RETIRED_LINKS.get(name, ()):
                Supplier.marques.through.objects.using(db).filter(
                    logisticssupplier_id=supplier.pk, marque__nom__iexact=retired
                ).delete()
        for name in (
            apps.get_model("parameter", "Emplacement")
            .objects.using(db)
            .filter(company_id=company.pk)
            .values_list("nom", flat=True)
        ):
            obtain(models["origine_marchandise"], company.pk, name)

    # Backfill all existing selections, including historical and custom values,
    # only in the company that originally owns each dossier. No label is changed.
    for model in (Order, History):
        for field, parameter in models.items():
            records = (
                model.objects.using(db)
                .filter(**{f"{field}_record__isnull": True})
                .exclude(**{field: ""})
            )
            for company_id, value in (
                records.values_list("company_id", field).distinct().iterator()
            ):
                if not company_id or not value.strip():
                    continue
                item = obtain(parameter, company_id, value.strip())
                records.filter(company_id=company_id, **{field: value}).update(
                    **{f"{field}_record_id": item.pk}
                )


class Migration(migrations.Migration):
    dependencies = [
        ("logistique", "0026_historicallogisticsorder_incoterm_record_and_more")
    ]
    operations = [migrations.RunPython(seed_catalog, migrations.RunPython.noop)]
