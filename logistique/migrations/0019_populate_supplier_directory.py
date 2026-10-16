from django.db import migrations
from django.utils import timezone


def populate_suppliers(apps, schema_editor):
    db = schema_editor.connection.alias
    Supplier = apps.get_model("logistique", "LogisticsSupplier")
    Order = apps.get_model("logistique", "LogisticsOrder")
    Brand = apps.get_model("parameter", "Marque")
    suppliers = {}

    def obtain(company_id, name, email):
        name, email = (name or "").strip(), (email or "").strip()
        if not name:
            return None
        key = (company_id, name.lower())
        supplier = suppliers.get(key)
        if supplier is None:
            supplier, _ = Supplier.objects.using(db).get_or_create(
                company_id=company_id,
                nom__iexact=name,
                defaults={"nom": name, "email": email},
            )
            suppliers[key] = supplier
        elif not supplier.email and email:
            Supplier.objects.using(db).filter(pk=supplier.pk).update(email=email)
            supplier.email = email
        return supplier

    # Latest dossier spelling and non-empty email take precedence. No dossier
    # snapshots, timestamps, events, brands or source documents are changed.
    for order in Order.objects.using(db).order_by("-date_updated", "-pk").iterator():
        supplier = obtain(order.company_id, order.fournisseur, order.fournisseur_email)
        if supplier:
            Order.objects.using(db).filter(pk=order.pk).update(
                fournisseur_record_id=supplier.pk
            )
    # The old contact form stored entries among brands. Retain those brands
    # and copy only contacts with an email into the new directory.
    for brand in (
        Brand.objects.using(db)
        .exclude(email="")
        .exclude(company_id=None)
        .order_by("-pk")
        .iterator()
    ):
        obtain(brand.company_id, brand.nom, brand.email)
    History = apps.get_model("logistique", "HistoricalLogisticsSupplier")
    History.objects.using(db).bulk_create(
        [
            History(
                id=s.pk,
                company_id=s.company_id,
                nom=s.nom,
                email=s.email,
                date_created=s.date_created,
                date_updated=s.date_updated,
                history_date=timezone.now(),
                history_type="+",
            )
            for s in suppliers.values()
        ]
    )


class Migration(migrations.Migration):
    dependencies = [
        ("logistique", "0018_supplier_directory"),
        ("parameter", "0011_historicalmarque_email_marque_email"),
    ]
    operations = [migrations.RunPython(populate_suppliers, migrations.RunPython.noop)]
