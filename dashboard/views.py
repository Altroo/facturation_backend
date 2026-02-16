from datetime import timedelta, datetime, time
from decimal import Decimal

from django.db.models import Sum, Count, F, Avg, Subquery, OuterRef, DecimalField, Case, When, Value, IntegerField
from django.db.models.functions import TruncMonth, TruncDate, Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine
from client.models import Client
from devi.models import Devi, DeviLine
from facture_client.models import FactureClient, FactureClientLine
from facture_proforma.models import FactureProForma, FactureProFormaLine
from reglement.models import Reglement
from .models import MonthlyObjectives
from .serializers import MonthlyObjectivesSerializer


def make_aware_datetime_start(d):
    """Convert a date to timezone-aware datetime at start of day."""
    if d is None:
        return None
    return timezone.make_aware(datetime.combine(d, time.min))


def _annotate_total_reglements(queryset):
    """Annotate a FactureClient queryset with total valid reglements (avoids N+1)."""
    total_reglements_subquery = Subquery(
        Reglement.objects.filter(
            facture_client_id=OuterRef('id'),
            statut="Valide"
        ).values('facture_client_id').annotate(
            total=Sum('montant')
        ).values('total')[:1],
        output_field=DecimalField()
    )
    return queryset.annotate(
        total_reglements=Coalesce(total_reglements_subquery, Decimal("0"))
    )


def make_aware_datetime_end(d):
    """Convert a date to timezone-aware datetime at end of day."""
    if d is None:
        return None
    return timezone.make_aware(datetime.combine(d, time.max))


def parse_date_filters(request):
    """
    Parse date_from, date_to, company_id, and devise query parameters.
    Validates that the user has membership in the requested company.

    Returns (date_from, date_to, company_id, devise) tuple.
    - date_to defaults to today if not provided
    - date_from is None if not provided (no lower bound)
    - company_id is required — raises ValidationError if missing
    - devise defaults to None if not provided (no filtering by currency)
    """
    date_to_str = request.query_params.get("date_to")
    date_from_str = request.query_params.get("date_from")
    company_id_str = request.query_params.get("company_id")
    devise = request.query_params.get("devise")

    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            date_to = timezone.now().date()
    else:
        date_to = timezone.now().date()

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            date_from = None
    else:
        date_from = None

    if company_id_str:
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError({"company_id": "company_id doit être un entier valide."})
    else:
        raise ValidationError({"company_id": "company_id est requis."})

    # Verify user has membership in this company
    if not Membership.objects.filter(
        user=request.user, company_id=company_id
    ).exists():
        raise PermissionDenied(
            "Vous n'avez pas accès aux données de cette société."
        )

    # Validate devise if provided
    if devise and devise not in ['MAD', 'EUR', 'USD']:
        devise = None

    return date_from, date_to, company_id, devise


class MonthlyRevenueEvolutionView(APIView):
    """Monthly revenue evolution."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Default to last 12 months if no date_from
        if not date_from:
            date_from = date_to - timedelta(days=365)

        queryset = FactureClient.objects.filter(
            date_facture__gte=date_from, date_facture__lte=date_to
        )

        if company_id:
            queryset = queryset.filter(client__company_id=company_id)
        
        if devise:
            queryset = queryset.filter(devise=devise)

        data = (
            queryset.annotate(month=TruncMonth("date_facture"))
            .values("month")
            .annotate(revenue=Sum("total_ttc_apres_remise"))
            .order_by("month")
        )

        result = [
            {
                "month": item["month"].strftime("%Y-%m"),
                "revenue": float(item["revenue"] or 0),
            }
            for item in data
        ]

        return Response(result)


class RevenueByDocumentTypeView(APIView):
    """Revenue breakdown by document type."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Build filters
        devi_filter = {"date_devis__lte": date_to}
        proforma_filter = {"date_facture__lte": date_to}
        facture_filter = {"date_facture__lte": date_to}
        bdl_filter = {"date_bon_livraison__lte": date_to}

        if date_from:
            devi_filter["date_devis__gte"] = date_from
            proforma_filter["date_facture__gte"] = date_from
            facture_filter["date_facture__gte"] = date_from
            bdl_filter["date_bon_livraison__gte"] = date_from

        if company_id:
            devi_filter["client__company_id"] = company_id
            proforma_filter["client__company_id"] = company_id
            facture_filter["client__company_id"] = company_id
            bdl_filter["client__company_id"] = company_id
        
        if devise:
            devi_filter["devise"] = devise
            proforma_filter["devise"] = devise
            facture_filter["devise"] = devise
            bdl_filter["devise"] = devise

        devis_total = (
            Devi.objects.filter(**devi_filter).aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )
        proforma_total = (
            FactureProForma.objects.filter(**proforma_filter).aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )
        facture_total = (
            FactureClient.objects.filter(**facture_filter).aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )
        bdl_total = (
            BonDeLivraison.objects.filter(**bdl_filter).aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )

        result = [
            {"type": "Devis", "amount": float(devis_total)},
            {"type": "Facture Pro Forma", "amount": float(proforma_total)},
            {"type": "Facture Client", "amount": float(facture_total)},
            {"type": "Bon de Livraison", "amount": float(bdl_total)},
        ]

        return Response(result)


