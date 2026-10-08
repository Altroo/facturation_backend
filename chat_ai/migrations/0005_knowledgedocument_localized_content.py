from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat_ai", "0004_auditevent_instruction_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocument",
            name="localized_content",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
