# Generated manually

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_populate_roles"),
    ]

    operations = [
        # Step 1: Remove old role field
        migrations.RemoveField(
            model_name="membership",
            name="role",
        ),
        # Step 2: Rename new_role to role
        migrations.RenameField(
            model_name="membership",
            old_name="new_role",
            new_name="role",
        ),
        # Step 3: Update related_name
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="accounts.role",
            ),
        ),
    ]
