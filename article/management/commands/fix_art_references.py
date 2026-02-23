"""
Management command to strip the 'ART' prefix from article references
created on 17 February 2026 at 15:42 (server local time).

Usage:
    python manage.py fix_art_references            # dry-run (no DB changes)
    python manage.py fix_art_references --apply    # actually save changes
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import datetime


class Command(BaseCommand):
    help = (
        "Strip the 'ART' prefix from article references "
        "created on 17/02/2026 at 15:42."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually persist the changes. Without this flag the command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        # ------------------------------------------------------------------ #
        # Build the minute-wide time window in the project's active timezone  #
        # ------------------------------------------------------------------ #
        tz = timezone.get_current_timezone()

        window_start = timezone.make_aware(
            datetime.datetime(2026, 2, 17, 15, 42, 0), tz
        )
        window_end = timezone.make_aware(
            datetime.datetime(2026, 2, 17, 15, 42, 59, 999999), tz
        )

        # Import here to avoid issues if the command is loaded before Django setup
        from article.models import Article

        articles = Article.objects.filter(
            date_created__gte=window_start,
            date_created__lte=window_end,
            reference__startswith="ART",
        )

        count = articles.count()

        if count == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No articles found with an 'ART' prefix created between "
                    f"{window_start} and {window_end}."
                )
            )
            return

        self.stdout.write(
            f"Found {count} article(s) to update (window: {window_start} → {window_end}):"
        )

        apply = options["apply"]

        with transaction.atomic():
            for article in articles:
                old_ref = article.reference
                new_ref = old_ref[3:]  # strip leading "ART"
                self.stdout.write(f"  [{article.pk}] {old_ref}  →  {new_ref}")

                if apply:
                    article.reference = new_ref
                    article.save(update_fields=["reference"])

            if not apply:
                self.stdout.write(
                    self.style.WARNING(
                        "\nDRY-RUN – no changes were saved. "
                        "Re-run with --apply to persist."
                    )
                )
                # Roll back even if something sneaked in
                transaction.set_rollback(True)
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✓ {count} reference(s) updated successfully."
                    )
                )
