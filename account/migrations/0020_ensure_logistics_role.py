from django.db import migrations


def ensure_logistics_role(apps, schema_editor):
    apps.get_model("accounts", "Role").objects.using(
        schema_editor.connection.alias
    ).get_or_create(name="Logistique")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_membership_can_change_document_status_and_more")]
    operations = [
        migrations.RunPython(ensure_logistics_role, migrations.RunPython.noop)
    ]
