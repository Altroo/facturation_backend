from datetime import datetime
from re import search

from .models import BonDeLivraison


def get_next_numero_bon_livraison() -> str:
    year_suffix = f"{datetime.now().year % 100:02d}"
    qs = BonDeLivraison.objects.filter(
        numero_bon_livraison__isnull=False,
        numero_bon_livraison__endswith=f"/{year_suffix}",
    ).values_list("numero_bon_livraison", flat=True)

    used_numbers = []
    for raw in qs:
        m = search(r"^(\d{4})/\d{2}$", raw or "")
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

    return f"{next_number:04d}/{year_suffix}"
