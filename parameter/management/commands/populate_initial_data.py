"""
Management command to populate initial parameter data.

This command populates:
- Catégories
- Unités  
- Marques
- Modes de paiement
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from parameter.models import Categorie, Unite, Marque, ModePaiement


class Command(BaseCommand):
    help = "Populate initial parameter data (categories, units, brands, payment modes)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Populating initial data..."))

        with transaction.atomic():
            # Categories
            categories = [
                "céramique",
                "cuisine",
                "dressing",
                "robinet",
                "jacuzzi",
                "hammam",
                "lighting",
                "ameublement",
            ]
            
            created_categories = 0
            for cat_name in categories:
                obj, created = Categorie.objects.get_or_create(nom=cat_name)
                if created:
                    created_categories += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created category: {cat_name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - Category already exists: {cat_name}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"Categories: {created_categories} created\n")
            )

            # Units
            units = [
                "m²",
                "mL",
                "Kg",
                "pièce",
            ]
            
            created_units = 0
            for unit_name in units:
                obj, created = Unite.objects.get_or_create(nom=unit_name)
                if created:
                    created_units += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created unit: {unit_name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - Unit already exists: {unit_name}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"Units: {created_units} created\n")
            )

            # Brands
            brands = [
                "Gessi",
                "Arredo3",
                "Marazzi",
                "Ariostea",
                "Delta light",
                "Effe",
                "Flaminia",
                "Flos",
                "Henry glass",
                "Poliform",
                "Giessegi",
                "jacuzzi",
                "Bonaldo",
            ]
            
            created_brands = 0
            for brand_name in brands:
                obj, created = Marque.objects.get_or_create(nom=brand_name)
                if created:
                    created_brands += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created brand: {brand_name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - Brand already exists: {brand_name}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"Brands: {created_brands} created\n")
            )

            # Payment modes
            payment_modes = [
                "Virement",
                "Espèce",
                "Chèque",
                "Acompte",
                "Carte bancaire",
            ]
            
            created_payment_modes = 0
            for mode_name in payment_modes:
                obj, created = ModePaiement.objects.get_or_create(nom=mode_name)
                if created:
                    created_payment_modes += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created payment mode: {mode_name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - Payment mode already exists: {mode_name}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"Payment modes: {created_payment_modes} created\n")
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone! Created {created_categories} categories, {created_units} units, "
                f"{created_brands} brands, and {created_payment_modes} payment modes."
            )
        )