class PaymentStatusOverviewView(APIView):
    """Payment status distribution of invoices."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id

        factures = _annotate_total_reglements(FactureClient.objects.filter(**facture_filter))

        counts = factures.aggregate(
            fully_paid=Count(Case(
                When(total_reglements__gte=F('total_ttc_apres_remise'), then=Value(1)),
                output_field=IntegerField(),
            )),
            partially_paid=Count(Case(
                When(total_reglements__gt=Decimal("0"), total_reglements__lt=F('total_ttc_apres_remise'), then=Value(1)),
                output_field=IntegerField(),
            )),
            unpaid=Count(Case(
                When(total_reglements__lte=Decimal("0"), then=Value(1)),
                output_field=IntegerField(),
            )),
        )

        result = [
            {"status": "Totalement payée", "count": counts["fully_paid"]},
            {"status": "Partiellement payée", "count": counts["partially_paid"]},
            {"status": "Impayée", "count": counts["unpaid"]},
        ]

        return Response(result)


class CollectionRateView(APIView):
    """Collection rate: percentage of payments collected vs total invoiced."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        reglement_filter = {"date_reglement__lte": date_to, "statut": "Valide"}

        if date_from:
            facture_filter["date_facture__gte"] = date_from
            reglement_filter["date_reglement__gte"] = date_from

        if company_id:
            facture_filter["client__company_id"] = company_id
            reglement_filter["facture_client__client__company_id"] = company_id
        
        if devise:
            facture_filter["devise"] = devise
            reglement_filter["facture_client__devise"] = devise

        total_invoiced = FactureClient.objects.filter(**facture_filter).aggregate(
            total=Sum("total_ttc_apres_remise")
        )["total"] or Decimal("0")

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

        return Response(result)


class TopClientsByRevenueView(APIView):
    """Top 10 clients by revenue."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id
        if devise:
            facture_filter["devise"] = devise

        data = (
            FactureClient.objects.filter(**facture_filter)
            .values("client__id", "client__code_client")
            .annotate(
                revenue=Sum("total_ttc_apres_remise"),
                client_name=F("client__raison_sociale"),
            )
            .order_by("-revenue")[:10]
        )

        result = [
            {
                "client_id": item["client__id"],
                "client_code": item["client__code_client"],
                "client_name": item["client_name"] or item["client__code_client"],
                "revenue": float(item["revenue"] or 0),
            }
            for item in data
        ]

        return Response(result)


class TopProductsByQuantityView(APIView):
    """Top 10 products by quantity sold."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Build date filters for each document type
        devi_filter = {"devis__date_devis__lte": date_to}
        facture_filter = {"facture_client__date_facture__lte": date_to}
        proforma_filter = {"facture_pro_forma__date_facture__lte": date_to}
        bdl_filter = {"bon_de_livraison__date_bon_livraison__lte": date_to}

        if date_from:
            devi_filter["devis__date_devis__gte"] = date_from
            facture_filter["facture_client__date_facture__gte"] = date_from
            proforma_filter["facture_pro_forma__date_facture__gte"] = date_from
            bdl_filter["bon_de_livraison__date_bon_livraison__gte"] = date_from

        if company_id:
            devi_filter["devis__client__company_id"] = company_id
            facture_filter["facture_client__client__company_id"] = company_id
            proforma_filter["facture_pro_forma__client__company_id"] = company_id
            bdl_filter["bon_de_livraison__client__company_id"] = company_id

        # Aggregate from all document lines
        devi_lines = (
            DeviLine.objects.filter(**devi_filter)
            .values("article__id", "article__designation")
            .annotate(qty=Sum("quantity"))
        )
        facture_lines = (
            FactureClientLine.objects.filter(**facture_filter)
            .values("article__id", "article__designation")
            .annotate(qty=Sum("quantity"))
        )
        proforma_lines = (
            FactureProFormaLine.objects.filter(**proforma_filter)
            .values("article__id", "article__designation")
            .annotate(qty=Sum("quantity"))
        )
        bdl_lines = (
            BonDeLivraisonLine.objects.filter(**bdl_filter)
            .values("article__id", "article__designation")
            .annotate(qty=Sum("quantity"))
        )

        # Combine all quantities
        article_quantities = {}

        for line in devi_lines:
            article_id = line["article__id"]
            if article_id not in article_quantities:
                article_quantities[article_id] = {
                    "designation": line["article__designation"],
                    "quantity": 0,
                }
            article_quantities[article_id]["quantity"] += line["qty"] or 0

        for line in facture_lines:
            article_id = line["article__id"]
            if article_id not in article_quantities:
                article_quantities[article_id] = {
                    "designation": line["article__designation"],
                    "quantity": 0,
                }
            article_quantities[article_id]["quantity"] += line["qty"] or 0

        for line in proforma_lines:
            article_id = line["article__id"]
            if article_id not in article_quantities:
                article_quantities[article_id] = {
                    "designation": line["article__designation"],
                    "quantity": 0,
                }
            article_quantities[article_id]["quantity"] += line["qty"] or 0

        for line in bdl_lines:
            article_id = line["article__id"]
            if article_id not in article_quantities:
                article_quantities[article_id] = {
                    "designation": line["article__designation"],
                    "quantity": 0,
                }
            article_quantities[article_id]["quantity"] += line["qty"] or 0

        # Sort and get top 10
        sorted_articles = sorted(
            [{"article_id": k, **v} for k, v in article_quantities.items()],
            key=lambda x: x["quantity"],
            reverse=True,
        )[:10]

        result = [
            {
                "article_id": item["article_id"],
                "designation": item["designation"],
                "quantity": float(item["quantity"]),
            }
            for item in sorted_articles
        ]

        return Response(result)


