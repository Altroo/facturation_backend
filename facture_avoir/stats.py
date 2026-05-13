from decimal import Decimal

from django.db.models import Sum

from company.models import Company
from .models import AVOIR_ACTIVE_STATUSES, FactureAvoir


def get_avoir_stats_by_currency(company_id: int) -> dict:
    company = Company.objects.get(id=company_id)
    stats_by_currency: dict = {}
    devises = ["MAD", "EUR", "USD"] if company.uses_foreign_currency else ["MAD"]

    for devise in devises:
        total = (
            FactureAvoir.objects.filter(
                company_id=company_id,
                devise=devise,
                statut__in=AVOIR_ACTIVE_STATUSES,
            ).aggregate(total=Sum("total_ttc_apres_remise"))["total"]
            or Decimal("0.00")
        )
        total_tva = (
            FactureAvoir.objects.filter(
                company_id=company_id,
                devise=devise,
                statut__in=AVOIR_ACTIVE_STATUSES,
            ).aggregate(total=Sum("total_tva"))["total"]
            or Decimal("0.00")
        )
        stats_by_currency[devise] = {
            "total_avoirs": str(total),
            "total_tva": str(total_tva),
        }

    for devise in ["MAD", "EUR", "USD"]:
        stats_by_currency.setdefault(
            devise,
            {
                "total_avoirs": "0.00",
                "total_tva": "0.00",
            },
        )

    return stats_by_currency
