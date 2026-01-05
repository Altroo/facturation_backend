from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response

from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
)
from facturation_backend.utils import CustomPagination
from .filters import BonDeLivraisonFilter
from .models import BonDeLivraison
from .serializers import (
    BonDeLivraisonSerializer,
    BonDeLivraisonDetailSerializer,
    BonDeLivraisonListSerializer,
)
from .utils import get_next_numero_bon_livraison


class BonDeLivraisonListCreateView(BaseDocumentListCreateView):
    model = BonDeLivraison
    filter_class = BonDeLivraisonFilter
    list_serializer_class = BonDeLivraisonListSerializer
    create_serializer_class = BonDeLivraisonSerializer
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "le bon de livraison"


class BonDeLivraisonDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = BonDeLivraison
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "bon de livraison"


class GenerateNumeroBonDeLivraisonView(BaseGenerateNumeroView):
    numero_generator = staticmethod(get_next_numero_bon_livraison)
    response_key = "numero_bon_livraison"


class BonDeLivraisonStatusUpdateView(BaseStatusUpdateView):
    model = BonDeLivraison
    document_name = "bon de livraison"


class BonDeLivraisonUninvoicedListView(BaseDocumentListCreateView):
    """
    List bons de livraison that haven't been invoiced yet.
    GET only - returns BLs with statut='Brouillon' or 'Validé' (not yet converted to facture).
    """
    model = BonDeLivraison
    filter_class = BonDeLivraisonFilter
    list_serializer_class = BonDeLivraisonListSerializer
    document_name = "le bon de livraison"

    def get(self, request, *args, **kwargs):
        """Get list of uninvoiced bons de livraison."""
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)

        # Get BLs that are not yet invoiced (excluding 'Facturé' status if it exists)
        # For now, we'll show all BLs - you can add more specific filtering later
        base_queryset = self.model.objects.filter(
            client__company_id=company_id
        ).exclude(
            statut="Facturé"  # Exclude if there's a "Facturé" status
        )

        filterset = self.filter_class(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = self.list_serializer_class(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)

        serializer = self.list_serializer_class(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        """Disable POST for uninvoiced list."""
        return Response(
            {"detail": _("Création non autorisée depuis cette vue.")},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
