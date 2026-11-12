"""Company-scoped aggregates for logistics charts and list summaries."""

from collections import Counter
from datetime import datetime, time
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import LogisticsOrder


def _money_field():
    return DecimalField(max_digits=12, decimal_places=2)


def _add_months(date_value, months):
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    return date_value.replace(year=year, month=month, day=1)


def _month_start_datetime(date_value):
    return timezone.make_aware(datetime.combine(date_value, time.min))


def get_logistics_stats(company_id):
    base = LogisticsOrder.objects.filter(company_id=company_id)
    global_status_counts = Counter(
        order.calculate_global_status() for order in base.iterator()
    )
    today = timezone.localdate()
    current_month = today.replace(day=1)
    months = [_add_months(current_month, offset) for offset in range(-5, 1)]
    active_count = sum(
        total
        for global_status, total in global_status_counts.items()
        if global_status not in {"Clôturé", "Annulé"}
    )
    pending_payments = base.filter(statut_paiement="En attente")
    delivered = base.filter(
        Q(statut_global__in=["À clôturer", "Clôturé"])
        | Q(statut__in=["Livraison client", "Clôture"])
    ).distinct()
    monthly_flow = []

    for month_start in months:
        month_end = _add_months(month_start, 1)
        month_start_dt = _month_start_datetime(month_start)
        month_end_dt = _month_start_datetime(month_end)
        created_in_month = base.filter(
            date_created__gte=month_start_dt,
            date_created__lt=month_end_dt,
        )
        monthly_flow.append(
            {
                "month": month_start.strftime("%Y-%m"),
                "commandes": created_in_month.count(),
                "livraisons": delivered.filter(
                    date_reelle__gte=month_start,
                    date_reelle__lt=month_end,
                ).count(),
                "paiements": base.filter(
                    statut_paiement="Validé",
                    paiement_valide_le__gte=month_start_dt,
                    paiement_valide_le__lt=month_end_dt,
                ).count(),
                "cout_total": created_in_month.aggregate(
                    total=Coalesce(
                        Sum("cout_total"), Decimal("0"), output_field=_money_field()
                    )
                )["total"],
            }
        )

    # noinspection PyDictCreation
    stats = {
        "commandes_en_cours": active_count,
        "total_commandes": base.count(),
        "retards": global_status_counts.get("En retard", 0),
        "paiements_en_attente": pending_payments.count(),
        "livraisons": delivered.count(),
        "couts_logistiques": base.aggregate(
            total=Coalesce(Sum("cout_total"), Decimal("0"), output_field=_money_field())
        )["total"],
        "swift_manquant": base.filter(statut_paiement="Validé")
        .filter(Q(swift_file="") | Q(swift_file__isnull=True))
        .count(),
        "documents_non_recus": base.filter(
            statut__in=["Documents originaux", "Transit"],
        )
        .filter(
            Q(documents_originaux_file="") | Q(documents_originaux_file__isnull=True)
        )
        .count(),
        "transit_non_lance": base.filter(
            statut__in=["Expédition", "Documents originaux"]
        ).count(),
        "statuts_workflow": [
            {"statut": global_status, "total": total}
            for global_status, total in sorted(global_status_counts.items())
        ],
        "statuts_paiement": list(
            base.values("statut_paiement")
            .annotate(total=Count("id"))
            .order_by("statut_paiement")
        ),
        "couts_detail": base.aggregate(
            achat=Coalesce(
                Sum(
                    Case(
                        When(
                            Q(workflow_version=2) & ~Q(devise="MAD"),
                            then=F("cout_achat_mad"),
                        ),
                        default=F("cout_achat"),
                        output_field=_money_field(),
                    )
                ),
                Decimal("0"),
                output_field=_money_field(),
            ),
            transport=Coalesce(
                Sum("cout_transport"), Decimal("0"), output_field=_money_field()
            ),
            transit=Coalesce(
                Sum("frais_transit"), Decimal("0"), output_field=_money_field()
            ),
            douane=Coalesce(
                Sum("frais_douane"), Decimal("0"), output_field=_money_field()
            ),
            tva=Coalesce(
                Sum(
                    Case(
                        When(workflow_version=2, then=Value(Decimal("0"))),
                        default=F("tva"),
                        output_field=_money_field(),
                    )
                ),
                Decimal("0"),
                output_field=_money_field(),
            ),
            livraison_locale=Coalesce(
                Sum("livraison_locale"), Decimal("0"), output_field=_money_field()
            ),
            autres=Coalesce(
                Sum(
                    F("autres_frais")
                    + Case(
                        When(
                            autres_frais_virement_actif=True,
                            then=F("autres_frais_virement"),
                        ),
                        default=Value(Decimal("0")),
                        output_field=_money_field(),
                    )
                ),
                Decimal("0"),
                output_field=_money_field(),
            ),
            total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        ),
        "monthly_flow": monthly_flow,
    }
    stats["marques"] = [
        {"id": brand["marque"], "nom": brand["marque__nom"]}
        for brand in base.exclude(marque__isnull=True)
        .exclude(marque__nom="")
        .order_by("marque__nom")
        .values("marque", "marque__nom")
        .distinct()[:100]
    ]
    stats["kpi_marques"] = list(
        base.exclude(marque__isnull=True)
        .exclude(marque__nom="")
        .values("marque", "marque__nom")
        .annotate(
            total_commandes=Count("id"),
            cout_total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        )
        .order_by("-total_commandes")[:5]
    )
    stats["fournisseurs"] = list(
        base.exclude(fournisseur="")
        .order_by("fournisseur")
        .values("fournisseur")
        .distinct()[:100]
    )
    stats["kpi_fournisseurs"] = list(
        base.exclude(fournisseur="")
        .values("fournisseur")
        .annotate(
            total_commandes=Count("id"),
            cout_total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        )
        .order_by("-total_commandes")[:5]
    )
    return stats
