from datetime import datetime
from re import search

from django.db import transaction

from core.utils import format_number_with_dynamic_digits
from .models import Devi


def get_next_numero_devis(company_id: int) -> str:
    """
    Return the next available numero_devis string like '0001/25' for the given company.
    Automatically increases digit count when 9999 is reached.
    """
    year_suffix = f"{datetime.now().year % 100:02d}"

    with transaction.atomic():
        # Lock the relevant rows to prevent concurrent access
        existing = (
            Devi.objects.filter(
                company_id=company_id,
                numero_devis__isnull=False,
                numero_devis__endswith=f"/{year_suffix}"
            )
            .select_for_update()
            .values_list("numero_devis", flat=True)
        )

        used_numbers = []
        for raw in existing:
            m = search(r"^(\d+)/\d{2}$", raw or "")
            if m:
                try:
                    used_numbers.append(int(m.group(1)))
                except ValueError:
                    continue

        used_numbers = sorted(set(used_numbers))
        next_number = None
        for i in range(1, (max(used_numbers) if used_numbers else 0) + 2):
            if i not in used_numbers:
                next_number = i
                break

        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
        return f"{formatted_number}/{year_suffix}"
