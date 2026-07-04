from datetime import datetime

from django.db.models import Max

from .models import LogisticsOrder


def get_next_numero_logistique(company_id: int) -> str:
    """Return the next logistics order number for a company."""
    year_suffix = f"{datetime.now().year % 100:02d}"
    prefix = f"LOG"
    latest = (
        LogisticsOrder.objects.filter(
            company_id=company_id,
            numero_commande__startswith=prefix,
            numero_commande__endswith=f"/{year_suffix}",
        )
        .aggregate(max_num=Max("numero_commande"))
        .get("max_num")
    )
    next_number = 1
    if latest:
        try:
            next_number = int(latest.split("/")[0].replace(prefix, "")) + 1
        except (ValueError, IndexError):
            next_number = 1
    return f"{prefix}{next_number:03d}/{year_suffix}"
