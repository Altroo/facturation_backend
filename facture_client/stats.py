from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from company.models import Company
from facture_avoir.models import AVOIR_ACTIVE_STATUSES, FactureAvoir
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
            avoirs = FactureAvoir.objects.filter(
                company_id=company_id,
                devise=devise,
                statut__in=AVOIR_ACTIVE_STATUSES,
            ).aggregate(total=Sum("total_ttc_apres_remise"))["total"] or Decimal("0.00")

            reglements = Reglement.objects.filter(
                facture_client__client__company_id=company_id,
                facture_client__devise=devise,
                statut="Valide",
            ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

            chiffre_affaire_net = chiffre_affaire - avoirs
            impayes = chiffre_affaire_net - reglements

            stats_by_currency[devise] = {
                "chiffre_affaire_total": format(chiffre_affaire_net, "f"),
                "total_reglements": format(reglements, "f"),
                "total_impayes": format(impayes, "f"),
                "total_avoirs": format(avoirs, "f"),
            }
    else:
        # Only send MAD stats if company doesn't use foreign currency
        chiffre_affaire = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")
        avoirs = FactureAvoir.objects.filter(
            company_id=company_id,
            statut__in=AVOIR_ACTIVE_STATUSES,
        ).aggregate(total=Sum("total_ttc_apres_remise"))["total"] or Decimal("0.00")

        reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

        chiffre_affaire_net = chiffre_affaire - avoirs
        impayes = chiffre_affaire_net - reglements

        stats_by_currency["MAD"] = {
            "chiffre_affaire_total": format(chiffre_affaire_net, "f"),
            "total_reglements": format(reglements, "f"),
            "total_impayes": format(impayes, "f"),
            "total_avoirs": format(avoirs, "f"),
        }
        # Initialize EUR and USD to zeros for consistency
        stats_by_currency["EUR"] = {
            "chiffre_affaire_total": "0.00",
            "total_reglements": "0.00",
            "total_impayes": "0.00",
            "total_avoirs": "0.00",
        }
        stats_by_currency["USD"] = {
            "chiffre_affaire_total": "0.00",
            "total_reglements": "0.00",
            "total_impayes": "0.00",
            "total_avoirs": "0.00",
        }

    return stats_by_currency


def annotate_payment_and_avoir_totals(queryset):
    """Annotate invoice balances without multiplying reglement/avoir joins."""
    payment_count_subquery = Subquery(
        Reglement.objects.filter(facture_client_id=OuterRef("pk"), statut="Valide")
        .values("facture_client_id")
        .annotate(total=Count("id"))
        .values("total")[:1],
    )
    total_paid_subquery = Subquery(
        Reglement.objects.filter(facture_client_id=OuterRef("pk"), statut="Valide")
        .values("facture_client_id")
        .annotate(total=Sum("montant"))
        .values("total")[:1],
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    total_avoirs_subquery = Subquery(
        FactureAvoir.objects.filter(
            facture_origine_id=OuterRef("pk"),
            statut__in=AVOIR_ACTIVE_STATUSES,
        )
        .values("facture_origine_id")
        .annotate(total=Sum("total_ttc_apres_remise"))
        .values("total")[:1],
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    money_field = DecimalField(max_digits=10, decimal_places=2)
    return queryset.annotate(
        total_paid=Coalesce(
            total_paid_subquery,
            Value(Decimal("0.00")),
            output_field=money_field,
        ),
        payment_count=Coalesce(
            payment_count_subquery,
            Value(0),
        ),
        total_avoirs=Coalesce(
            total_avoirs_subquery,
            Value(Decimal("0.00")),
            output_field=money_field,
        ),
        net_total=ExpressionWrapper(
            F("total_ttc_apres_remise") - F("total_avoirs"),
            output_field=money_field,
        ),
    )
