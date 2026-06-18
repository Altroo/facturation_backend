from re import search

from django.db import transaction
from django.utils import timezone

from core.utils import format_number_with_dynamic_digits


def get_next_numero_facture_avoir(company_id: int) -> str:
    """Return the next credit-note number, independently from invoices: 'AV001/26'."""
    year_suffix = f"{timezone.localtime(timezone.now()).year % 100:02d}"

    from .models import FactureAvoir

    with transaction.atomic():
        existing = (
            FactureAvoir.objects.filter(
                company_id=company_id,
                numero_avoir__isnull=False,
                numero_avoir__endswith=f"/{year_suffix}",
            )
            .select_for_update()
            .values_list("numero_avoir", flat=True)
        )

        used_numbers = []
        for raw in existing:
            match = search(r"^AV(\d+)/\d{2}$", raw or "")
            if match:
                try:
                    used_numbers.append(int(match.group(1)))
                except ValueError:
                    continue

        used_numbers = sorted(set(used_numbers))
        next_number = None
        for i in range(1, (max(used_numbers) if used_numbers else 0) + 2):
            if i not in used_numbers:
                next_number = i
                break

        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=3)
        return f"AV{formatted_number}/{year_suffix}"
