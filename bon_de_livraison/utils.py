from datetime import datetime
from re import search

from django.db import transaction

from core.utils import format_number_with_dynamic_digits
from .models import BonDeLivraison


def get_next_numero_bon_livraison() -> str:
    """
    Return the next available numero_bon_livraison string like '0001/25'.
    Automatically increases digit count when 9999 is reached.
    """
    year_suffix = f"{datetime.now().year % 100:02d}"

    with transaction.atomic():
        # Lock the relevant rows to prevent concurrent access
        existing = (
            BonDeLivraison.objects.filter(
                numero_bon_livraison__isnull=False,
                numero_bon_livraison__endswith=f"/{year_suffix}",
            )
            .select_for_update()
            .values_list("numero_bon_livraison", flat=True)
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
