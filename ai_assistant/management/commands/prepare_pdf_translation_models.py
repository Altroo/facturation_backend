import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ai_assistant.model_packages import prepare_models


class Command(BaseCommand):
    help = "Install or check pinned offline PDF translation models. Setup only."

    def add_arguments(self, parser):
        parser.add_argument("--directory")
        parser.add_argument("--archives")
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, **options):
        try:
            result = prepare_models(
                options["directory"] or settings.PDF_TRANSLATION_MODELS_DIR,
                archives=options["archives"], check=options["check"],
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
