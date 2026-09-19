from re import search
from typing import TYPE_CHECKING, cast

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from core.utils import format_number_with_dynamic_digits

if TYPE_CHECKING:
    from .models import FactureAvoir


def get_next_numero_facture_avoir(company_id: int) -> str:
    """Return the next credit-note number, independently of invoices: 'AV001/26'."""
    year_suffix = f"{timezone.localtime(timezone.now()).year % 100:02d}"
    facture_avoir_model = cast(
        "type[FactureAvoir]", apps.get_model("facture_avoir", "FactureAvoir")
    )

    with transaction.atomic():
        existing = (
            facture_avoir_model.objects.filter(
                company_id=company_id,
                numero_avoir__isnull=False,
                numero_avoir__endswith=f"/{year_suffix}",
            )
            .select_for_update()
            .values_list("numero_avoir", flat=True)
        )

        used_numbers = []
        for raw in existing:
            matched_number = search(r"^AV(\d+)/\d{2}$", raw or "")
            if matched_number:
                try:
                    used_numbers.append(int(matched_number.group(1)))
                except ValueError:
                    continue

        used_numbers = sorted(set(used_numbers))
        next_number = 1
        for candidate in range(1, (max(used_numbers) if used_numbers else 0) + 2):
            if candidate not in used_numbers:
                next_number = candidate
                break

        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=3)
        return f"AV{formatted_number}/{year_suffix}"