class QuoteConversionRateView(APIView):
    """Quote status distribution."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        devi_filter = {"date_devis__lte": date_to}
        if date_from:
            devi_filter["date_devis__gte"] = date_from
        if company_id:
            devi_filter["client__company_id"] = company_id

        data = (
            Devi.objects.filter(**devi_filter)
            .values("statut")
            .annotate(count=Count("id"))
        )

        result = [{"status": item["statut"], "count": item["count"]} for item in data]

        return Response(result)


class ProductPriceVolumeAnalysisView(APIView):
    """Price vs volume analysis for products."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"facture_client__date_facture__lte": date_to}
        if date_from:
            facture_filter["facture_client__date_facture__gte"] = date_from
        if company_id:
            facture_filter["facture_client__client__company_id"] = company_id
        if devise:
            facture_filter["devise_prix_vente"] = devise

        # Get total quantity and average price for each article
        article_data = {}

        for line in FactureClientLine.objects.filter(**facture_filter).select_related(
            "article"
        ):
            article_id = line.article.id
            if article_id not in article_data:
                article_data[article_id] = {
                    "designation": line.article.designation,
                    "total_quantity": 0,
                    "total_revenue": Decimal("0"),
                }
            article_data[article_id]["total_quantity"] += line.quantity
            article_data[article_id]["total_revenue"] += line.prix_vente * line.quantity

        result = []
        for article_id, data in article_data.items():
            if data["total_quantity"] > 0:
                avg_price = data["total_revenue"] / data["total_quantity"]
                result.append(
                    {
                        "article_id": article_id,
                        "designation": data["designation"],
                        "average_price": float(avg_price),
                        "total_quantity": float(data["total_quantity"]),
                    }
                )

        return Response(result)


