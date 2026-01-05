from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response

from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
)
from facturation_backend.utils import CustomPagination
from bon_de_livraison.utils import get_next_numero_bon_livraison
from reglement.models import Reglement
from .filters import FactureClientFilter
from .models import FactureClient
from .serializers import (
    FactureClientSerializer,
    FactureClientDetailSerializer,
    FactureClientListSerializer,
)
from .utils import get_next_numero_facture_client


class FactureClientListCreateView(BaseDocumentListCreateView):
    model = FactureClient
    filter_class = FactureClientFilter
    list_serializer_class = FactureClientListSerializer
    create_serializer_class = FactureClientSerializer
    detail_serializer_class = FactureClientDetailSerializer
    document_name = "la facture client"

    def get(self, request, *args, **kwargs):
        """
        Override to add extra stats:
        - chiffre_affaire_total: Total TTC après remise of all factures for the company
        - total_reglements: Sum of all valid règlements for the company
        - total_impayes: chiffre_affaire_total - total_reglements
        """
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)
        base_queryset = self.model.objects.filter(client__company_id=company_id)
        filterset = self.filter_class(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        # Calculate aggregated stats for the company
        # Chiffre d'affaire total = sum of all factures' total_ttc_apres_remise
        factures = FactureClient.objects.filter(client__company_id=company_id)
        chiffre_affaire_total = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")

        # Total des règlements = sum of all valid règlements
        total_reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

        # Total des impayés = CA - règlements
        total_impayes = chiffre_affaire_total - total_reglements

        extra_stats = {
            "chiffre_affaire_total": str(chiffre_affaire_total),
            "total_reglements": str(total_reglements),
            "total_impayes": str(total_impayes),
        }

        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = self.list_serializer_class(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)
            response.data.update(extra_stats)
            return response

        serializer = self.list_serializer_class(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(
            {
                "results": serializer.data,
                **extra_stats,
            },
            status=status.HTTP_200_OK,
        )


class FactureClientDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = FactureClient
    detail_serializer_class = FactureClientDetailSerializer
    document_name = "facture client"


class GenerateNumeroFactureView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_facture_client)
    response_key = "numero_facture"


class FactureClientStatusUpdateView(BaseStatusUpdateView):
    model = FactureClient
    document_name = "facture client"


class FactureClientConvertToBonDeLivraisonView(BaseConversionView):
    model = FactureClient
    document_name = "facture client"
    numero_generator = staticmethod(get_next_numero_bon_livraison)
    conversion_method = "convert_to_bon_de_livraison"
    numero_param_name = "numero_bon_livraison"
