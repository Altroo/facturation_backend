import re
from django.utils import timezone
from .models import LogisticsOrder


def get_next_numero_logistique(company_id: int) -> str:
    """Allocate COM references numerically, including sequences longer than 999."""
    suffix = f"/{timezone.localdate().year % 100:02d}"
    references = LogisticsOrder.objects.filter(
        company_id=company_id, numero_commande__endswith=suffix
    ).values_list("numero_commande", flat=True)
    numbers = [
        int(match.group(1))
        for reference in references
        if (match := re.fullmatch(r"(?:COM|LOG)(\d+)/\d{2}", reference))
    ]
    return f"COM{max(numbers, default=0) + 1:03d}{suffix}"
