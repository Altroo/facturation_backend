"""
Management command to set up permission groups.

This command creates the following groups:
- Caissier (formerly Admin): Full access
- Comptable (formerly Finance): Read and print only, no edit/create/delete
- Commercial: Create everything except users & companies, cannot update prix_vente
- Lecture: View only, no print/create/delete/edit
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction


class Command(BaseCommand):
    help = "Set up permission groups (Caissier, Comptable, Commercial, Lecture)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Setting up permission groups..."))

        with transaction.atomic():
            # Create groups
            caissier, created = Group.objects.get_or_create(name="Caissier")
            if created:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ Created group: Caissier (full access)")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Group already exists: Caissier")
                )

            comptable, created = Group.objects.get_or_create(name="Comptable")
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        "  ✓ Created group: Comptable (read & print only)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Group already exists: Comptable")
                )

            commercial, created = Group.objects.get_or_create(name="Commercial")
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        "  ✓ Created group: Commercial (create documents)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Group already exists: Commercial")
                )

            lecture, created = Group.objects.get_or_create(name="Lecture")
            if created:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ Created group: Lecture (view only)")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Group already exists: Lecture")
                )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\nDone! All permission groups have been set up."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\nNote: Permission logic is enforced in views and serializers, not Django permissions."
            )
        )
