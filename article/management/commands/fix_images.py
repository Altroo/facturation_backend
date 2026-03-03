"""Management command to automatically link article photos from media/article_images folder.

This command scans the media/article_images folder and links photos to articles
based on their reference code. Image files should be named as: {reference}.{ext}

Usage:
    python manage.py fix_images --company_id=1
    python manage.py fix_images --company_id=1 --dry-run
    python manage.py fix_images --company_id=1 --overwrite
"""

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from article.models import Article


class Command(BaseCommand):
    help = "Automatically link article photos from media/article_images folder based on reference codes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--company_id",
            type=int,
            required=True,
            help="Company ID to process articles for",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing photos (default: skip articles that already have photos)",
        )
        parser.add_argument(
            "--image-folder",
            type=str,
            default="article_images",
            help="Folder inside media directory containing images (default: article_images)",
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]
        image_folder = options["image_folder"]

        # Get the full path to the image folder
        media_root = settings.MEDIA_ROOT
        image_folder_path = os.path.join(media_root, image_folder)

        if not os.path.exists(image_folder_path):
            self.stdout.write(
                self.style.ERROR(f"✗ Image folder not found: {image_folder_path}")
            )
            self.stdout.write(
                self.style.WARNING(f"  Creating folder: {image_folder_path}")
            )
            os.makedirs(image_folder_path, exist_ok=True)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ Folder created. Please upload images to this folder."
                )
            )
            return

        # Get all image files
        image_files = [
            f
            for f in os.listdir(image_folder_path)
            if os.path.isfile(os.path.join(image_folder_path, f))
            and f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))
        ]

        if not image_files:
            self.stdout.write(
                self.style.WARNING(f"No image files found in {image_folder_path}")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFound {len(image_files)} image files in {image_folder_path}\n"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made\n")
            )

        # Get all articles for the company
        articles = Article.objects.filter(company_id=company_id)
        article_count = articles.count()

        if article_count == 0:
            self.stdout.write(
                self.style.ERROR(f"No articles found for company_id={company_id}")
            )
            return

        self.stdout.write(f"Total articles in company: {article_count}\n")

        # Create a lookup map by reference
        article_map = {article.reference: article for article in articles}

        updated_count = 0
        skipped_has_photo = 0
        not_found_count = 0

        self.stdout.write("Processing images...\n")

        for image_file in sorted(image_files):
            # Extract reference from filename (remove extension)
            base_name = os.path.splitext(image_file)[0]

            # Try multiple reference formats
            # 1. Try as-is (e.g., "ART68712726")
            # 2. Try with ART prefix (e.g., "68712726" -> "ART68712726")
            possible_references = [
                base_name,
                f"ART{base_name}",
            ]

            # Find the matching article
            reference = None
            for ref in possible_references:
                if ref in article_map:
                    reference = ref
                    break

            if reference is None:
                self.stdout.write(
                    self.style.WARNING(
                        f'  [X] {base_name}: Article not found in company {company_id} (tried: {", ".join(possible_references)})'
                    )
                )
                not_found_count += 1
                continue

            article = article_map[reference]

            # Check if article already has a photo
            if article.photo and not overwrite:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [!] {reference}: Already has photo ({article.photo}), would skip"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [!] {reference}: Already has photo ({article.photo}), skipping"
                        )
                    )
                skipped_has_photo += 1
                continue

            # Construct the photo path relative to MEDIA_ROOT
            photo_path = os.path.join(image_folder, image_file)

            if dry_run:
                action = "Would update" if article.photo else "Would link"
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] {reference}: {action} to {photo_path}")
                )
            else:
                old_photo = article.photo
                article.photo = photo_path
                article.save(update_fields=["photo"])

                if old_photo:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [OK] {reference}: Updated {old_photo} -> {photo_path}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [OK] {reference}: Linked to {photo_path}"
                        )
                    )

            updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 70)
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN COMPLETE - No changes were made\n")
            )
        else:
            self.stdout.write(self.style.SUCCESS("OPERATION COMPLETE\n"))

        self.stdout.write("Summary:")
        self.stdout.write(f"  - Total images processed:    {len(image_files)}")
        self.stdout.write(
            self.style.SUCCESS(f"  - Successfully linked:       {updated_count}")
        )
        if skipped_has_photo > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"  - Skipped (already had photo): {skipped_has_photo}"
                )
            )
        if not_found_count > 0:
            self.stdout.write(
                self.style.ERROR(f"  - Article not found:         {not_found_count}")
            )

        self.stdout.write("=" * 70)

        if skipped_has_photo > 0 and not overwrite:
            self.stdout.write(
                self.style.WARNING(
                    f"\nTip: Use --overwrite to update articles that already have photos"
                )
            )

        if not dry_run and updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully updated {updated_count} articles with photos!"
                )
            )
