from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_customuser_password_reset_code_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="sso_subject",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Identifiant stable du compte central E.B.H.",
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Identifiant SSO",
            ),
        ),
        migrations.AddField(
            model_name="historicalcustomuser",
            name="sso_subject",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Identifiant stable du compte central E.B.H.",
                max_length=64,
                null=True,
                verbose_name="Identifiant SSO",
            ),
        ),
    ]
