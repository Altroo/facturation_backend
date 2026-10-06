from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("logistique", "0014_logistics_field_review")]

    operations = [
        migrations.AddField(
            model_name="logisticsfieldreview",
            name="proposed_fields",
            field=models.JSONField(default=dict),
        ),
    ]
