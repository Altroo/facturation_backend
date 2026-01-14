# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_customuser_date_updated"),
    ]

    operations = [
        # Step 1: Create Role model
        migrations.CreateModel(
            name="Role",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=150, unique=True, verbose_name="Role Name"
                    ),
                ),
                (
                    "is_admin",
                    models.BooleanField(
                        default=False,
                        help_text="Designates whether users with this role can manage companies and users.",
                        verbose_name="Is Admin",
                    ),
                ),
            ],
            options={
                "verbose_name": "Role",
                "verbose_name_plural": "Roles",
                "ordering": ("-is_admin", "name"),
            },
        ),
        # Step 2: Add nullable new_role field to Membership
        migrations.AddField(
            model_name="membership",
            name="new_role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="accounts.role",
                related_name="memberships_new",
            ),
        ),
    ]
