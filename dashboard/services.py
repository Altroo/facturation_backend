"""Financial aggregates shared by dashboards and authorized assistant tools."""

from decimal import Decimal
from typing import Any

from django.db.models import (
    Avg,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce, TruncDate

from facture_avoir.models import AVOIR_ACTIVE_STATUSES, FactureAvoir
from facture_client.models import FactureClient
from reglement.models import Reglement


def money_field():
    return DecimalField(max_digits=10, decimal_places=2)


def sum_decimal(queryset, field_name):
    return queryset.aggregate(
        total=Coalesce(Sum(field_name), Decimal("0"), output_field=money_field())
    )["total"]


def apply_scope_to_queryset(
    queryset,
    client_id=None,
    project_ref=None,
    client_field="client_id",
    project_field=None,
):
    if client_id and client_field:
        queryset = queryset.filter(**{client_field: client_id})
    if project_ref and project_field:
        queryset = queryset.filter(**{f"{project_field}__icontains": project_ref})
    return queryset


def apply_scope_to_filters(
    filters,
    client_id=None,
    project_ref=None,
    client_field="client_id",
    project_field=None,
):
    if client_id and client_field:
        filters[client_field] = client_id
    if project_ref and project_field:
        filters[f"{project_field}__icontains"] = project_ref
    return filters


def avoir_queryset(
    date_from=None,
    date_to=None,
    company_id=None,
    devise=None,
    client_id=None,
    project_ref=None,
):
    queryset = FactureAvoir.objects.filter(statut__in=AVOIR_ACTIVE_STATUSES)
    if date_from:
        queryset = queryset.filter(date_avoir__gte=date_from)
    if date_to:
        queryset = queryset.filter(date_avoir__lte=date_to)
    if company_id:
        queryset = queryset.filter(company_id=company_id)
    if devise:
        queryset = queryset.filter(devise=devise)
    queryset = apply_scope_to_queryset(
        queryset,
        client_id,
        project_ref,
        client_field="client_id",
        project_field="numero_bon_commande_client",
    )
    return queryset


def total_avoirs(
    date_from=None,
    date_to=None,
    company_id=None,
    devise=None,
    client_id=None,
    project_ref=None,
):
    return sum_decimal(
        avoir_queryset(date_from, date_to, company_id, devise, client_id, project_ref),
        "total_ttc_apres_remise",
    )


def annotate_total_reglements(queryset, as_of=None):
    """Annotate a FactureClient queryset with payments, credit_notes, and net total."""
    payments = Reglement.objects.filter(
        facture_client_id=OuterRef("id"), statut="Valide"
    )
    credit_notes = FactureAvoir.objects.filter(
        facture_origine_id=OuterRef("id"), statut__in=AVOIR_ACTIVE_STATUSES
    )
    if as_of is not None:
        payments = payments.filter(date_reglement__lte=as_of)
        credit_notes = credit_notes.filter(date_avoir__lte=as_of)
    total_reglements_subquery = Subquery(
        payments.values("facture_client_id")
        .annotate(total=Sum("montant"))
        .values("total")[:1],
        output_field=money_field(),
    )
    total_avoirs_subquery = Subquery(
        credit_notes.values("facture_origine_id")
        .annotate(total=Sum("total_ttc_apres_remise"))
        .values("total")[:1],
        output_field=money_field(),
    )
    return queryset.annotate(
        total_reglements=Coalesce(
            total_reglements_subquery, Decimal("0"), output_field=money_field()
        ),
        total_avoirs=Coalesce(
            total_avoirs_subquery, Decimal("0"), output_field=money_field()
        ),
        net_total=ExpressionWrapper(
            F("total_ttc_apres_remise") - F("total_avoirs"),
            output_field=money_field(),
        ),
    )


def collection_rate(
    date_from, date_to, company_id, devise=None, client_id=None, project_ref=None
):
    facture_filter: dict[str, Any] = {"date_facture__lte": date_to}
    reglement_filter: dict[str, Any] = {
        "date_reglement__lte": date_to,
        "statut": "Valide",
    }

    if date_from:
        facture_filter["date_facture__gte"] = date_from
        reglement_filter["date_reglement__gte"] = date_from

    if company_id:
        facture_filter["client__company_id"] = company_id
        reglement_filter["facture_client__client__company_id"] = company_id

    if devise:
        facture_filter["devise"] = devise
        reglement_filter["facture_client__devise"] = devise
    apply_scope_to_filters(
        facture_filter,
        client_id,
        project_ref,
        client_field="client_id",
        project_field="numero_bon_commande_client",
    )
    apply_scope_to_filters(
        reglement_filter,
        client_id,
        project_ref,
        client_field="facture_client__client_id",
        project_field="facture_client__numero_bon_commande_client",
    )

    total_invoiced = FactureClient.objects.filter(**facture_filter).aggregate(
        total=Sum("total_ttc_apres_remise")
    )["total"] or Decimal("0")
    total_invoiced -= total_avoirs(
        date_from, date_to, company_id, devise, client_id, project_ref
    )

    total_collected = Reglement.objects.filter(**reglement_filter).aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    if total_invoiced > 0:
        rate = (total_collected / total_invoiced) * 100
    else:
        rate = 0

    result = {
        "rate": float(rate),
        "total_invoiced": float(total_invoiced),
        "total_collected": float(total_collected),
    }

    return result


def calculate_kpi_for_currency(
    devise,
    date_from,
    date_to,
    company_id,
    current_period_start,
    seven_days_before_date_to,
    client_id=None,
    project_ref=None,
):
    """Calculate KPIs for a specific currency."""
    # CA total with trend
    current_month_query = FactureClient.objects.filter(
        date_facture__gte=current_period_start,
        date_facture__lte=date_to,
        devise=devise,
    )
    daily_revenue_query = FactureClient.objects.filter(
        date_facture__gte=seven_days_before_date_to,
        date_facture__lte=date_to,
        devise=devise,
    )

    if company_id:
        current_month_query = current_month_query.filter(client__company_id=company_id)
        daily_revenue_query = daily_revenue_query.filter(client__company_id=company_id)

    current_month_query = apply_scope_to_queryset(
        current_month_query,
        client_id,
        project_ref,
        client_field="client_id",
        project_field="numero_bon_commande_client",
    )
    daily_revenue_query = apply_scope_to_queryset(
        daily_revenue_query,
        client_id,
        project_ref,
        client_field="client_id",
        project_field="numero_bon_commande_client",
    )

    current_month_revenue = (
        current_month_query.aggregate(total=Sum("total_ttc_apres_remise"))["total"] or 0
    )
    current_month_revenue -= total_avoirs(
        current_period_start, date_to, company_id, devise, client_id, project_ref
    )

    daily_revenue = (
        daily_revenue_query.annotate(date=TruncDate("date_facture"))
        .values("date")
        .annotate(amount=Sum("total_ttc_apres_remise"))
        .order_by("date")
    )
    daily_credits = (
        avoir_queryset(
            seven_days_before_date_to,
            date_to,
            company_id,
            devise,
            client_id,
            project_ref,
        )
        .annotate(date=TruncDate("date_avoir"))
        .values("date")
        .annotate(amount=Sum("total_ttc_apres_remise"))
        .order_by("date")
    )

    daily_amounts = {}
    for item in daily_revenue:
        daily_amounts[item["date"]] = item["amount"] or Decimal("0")
    for item in daily_credits:
        daily_amounts[item["date"]] = daily_amounts.get(item["date"], Decimal("0")) - (
            item["amount"] or Decimal("0")
        )
    revenue_trend = [float(amount) for _, amount in sorted(daily_amounts.items())]

    # Créances en cours
    facture_filter: dict[str, Any] = {
        "date_facture__lte": date_to,
        "devise": devise,
    }
    if date_from:
        facture_filter["date_facture__gte"] = date_from
    if company_id:
        facture_filter["client__company_id"] = company_id
    apply_scope_to_filters(
        facture_filter,
        client_id,
        project_ref,
        client_field="client_id",
        project_field="numero_bon_commande_client",
    )

    factures = annotate_total_reglements(FactureClient.objects.filter(**facture_filter))
    outstanding_current = (
        factures.annotate(outstanding=F("net_total") - F("total_reglements"))
        .filter(outstanding__gt=0)
        .aggregate(total=Coalesce(Sum("outstanding"), Decimal("0")))["total"]
    )

    outstanding_trend = [
        float(outstanding_current * Decimal("0.95")),
        float(outstanding_current),
    ]

    # Montant moyen des factures
    avg_amount_current = (
        annotate_total_reglements(
            FactureClient.objects.filter(**facture_filter)
        ).aggregate(avg=Avg("net_total"))["avg"]
        or 0
    )

    # Nombre de clients actifs
    active_clients = (
        FactureClient.objects.filter(**facture_filter)
        .values("client")
        .distinct()
        .count()
    )

    return {
        "current_month_revenue": {
            "value": float(current_month_revenue),
            "trend": revenue_trend,
        },
        "outstanding_receivables": {
            "value": float(outstanding_current),
            "trend": outstanding_trend,
        },
        "average_invoice_amount": {"value": float(avg_amount_current), "trend": []},
        "active_clients": {"value": active_clients, "trend": []},
    }
