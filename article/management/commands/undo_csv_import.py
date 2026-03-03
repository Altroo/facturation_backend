"""Management command to undo a CSV import by deleting articles matching
the references found in the CSV file, along with their photos on disk.

Usage:
    python manage.py undo_csv_import --csv=gessi_products.csv --company_id=1 --dry-run
    python manage.py undo_csv_import --csv=gessi_products.csv --company_id=1
"""

import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from article.models import Article


class Command(BaseCommand):
    help = "Delete articles imported from a CSV file and remove their photos from disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            type=str,
            required=True,
            help="Path to the CSV file that was originally imported",
        )
        parser.add_argument(
            "--company_id",
            type=int,
            required=True,
            help="Company ID the articles belong to",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def _detect_delimiter(self, sample: str) -> str:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            return ";"

    def handle(self, *args, **options):
        csv_path = options["csv"]
        company_id = options["company_id"]
        dry_run = options["dry_run"]

        if not os.path.isfile(csv_path):
            self.stderr.write(self.style.ERROR(f"CSV file not found: {csv_path}"))
            return

        # --- read references from csv ----------------------------------------
        with open(csv_path, encoding="utf-8-sig") as f:
            content = f.read()

        delimiter = self._detect_delimiter(content[:2048])
        reader = csv.DictReader(content.splitlines().__iter__(), delimiter=delimiter)

        references: list[str] = []
        for row in reader:
            normalized = {
                k.strip().lower(): (v or "").strip()
                for k, v in row.items()
                if k is not None
            }
            ref = normalized.get("reference", "").strip()
            if ref:
                references.append(ref)

        if not references:
            self.stderr.write(self.style.ERROR("No references found in the CSV."))
            return

        self.stdout.write(f"Found {len(references)} references in the CSV.\n")

        # --- find matching articles ------------------------------------------
        articles = Article.objects.filter(
            company_id=company_id,
            reference__in=references,
        )
        found_count = articles.count()
        self.stdout.write(f"Matched {found_count} articles in the database.\n")

        if found_count == 0:
            self.stdout.write(self.style.WARNING("Nothing to delete."))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN — no changes will be made.\n")
            )

        # --- delete photos ---------------------------------------------------
        media_root = settings.MEDIA_ROOT
        photos_deleted = 0
        photos_missing = 0

        for article in articles:
            if article.photo:
                photo_path = os.path.join(media_root, str(article.photo))
                if os.path.isfile(photo_path):
                    if dry_run:
                        self.stdout.write(f"  Would delete photo: {photo_path}")
                    else:
                        os.remove(photo_path)
                        self.stdout.write(
                            self.style.SUCCESS(f"  Deleted photo: {photo_path}")
                        )
                    photos_deleted += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  Photo file not found: {photo_path}")
                    )
                    photos_missing += 1

        # --- delete articles -------------------------------------------------
        if dry_run:
            self.stdout.write(f"\n  Would delete {found_count} articles.\n")
        else:
            deleted_count, _ = articles.delete()
            self.stdout.write(
                self.style.SUCCESS(f"\n  Deleted {deleted_count} articles.\n")
            )

        # --- summary ---------------------------------------------------------
        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN COMPLETE\n"))
        else:
            self.stdout.write(self.style.SUCCESS("CLEANUP COMPLETE\n"))
        self.stdout.write(f"  CSV references:        {len(references)}")
        self.stdout.write(f"  Articles matched:      {found_count}")
        self.stdout.write(f"  Photos deleted:        {photos_deleted}")
        if photos_missing:
            self.stdout.write(f"  Photos not on disk:    {photos_missing}")
        self.stdout.write("=" * 60)
