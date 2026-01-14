# Generated manually

from django.db import migrations


def create_roles_and_migrate_data(apps, schema_editor):
    """Create roles and migrate Group memberships to Role memberships."""
    Role = apps.get_model("accounts", "Role")
    Membership = apps.get_model("accounts", "Membership")
    Group = apps.get_model("auth", "Group")

    # Create new roles
    admin_role, _ = Role.objects.get_or_create(
        name="Admin", defaults={"is_admin": True}
    )

    caissier_role, _ = Role.objects.get_or_create(
        name="Caissier", defaults={"is_admin": False}
    )

    comptable_role, _ = Role.objects.get_or_create(
        name="Comptable", defaults={"is_admin": False}
    )

    commercial_role, _ = Role.objects.get_or_create(
        name="Commercial", defaults={"is_admin": False}
    )

    lecture_role, _ = Role.objects.get_or_create(
        name="Lecture", defaults={"is_admin": False}
    )

    # Map old Group names to new Roles
    role_mapping = {
        "Admin": admin_role,
        "Finance": comptable_role,  # Rename Finance to Comptable
        "Lecture": lecture_role,
    }

    # Migrate existing memberships
    for membership in Membership.objects.select_related("role").all():
        if membership.role:
            try:
                old_group_name = membership.role.name
                new_role = role_mapping.get(old_group_name)
                if new_role:
                    membership.new_role = new_role
                    membership.save(update_fields=["new_role"])
            except Exception:
                pass


def reverse_migration(apps, schema_editor):
    """Reverse the data migration."""
    Role = apps.get_model("accounts", "Role")
    Role.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_create_role_model"),
    ]

    operations = [
        migrations.RunPython(create_roles_and_migrate_data, reverse_migration),
    ]