class InvoiceStatusDistributionView(APIView):
    """Invoice status distribution."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id

        data = (
            FactureClient.objects.filter(**facture_filter)
            .values("statut")
            .annotate(count=Count("id"))
        )

        result = [{"status": item["statut"], "count": item["count"]} for item in data]

        return Response(result)


class MonthlyDocumentVolumeView(APIView):
    """Monthly document volume."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Default to last 12 months if no date_from
        if not date_from:
            date_from = date_to - timedelta(days=365)

        devis_query = Devi.objects.filter(
            date_devis__gte=date_from, date_devis__lte=date_to
        )
        facture_query = FactureClient.objects.filter(
            date_facture__gte=date_from, date_facture__lte=date_to
        )
        bdl_query = BonDeLivraison.objects.filter(
            date_bon_livraison__gte=date_from, date_bon_livraison__lte=date_to
        )

        if company_id:
            devis_query = devis_query.filter(client__company_id=company_id)
            facture_query = facture_query.filter(client__company_id=company_id)
            bdl_query = bdl_query.filter(client__company_id=company_id)

        devis_data = (
            devis_query.annotate(month=TruncMonth("date_devis"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        facture_data = (
            facture_query.annotate(month=TruncMonth("date_facture"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        bdl_data = (
            bdl_query.annotate(month=TruncMonth("date_bon_livraison"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Combine data by month
        months = {}

        for item in devis_data:
            month_key = item["month"].strftime("%Y-%m")
            if month_key not in months:
                months[month_key] = {
                    "month": month_key,
                    "devis": 0,
                    "factures": 0,
                    "bdl": 0,
                }
            months[month_key]["devis"] = item["count"]

        for item in facture_data:
            month_key = item["month"].strftime("%Y-%m")
            if month_key not in months:
                months[month_key] = {
                    "month": month_key,
                    "devis": 0,
                    "factures": 0,
                    "bdl": 0,
                }
            months[month_key]["factures"] = item["count"]

        for item in bdl_data:
            month_key = item["month"].strftime("%Y-%m")
            if month_key not in months:
                months[month_key] = {
                    "month": month_key,
                    "devis": 0,
                    "factures": 0,
                    "bdl": 0,
                }
            months[month_key]["bdl"] = item["count"]

        result = sorted(months.values(), key=lambda x: x["month"])

        return Response(result)


class PaymentTimelineView(APIView):
    """Payment timeline: invoices vs actual payments by date."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Default to last 30 days if no date_from
        if not date_from:
            date_from = date_to - timedelta(days=30)

        # Build queries
        invoice_query = FactureClient.objects.filter(
            date_facture__gte=date_from, date_facture__lte=date_to
        )
        payment_query = Reglement.objects.filter(
            date_reglement__gte=date_from,
            date_reglement__lte=date_to,
            statut="Valide",
        )

        if company_id:
            invoice_query = invoice_query.filter(client__company_id=company_id)
            payment_query = payment_query.filter(
                facture_client__client__company_id=company_id
            )
        
        if devise:
            invoice_query = invoice_query.filter(devise=devise)
            payment_query = payment_query.filter(facture_client__devise=devise)

        # Invoices by date
        invoice_data = (
            invoice_query.annotate(date=TruncDate("date_facture"))
            .values("date")
            .annotate(amount=Sum("total_ttc_apres_remise"))
            .order_by("date")
        )

        # Payments by date
        payment_data = (
            payment_query.annotate(date=TruncDate("date_reglement"))
            .values("date")
            .annotate(amount=Sum("montant"))
            .order_by("date")
        )

        # Combine data
        dates = {}

        for item in invoice_data:
            date_key = item["date"].strftime("%Y-%m-%d")
            if date_key not in dates:
                dates[date_key] = {"date": date_key, "invoiced": 0, "collected": 0}
            dates[date_key]["invoiced"] = float(item["amount"] or 0)

        for item in payment_data:
            date_key = item["date"].strftime("%Y-%m-%d")
            if date_key not in dates:
                dates[date_key] = {"date": date_key, "invoiced": 0, "collected": 0}
            dates[date_key]["collected"] = float(item["amount"] or 0)

        result = sorted(dates.values(), key=lambda x: x["date"])

        return Response(result)


class OverdueReceivablesView(APIView):
    """Overdue receivables grouped by aging periods."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id
        if devise:
            facture_filter["devise"] = devise

        factures = _annotate_total_reglements(FactureClient.objects.filter(**facture_filter))

        aging_buckets = {
            "0-30": {"label": "0-30 jours", "count": 0, "amount": Decimal("0")},
            "31-60": {"label": "31-60 jours", "count": 0, "amount": Decimal("0")},
            "61-90": {"label": "61-90 jours", "count": 0, "amount": Decimal("0")},
            "90+": {"label": "90+ jours", "count": 0, "amount": Decimal("0")},
        }

        for facture in factures:
            outstanding = facture.total_ttc_apres_remise - facture.total_reglements

            if outstanding > 0:
                days_overdue = (date_to - facture.date_facture).days

                if days_overdue <= 30:
                    bucket = "0-30"
                elif days_overdue <= 60:
                    bucket = "31-60"
                elif days_overdue <= 90:
                    bucket = "61-90"
                else:
                    bucket = "90+"

                aging_buckets[bucket]["count"] += 1
                aging_buckets[bucket]["amount"] += outstanding

        result = [
            {
                "period": bucket["label"],
                "count": bucket["count"],
                "amount": float(bucket["amount"]),
            }
            for bucket in aging_buckets.values()
        ]

        return Response(result)


class PaymentDelayByClientView(APIView):
    """Payment delay analysis by client."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        reglement_filter = {"statut": "Valide", "date_reglement__lte": date_to}
        if date_from:
            reglement_filter["date_reglement__gte"] = date_from
        if company_id:
            reglement_filter["facture_client__client__company_id"] = company_id

        clients_data = {}

        for reglement in Reglement.objects.filter(**reglement_filter).select_related(
            "facture_client", "facture_client__client"
        ):
            client_id = reglement.facture_client.client.id
            client_name = (
                reglement.facture_client.client.raison_sociale
                or reglement.facture_client.client.code_client
            )

            delay_days = (
                reglement.date_reglement - reglement.facture_client.date_facture
            ).days

            if client_id not in clients_data:
                clients_data[client_id] = {
                    "client_name": client_name,
                    "total_amount": Decimal("0"),
                    "total_delay_weighted": 0,
                }

            clients_data[client_id]["total_amount"] += reglement.montant
            clients_data[client_id]["total_delay_weighted"] += delay_days * float(
                reglement.montant
            )

        result = []
        for client_id, data in clients_data.items():
            if data["total_amount"] > 0:
                avg_delay = data["total_delay_weighted"] / float(data["total_amount"])
                result.append(
                    {
                        "client_id": client_id,
                        "client_name": data["client_name"],
                        "total_amount": float(data["total_amount"]),
                        "average_delay_days": round(avg_delay, 1),
                    }
                )

        return Response(result)


class ClientMultidimensionalProfileView(APIView):
    """Multi-dimensional profile of top 5 clients."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id

        # Get top 5 clients by revenue
        top_clients = (
            FactureClient.objects.filter(**facture_filter)
            .values("client__id", "client__code_client", "client__raison_sociale")
            .annotate(revenue=Sum("total_ttc_apres_remise"))
            .order_by("-revenue")[:5]
        )

        result = []

        for client_data in top_clients:
            client_id = client_data["client__id"]
            client_name = (
                client_data["client__raison_sociale"]
                or client_data["client__code_client"]
            )

            # Volume d'affaires (normalized to 100)
            volume = float(client_data["revenue"] or 0)

            # Fréquence de commande
            frequency = FactureClient.objects.filter(
                client_id=client_id, **facture_filter
            ).count()

            # Montant moyen
            avg_amount = volume / frequency if frequency > 0 else 0

            # Rapidité de paiement (inverse of average delay)
            reglement_filter = {
                "facture_client__client_id": client_id,
                "statut": "Valide",
                "date_reglement__lte": date_to,
            }
            if date_from:
                reglement_filter["date_reglement__gte"] = date_from

            reglements = Reglement.objects.filter(**reglement_filter).select_related(
                "facture_client"
            )

            total_delay = 0
            delay_count = 0
            for reglement in reglements:
                delay = (
                    reglement.date_reglement - reglement.facture_client.date_facture
                ).days
                total_delay += delay
                delay_count += 1

            avg_delay = total_delay / delay_count if delay_count > 0 else 0
            # Convert to a score (lower delay = higher score)
            payment_speed = max(0, 100 - avg_delay) if avg_delay < 100 else 0

            # Taux d'acceptation des devis
            devi_filter = {"client_id": client_id, "date_devis__lte": date_to}
            if date_from:
                devi_filter["date_devis__gte"] = date_from

            total_devis = Devi.objects.filter(**devi_filter).count()
            accepted_devis = Devi.objects.filter(
                **devi_filter, statut="Accepté"
            ).count()
            acceptance_rate = (
                (accepted_devis / total_devis * 100) if total_devis > 0 else 0
            )

            result.append(
                {
                    "client_id": client_id,
                    "client_name": client_name,
                    "metrics": {
                        "volume": volume,
                        "frequency": frequency,
                        "avg_amount": avg_amount,
                        "payment_speed": payment_speed,
                        "acceptance_rate": acceptance_rate,
                    },
                }
            )

        return Response(result)


class KPICardsWithTrendsView(APIView):
    """KPI cards with sparkline data."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def calculate_kpi_for_currency(devise, date_from, date_to, company_id, current_period_start, seven_days_before_date_to):
        """Calculate KPIs for a specific currency."""
        # CA total with trend
        current_month_query = FactureClient.objects.filter(
            date_facture__gte=current_period_start, 
            date_facture__lte=date_to,
            devise=devise
        )
        daily_revenue_query = FactureClient.objects.filter(
            date_facture__gte=seven_days_before_date_to, 
            date_facture__lte=date_to,
            devise=devise
        )

        if company_id:
            current_month_query = current_month_query.filter(
                client__company_id=company_id
            )
            daily_revenue_query = daily_revenue_query.filter(
                client__company_id=company_id
            )

        current_month_revenue = (
            current_month_query.aggregate(total=Sum("total_ttc_apres_remise"))["total"]
            or 0
        )

        daily_revenue = (
            daily_revenue_query.annotate(date=TruncDate("date_facture"))
            .values("date")
            .annotate(amount=Sum("total_ttc_apres_remise"))
            .order_by("date")
        )

        revenue_trend = [float(item["amount"] or 0) for item in daily_revenue]

        # Créances en cours
        facture_filter = {"date_facture__lte": date_to, "devise": devise}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id

        factures = _annotate_total_reglements(FactureClient.objects.filter(**facture_filter))
        outstanding_current = factures.annotate(
            outstanding=F('total_ttc_apres_remise') - F('total_reglements')
        ).filter(outstanding__gt=0).aggregate(
            total=Coalesce(Sum('outstanding'), Decimal("0"))
        )["total"]

        outstanding_trend = [
            float(outstanding_current * Decimal("0.95")),
            float(outstanding_current),
        ]

        # Montant moyen des factures
        avg_amount_current = (
            FactureClient.objects.filter(**facture_filter).aggregate(
                avg=Avg("total_ttc_apres_remise")
            )["avg"]
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

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        today = timezone.now()
        seven_days_before_date_to = date_to - timedelta(days=7)

        # CA total with trend
        if date_from:
            current_period_start = date_from
        else:
            # Default to current month
            current_period_start = today.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).date()

        # Calculate KPIs for each currency
        result = {
            "currency_data": {
                "MAD": KPICardsWithTrendsView.calculate_kpi_for_currency(
                    "MAD", date_from, date_to, company_id, current_period_start, seven_days_before_date_to
                ),
                "EUR": KPICardsWithTrendsView.calculate_kpi_for_currency(
                    "EUR", date_from, date_to, company_id, current_period_start, seven_days_before_date_to
                ),
                "USD": KPICardsWithTrendsView.calculate_kpi_for_currency(
                    "USD", date_from, date_to, company_id, current_period_start, seven_days_before_date_to
                ),
            }
        }

        return Response(result)


class MonthlyObjectivesView(APIView):
    """Monthly objectives' achievement."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Use date range or default to current month
        if date_from:
            current_period_start = date_from
        else:
            today = timezone.now()
            current_period_start = today.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).date()

        facture_filter = {
            "date_facture__gte": current_period_start,
            "date_facture__lte": date_to,
        }
        devi_filter = {
            "date_devis__gte": current_period_start,
            "date_devis__lte": date_to,
        }

        if company_id:
            facture_filter["client__company_id"] = company_id
            devi_filter["client__company_id"] = company_id

        # Calculate revenue for each currency
        current_revenue_mad = (
            FactureClient.objects.filter(**facture_filter, devise="MAD").aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )
        current_revenue_eur = (
            FactureClient.objects.filter(**facture_filter, devise="EUR").aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )
        current_revenue_usd = (
            FactureClient.objects.filter(**facture_filter, devise="USD").aggregate(
                total=Sum("total_ttc_apres_remise")
            )["total"]
            or 0
        )

        invoice_count = FactureClient.objects.filter(**facture_filter).count()

        # Quote conversion
        total_quotes = Devi.objects.filter(**devi_filter).count()
        accepted_quotes = Devi.objects.filter(**devi_filter, statut="Accepté").count()
        conversion_rate = (
            (accepted_quotes / total_quotes * 100) if total_quotes > 0 else 0
        )

        # Get objectives from database
        try:
            if company_id:
                objectives = MonthlyObjectives.objects.get(company_id=company_id)
                revenue_objective = float(objectives.objectif_ca)
                revenue_objective_eur = float(objectives.objectif_ca_eur or 0)
                revenue_objective_usd = float(objectives.objectif_ca_usd or 0)
                invoice_objective = objectives.objectif_factures
                conversion_objective = float(objectives.objectif_conversion)
                objectives_set = True
            else:
                # Default values if no company specified
                revenue_objective = 0
                revenue_objective_eur = 0
                revenue_objective_usd = 0
                invoice_objective = 0
                conversion_objective = 0
                objectives_set = False
        except MonthlyObjectives.DoesNotExist:
            revenue_objective = 0
            revenue_objective_eur = 0
            revenue_objective_usd = 0
            invoice_objective = 0
            conversion_objective = 0
            objectives_set = False

        result = {
            "revenue": {
                "current": float(current_revenue_mad),
                "objective": revenue_objective,
                "percentage": (
                    min(100, int(float(current_revenue_mad) / revenue_objective * 100))
                    if revenue_objective > 0
                    else 0
                ),
            },
            "revenue_eur": {
                "current": float(current_revenue_eur),
                "objective": revenue_objective_eur,
                "percentage": (
                    min(100, int(float(current_revenue_eur) / revenue_objective_eur * 100))
                    if revenue_objective_eur > 0
                    else 0
                ),
            },
            "revenue_usd": {
                "current": float(current_revenue_usd),
                "objective": revenue_objective_usd,
                "percentage": (
                    min(100, int(float(current_revenue_usd) / revenue_objective_usd * 100))
                    if revenue_objective_usd > 0
                    else 0
                ),
            },
            "invoices": {
                "current": invoice_count,
                "objective": invoice_objective,
                "percentage": (
                    min(100, int(invoice_count / invoice_objective * 100))
                    if invoice_objective > 0
                    else 0
                ),
            },
            "conversion": {
                "current": conversion_rate,
                "objective": conversion_objective,
                "percentage": (
                    min(100, int(conversion_rate / conversion_objective * 100))
                    if conversion_objective > 0
                    else 0
                ),
            },
            "objectives_set": objectives_set,
        }

        return Response(result)


class DiscountImpactAnalysisView(APIView):
    """Discount impact on revenue."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"date_facture__lte": date_to}
        if date_from:
            facture_filter["date_facture__gte"] = date_from
        if company_id:
            facture_filter["client__company_id"] = company_id
        if devise:
            facture_filter["devise"] = devise

        # Get all documents with remise data
        result = []

        for facture in FactureClient.objects.filter(**facture_filter).exclude(remise=0):
            discount_amount = facture.total_ttc - facture.total_ttc_apres_remise
            result.append(
                {
                    "document_id": facture.id,
                    "document_type": "Facture",
                    "total_amount": float(facture.total_ttc_apres_remise),
                    "discount_amount": float(discount_amount),
                }
            )

        return Response(result)


class ProductMarginVolumeView(APIView):
    """Product margin vs volume analysis."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        facture_filter = {"facture_client__date_facture__lte": date_to}
        if date_from:
            facture_filter["facture_client__date_facture__gte"] = date_from
        if company_id:
            facture_filter["facture_client__client__company_id"] = company_id
        if devise:
            facture_filter["devise_prix_vente"] = devise

        article_data = {}

        for line in FactureClientLine.objects.filter(**facture_filter).select_related(
            "article"
        ):
            article_id = line.article.id
            if article_id not in article_data:
                article_data[article_id] = {
                    "designation": line.article.designation,
                    "total_quantity": 0,
                    "total_margin": Decimal("0"),
                }

            margin_per_unit = line.prix_vente - line.prix_achat
            article_data[article_id]["total_quantity"] += line.quantity
            article_data[article_id]["total_margin"] += margin_per_unit * line.quantity

        result = []
        for article_id, data in article_data.items():
            if data["total_quantity"] > 0:
                avg_margin = data["total_margin"] / data["total_quantity"]
                result.append(
                    {
                        "article_id": article_id,
                        "designation": data["designation"],
                        "average_margin": float(avg_margin),
                        "total_quantity": float(data["total_quantity"]),
                    }
                )

        return Response(result)


class MonthlyGlobalPerformanceView(APIView):
    """Global performance comparison: current period vs previous period."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        today = timezone.now()

        # If date range provided, use it; otherwise use current month
        if date_from:
            current_start = date_from
            current_end = date_to
            # Calculate previous period of same duration
            duration = (date_to - date_from).days
            previous_end = date_from - timedelta(days=1)
            previous_start = previous_end - timedelta(days=duration)
        else:
            current_start = today.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).date()
            current_end = date_to

            # Previous month
            if current_start.month == 1:
                previous_start = current_start.replace(
                    year=current_start.year - 1, month=12
                )
            else:
                previous_start = current_start.replace(month=current_start.month - 1)
            previous_end = current_start - timedelta(days=1)

        # Build queries with company filter
        current_facture_query = FactureClient.objects.filter(
            date_facture__gte=current_start, date_facture__lte=current_end
        )
        current_devi_query = Devi.objects.filter(
            date_devis__gte=current_start, date_devis__lte=current_end
        )
        current_reglement_query = Reglement.objects.filter(
            date_reglement__gte=current_start,
            date_reglement__lte=current_end,
            statut="Valide",
        )
        # Use timezone-aware datetimes for DateTimeField
        current_client_query = Client.objects.filter(
            date_created__gte=make_aware_datetime_start(current_start),
            date_created__lte=make_aware_datetime_end(current_end),
        )

        previous_facture_query = FactureClient.objects.filter(
            date_facture__gte=previous_start, date_facture__lte=previous_end
        )
        previous_devi_query = Devi.objects.filter(
            date_devis__gte=previous_start, date_devis__lte=previous_end
        )
        previous_reglement_query = Reglement.objects.filter(
            date_reglement__gte=previous_start,
            date_reglement__lte=previous_end,
            statut="Valide",
        )
        # Use timezone-aware datetimes for DateTimeField
        previous_client_query = Client.objects.filter(
            date_created__gte=make_aware_datetime_start(previous_start),
            date_created__lte=make_aware_datetime_end(previous_end),
        )

        if company_id:
            current_facture_query = current_facture_query.filter(
                client__company_id=company_id
            )
            current_devi_query = current_devi_query.filter(
                client__company_id=company_id
            )
            current_reglement_query = current_reglement_query.filter(
                facture_client__client__company_id=company_id
            )
            current_client_query = current_client_query.filter(company_id=company_id)

            previous_facture_query = previous_facture_query.filter(
                client__company_id=company_id
            )
            previous_devi_query = previous_devi_query.filter(
                client__company_id=company_id
            )
            previous_reglement_query = previous_reglement_query.filter(
                facture_client__client__company_id=company_id
            )
            previous_client_query = previous_client_query.filter(company_id=company_id)

        # Current period metrics
        current_revenue = (
            current_facture_query.aggregate(total=Sum("total_ttc_apres_remise"))[
                "total"
            ]
            or 0
        )

        current_quotes = current_devi_query.count()

        current_accepted = current_devi_query.filter(statut="Accepté").count()
        current_conversion = (
            (current_accepted / current_quotes * 100) if current_quotes > 0 else 0
        )

        current_collected = (
            current_reglement_query.aggregate(total=Sum("montant"))["total"] or 0
        )

        current_new_clients = current_client_query.count()

        # Previous period metrics
        previous_revenue = (
            previous_facture_query.aggregate(total=Sum("total_ttc_apres_remise"))[
                "total"
            ]
            or 0
        )

        previous_quotes = previous_devi_query.count()

        previous_accepted = previous_devi_query.filter(statut="Accepté").count()
        previous_conversion = (
            (previous_accepted / previous_quotes * 100) if previous_quotes > 0 else 0
        )

        previous_collected = (
            previous_reglement_query.aggregate(total=Sum("montant"))["total"] or 0
        )

        previous_new_clients = previous_client_query.count()

        result = {
            "current": {
                "revenue": float(current_revenue),
                "quotes": current_quotes,
                "conversion": current_conversion,
                "collection": float(current_collected),
                "new_clients": current_new_clients,
            },
            "previous": {
                "revenue": float(previous_revenue),
                "quotes": previous_quotes,
                "conversion": previous_conversion,
                "collection": float(previous_collected),
                "new_clients": previous_new_clients,
            },
        }

        return Response(result)


class SectionMicroTrendsView(APIView):
    """Micro trends for each dashboard section."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        date_from, date_to, company_id, devise = parse_date_filters(request)

        # Default to last 30 days if no date_from
        if not date_from:
            date_from = date_to - timedelta(days=30)

        # Build queries
        financial_query = FactureClient.objects.filter(
            date_facture__gte=date_from, date_facture__lte=date_to
        )
        commercial_query = Devi.objects.filter(
            date_devis__gte=date_from, date_devis__lte=date_to
        )
        # Use timezone-aware datetimes for DateTimeField
        operational_query = FactureClient.objects.filter(
            date_created__gte=make_aware_datetime_start(date_from),
            date_created__lte=make_aware_datetime_end(date_to),
        )
        cashflow_query = Reglement.objects.filter(
            date_reglement__gte=date_from, date_reglement__lte=date_to, statut="Valide"
        )

        if company_id:
            financial_query = financial_query.filter(client__company_id=company_id)
            commercial_query = commercial_query.filter(client__company_id=company_id)
            operational_query = operational_query.filter(client__company_id=company_id)
            cashflow_query = cashflow_query.filter(
                facture_client__client__company_id=company_id
            )

        # Financial section trend
        financial_trend = (
            financial_query.annotate(date=TruncDate("date_facture"))
            .values("date")
            .annotate(amount=Sum("total_ttc_apres_remise"))
            .order_by("date")
        )

        # Commercial section trend (quotes created)
        commercial_trend = (
            commercial_query.annotate(date=TruncDate("date_devis"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Operational section trend (invoices created)
        operational_trend = (
            operational_query.annotate(date=TruncDate("date_created"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Cash flow section trend (payments)
        cashflow_trend = (
            cashflow_query.annotate(date=TruncDate("date_reglement"))
            .values("date")
            .annotate(amount=Sum("montant"))
            .order_by("date")
        )

        result = {
            "financial": [float(item["amount"] or 0) for item in financial_trend],
            "commercial": [item["count"] for item in commercial_trend],
            "operational": [item["count"] for item in operational_trend],
            "cashflow": [float(item["amount"] or 0) for item in cashflow_trend],
        }

        return Response(result)


class MonthlyObjectivesListCreateView(APIView):
    """List all monthly objectives or create a new one."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request):
        objectives = MonthlyObjectives.objects.all()
        serializer = MonthlyObjectivesSerializer(objectives, many=True)
        return Response(serializer.data)

    @staticmethod
    def post(request):
        serializer = MonthlyObjectivesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MonthlyObjectivesDetailView(APIView):
    """Retrieve, update or delete a monthly objective."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get_object(pk):
        try:
            return MonthlyObjectives.objects.get(pk=pk)
        except MonthlyObjectives.DoesNotExist:
            return None

    def get(self, request, pk):
        objectives = self.get_object(pk)
        if not objectives:
            return Response(
                {"detail": "Objectifs non trouvés"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = MonthlyObjectivesSerializer(objectives)
        return Response(serializer.data)

    def put(self, request, pk):
        objectives = self.get_object(pk)
        if not objectives:
            return Response(
                {"detail": "Objectifs non trouvés"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = MonthlyObjectivesSerializer(objectives, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk):
        objectives = self.get_object(pk)
        if not objectives:
            return Response(
                {"detail": "Objectifs non trouvés"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = MonthlyObjectivesSerializer(
            objectives, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        objectives = self.get_object(pk)
        if not objectives:
            return Response(
                {"detail": "Objectifs non trouvés"},
                status=status.HTTP_404_NOT_FOUND,
            )
        objectives.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MonthlyObjectivesByCompanyView(APIView):
    """Retrieve monthly objectives for a specific company."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def get(request, company_id):
        try:
            objectives = MonthlyObjectives.objects.get(company_id=company_id)
            serializer = MonthlyObjectivesSerializer(objectives)
            return Response(serializer.data)
        except MonthlyObjectives.DoesNotExist:
            return Response(
                {"detail": "Objectifs non trouvés pour cette société"},
                status=status.HTTP_404_NOT_FOUND,
            )
