from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_assistant", "0002_pdftexttranslation_priority")]
    operations = [
        migrations.AddField(
            model_name="pdftexttranslation",
            name="engine_revision",
            field=models.PositiveSmallIntegerField(default=1, db_default=1),
        ),
        migrations.AlterField(
            model_name="pdftexttranslation",
            name="engine_revision",
            field=models.PositiveSmallIntegerField(default=2, db_default=1),
        ),
    ]
