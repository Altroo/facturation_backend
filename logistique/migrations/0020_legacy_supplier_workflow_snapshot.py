from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("logistique", "0019_populate_supplier_directory")]
    operations = [
        migrations.AddField(
            model_name="logisticsorder",
            name="legacy_source_snapshot",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
        migrations.AddField(
            model_name="historicallogisticsorder",
            name="legacy_source_snapshot",
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
