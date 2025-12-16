from datetime import datetime
from re import search

from .models import FactureProForma


def get_next_numero_facture_pro_forma() -> str:
    """
    Return the next available numero_facture string like '0001/25'.
    """
    year_suffix = f"{datetime.now().year % 100:02d}"

    # Get all numbers for this year
    qs = FactureProForma.objects.filter(
        numero_facture__isnull=False,
        numero_facture__endswith=f"/{year_suffix}",
    ).values_list("numero_facture", flat=True)

    used_numbers = []
    for raw in qs:
        m = search(r"^(\d{4})/\d{2}$", raw or "")
        if m:
            try:
                used_numbers.append(int(m.group(1)))
            except ValueError:
                continue

    used_numbers = sorted(set(used_numbers))

    # Find first gap
    next_number = None
    for i in range(1, (max(used_numbers) if used_numbers else 0) + 2):
        if i not in used_numbers:
            next_number = i
            break

    return f"{next_number:04d}/{year_suffix}"
