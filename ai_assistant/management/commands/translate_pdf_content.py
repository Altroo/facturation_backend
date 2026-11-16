from django.core.management.base import BaseCommand, CommandError

from ai_assistant.models import PdfTextTranslation
from ai_assistant.pdf_translation import LANGUAGES, translation_enabled
from ai_assistant.tasks import backfill_pdf_translations


class Command(BaseCommand):
    help = "Queue a resumable Celery backfill of saved PDF text translations."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int)
        parser.add_argument("--language", action="append", choices=LANGUAGES)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--status", action="store_true")

    def handle(self, *args, **options):
        from django.db.models import Count
        from django.utils import timezone

        queryset = PdfTextTranslation.objects.all()
        if options["company"]:
            queryset = queryset.filter(company_id=options["company"])
        if options["language"]:
            queryset = queryset.filter(language__in=options["language"])
        if options["status"]:
            for group in queryset.values("language", "status").annotate(count=Count("pk")).order_by("language", "status"):
                self.stdout.write(f"{group['language']} {group['status']}: {group['count']}")
            return
        if not translation_enabled():
            raise CommandError("AI_PDF_TRANSLATION_ENABLED must be enabled.")
        if not 1 <= options["batch_size"] <= 500:
            raise CommandError("--batch-size must be between 1 and 500.")
        if options["retry_failed"]:
            queryset.filter(status="failed").update(status="pending", attempts=0, available_at=timezone.now(), last_error="")
        result = backfill_pdf_translations.delay(company_id=options["company"], languages=options["language"], batch_size=options["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"PDF translation backfill queued: {result.id}"))
