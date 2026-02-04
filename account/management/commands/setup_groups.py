"""
Management command to set up permission groups.

This command creates the following groups:
- Caissier (formerly Admin): Full access
- Comptable (formerly Finance): Read and print only, no edit/create/delete
- Commercial: Create everything except users & companies, cannot update prix_vente
- Lecture: View only, no print/create/delete/edit
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from models import Role


class Command(BaseCommand):
    help = "Set up permission Roles (Caissier, Comptable, Commercial, Lecture)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Setting up permission Roles..."))

        with transaction.atomic():
            # Create groups
            caissier, created = Role.objects.get_or_create(name="Caissier")
            if created:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ Created Role: Caissier (full access)")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Group Role exists: Caissier")
                )

            comptable, created = Role.objects.get_or_create(name="Comptable")
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        "  ✓ Created Role: Comptable (read & print only)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Role already exists: Comptable")
                )

            commercial, created = Role.objects.get_or_create(name="Commercial")
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        "  ✓ Created Role: Commercial (create documents)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Role already exists: Commercial")
                )

            lecture, created = Role.objects.get_or_create(name="Lecture")
            if created:
                self.stdout.write(
                    self.style.SUCCESS("  ✓ Created Role: Lecture (view only)")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("  - Role already exists: Lecture")
                )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\nDone! All permission Role have been set up."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\nNote: Permission logic is enforced in views and serializers, not Django permissions."
            )
        )
