from decimal import Decimal

from django.db.models import Sum

from company.models import Company
from reglement.models import Reglement
from .models import FactureClient


def get_stats_by_currency(company_id: int) -> dict:
    """
    Calculate aggregated financial stats per currency for a given company.

    Returns a dict keyed by currency code ("MAD", "EUR", "USD"), each containing:
        - chiffre_affaire_total: str — total TTC après remise of all factures
        - total_reglements:      str — sum of all valid règlements
        - total_impayes:         str — chiffre_affaire_total - total_reglements

    When company.uses_foreign_currency is True, real figures are computed for
    every currency.  When False, only MAD is computed; EUR and USD are zeroed.
    """
    factures = FactureClient.objects.filter(client__company_id=company_id)
    company = Company.objects.get(id=company_id)

    stats_by_currency: dict = {}

    if company.uses_foreign_currency:
        # Send stats for all currencies if company uses foreign currency
        for devise in ["MAD", "EUR", "USD"]:
            factures_devise = factures.filter(devise=devise)
            chiffre_affaire = factures_devise.aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"] or Decimal("0.00")

            reglements = Reglement.objects.filter(
                facture_client__client__company_id=company_id,
                facture_client__devise=devise,
                statut="Valide",
            ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

            impayes = chiffre_affaire - reglements

            stats_by_currency[devise] = {
                "chiffre_affaire_total": str(chiffre_affaire),
                "total_reglements": str(reglements),
                "total_impayes": str(impayes),
            }
    else:
        # Only send MAD stats if company doesn't use foreign currency
        chiffre_affaire = factures.aggregate(
            total=Sum("total_ttc_apres_remise")
        )["total"] or Decimal("0.00")

        reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

        impayes = chiffre_affaire - reglements

        stats_by_currency["MAD"] = {
            "chiffre_affaire_total": str(chiffre_affaire),
            "total_reglements": str(reglements),
            "total_impayes": str(impayes),
        }
        # Initialize EUR and USD to zeros for consistency
        stats_by_currency["EUR"] = {
            "chiffre_affaire_total": "0.00",
            "total_reglements": "0.00",
            "total_impayes": "0.00",
        }
        stats_by_currency["USD"] = {
            "chiffre_affaire_total": "0.00",
            "total_reglements": "0.00",
            "total_impayes": "0.00",
        }

    return stats_by_currency
