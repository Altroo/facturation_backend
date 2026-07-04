from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logistique", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="logisticsorderline",
            name="project_reference",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
