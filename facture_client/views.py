from decimal import Decimal

from django.db.models import Q, F, Sum as DjangoSum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, KeepTogether
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from bon_de_livraison.utils import get_next_numero_bon_livraison
from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator
from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
    BaseBulkDeleteView,
)
from facturation_backend.utils import CustomPagination
from .filters import FactureClientFilter
from .models import FactureClient
from .serializers import (
    FactureClientSerializer,
    FactureClientDetailSerializer,
    FactureClientListSerializer,
)
from .stats import get_stats_by_currency
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
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError(
                {"company_id": _("company_id doit être un entier valide.")}
            )
        self._check_company_access(request, company_id)
        base_queryset = (
            self.model.objects.filter(client__company_id=company_id)
            .select_related(*self.list_select_related)
            .prefetch_related(*self.list_prefetch_related)
        )
        filterset = self.filter_class(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        extra_stats = {
            "stats_by_currency": get_stats_by_currency(company_id),
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
    numero_generator = get_next_numero_facture_client
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


class FactureClientUnpaidListView(BaseDocumentListCreateView):
    """
    List factures with unpaid amounts (total_impayes > 0).
    GET only - returns factures where reglements don't cover full amount.
    Includes same extra stats as FactureClientListCreateView.
    """

    model = FactureClient
    filter_class = FactureClientFilter
    list_serializer_class = FactureClientListSerializer
    document_name = "la facture client"

    def get(self, request, *args, **kwargs):
        """Get list of unpaid factures with stats."""
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError(
                {"company_id": _("company_id doit être un entier valide.")}
            )
        self._check_company_access(request, company_id)

        # Get all factures for the company
        base_queryset = (
            self.model.objects.filter(client__company_id=company_id)
            .select_related(*self.list_select_related)
            .prefetch_related(*self.list_prefetch_related)
        )

        # Annotate with total paid per facture and filter for unpaid
        queryset = base_queryset.annotate(
            total_paid=Coalesce(
                DjangoSum(
                    "reglements__montant",
                    filter=Q(reglements__statut="Valide"),
                ),
                Value(Decimal("0.00")),
            )
        ).filter(
            # Only include factures where payment is less than total
            total_paid__lt=F("total_ttc_apres_remise")
        )

        filterset = self.filter_class(request.GET, queryset=queryset)
        ordered_qs = filterset.qs.order_by("-id")

        extra_stats = {
            "stats_by_currency": get_stats_by_currency(company_id),
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

    def post(self, request, *args, **kwargs):
        """Disable POST for unpaid list."""
        return Response(
            {"detail": _("Création non autorisée depuis cette vue.")},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class FactureClientForPaymentView(APIView):
    """
    GET: List factures available for payment (Envoyé or Accepté status) with remaining unpaid amounts.
    Used for the reglement form dropdown.
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        from account.models import Membership

        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def get(self, request):
        """Get list of factures available for payment with remaining amounts."""
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("company_id is required"))

        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError(
                {"company_id": _("company_id doit être un entier valide.")}
            )

        if not self._has_membership(request.user, company_id):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à accéder à cette société.")
            )

        # Get factures with allowed statuses
        factures = (
            FactureClient.objects.filter(
                client__company_id=company_id, statut__in=["Envoyé", "Accepté"]
            )
            .select_related("client")
            .annotate(
                total_paid=Coalesce(
                    DjangoSum(
                        "reglements__montant", filter=Q(reglements__statut="Valide")
                    ),
                    Value(Decimal("0.00")),
                )
            )
            .filter(
                # Only include factures with remaining amount to pay
                total_paid__lt=F("total_ttc_apres_remise")
            )
            .order_by("-date_facture")
        )

        # Build response data
        results = []
        for facture in factures:
            remaining = facture.total_ttc_apres_remise - facture.total_paid  # type: ignore[attr-defined]
            results.append(
                {
                    "id": facture.id,
                    "numero_facture": facture.numero_facture,
                    "client_name": (
                        facture.client.raison_sociale
                        or f"{facture.client.prenom or ''} {facture.client.nom or ''}".strip()
                        or "Client inconnu"
                    ),
                    "date_facture": facture.date_facture,
                    "total_ttc_apres_remise": str(facture.total_ttc_apres_remise),
                    "total_paid": str(facture.total_paid),  # type: ignore[attr-defined]
                    "remaining_amount": str(remaining),
                    "statut": facture.statut,
                    "devise": facture.devise,
                }
            )

        return Response(results, status=status.HTTP_200_OK)


class FactureClientPDFGenerator(BasePDFGenerator):
    """PDF generator for FactureClient documents."""

    def _build_content(self) -> list:
        """Build PDF content for facture client."""
        elements = []
        elements.append(
            self._build_doc_header(
                f"{self._('Invoice_Number')} {self.document.numero_facture}",
                f"{self._('Invoice_Date')} {self.document.date_facture.strftime('%d/%m/%Y')}",
            )
        )
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(
            self._build_parties_grid(
                Paragraph(
                    f"<b>{self._('Invoice_Issued_By')}</b>",
                    self.styles["SectionHeader"],
                )
            )
        )
        elements.append(Spacer(1, 0.7 * cm))
        show_remise = self.pdf_type != "sans_remise"
        show_unite = self.pdf_type == "avec_unite"
        elements.append(
            self._build_standard_articles_table(
                show_remise=show_remise, show_unite=show_unite
            )
        )
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(
            KeepTogether(
                self._build_tail(
                    self._("Invoice_Amount_Words"),
                    default_remarks_key="Invoice_Default_Remarks",
                    show_remise=show_remise,
                )
            )
        )
        return elements

    def _get_filename(self) -> str:
        """Get PDF filename for facture client."""
        return f"facture_{self.document.numero_facture.replace('/', '_')}.pdf"

    def _get_pdf_title(self) -> str:
        """Get PDF document title for metadata."""
        client_name = (
            self.document.client.raison_sociale
            if self.document.client.raison_sociale
            else self._("Client")
        )
        doc_type = self._("Invoice")
        return f"{doc_type} {self.document.numero_facture} - {client_name}"


class FactureClientPDFView(APIView):
    """Generate PDF for FactureClient with different variations."""

    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int, language: str = "fr"):
        """Generate and return PDF for the facture client."""
        from core.permissions import can_print

        company_id = request.query_params.get("company_id")
        pdf_type = request.query_params.get("type", "avec_remise")

        if not company_id:
            return Response(
                {"error": "company_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        facture_client = get_object_or_404(FactureClient, pk=pk, company_id=company_id)

        # Check if user has print permission
        if not can_print(request.user, company.pk):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = FactureClientPDFGenerator(
            facture_client, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()


class BulkDeleteFactureClientView(BaseBulkDeleteView):
    model = FactureClient
    document_name = "facture client"

    def get_queryset_with_related(self, ids):
        return FactureClient.objects.filter(pk__in=ids).select_related("client")

    def get_company_id(self, obj):
        return obj.client.company_id
