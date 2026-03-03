from django.shortcuts import get_object_or_404
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, KeepTogether
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

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
from facture_client.utils import get_next_numero_facture_client
from facture_proforma.utils import get_next_numero_facture_pro_forma
from .filters import DeviFilter
from .models import Devi
from .serializers import (
    DeviSerializer,
    DeviDetailSerializer,
    DeviListSerializer,
)
from .utils import get_next_numero_devis


class DeviListCreateView(BaseDocumentListCreateView):
    model = Devi
    filter_class = DeviFilter
    list_serializer_class = DeviListSerializer
    create_serializer_class = DeviSerializer
    detail_serializer_class = DeviDetailSerializer
    document_name = "le devis"


class DeviDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = Devi
    detail_serializer_class = DeviDetailSerializer
    document_name = "devis"


class GenerateNumeroDevisView(BaseGenerateNumeroView):
    numero_generator = get_next_numero_devis
    response_key = "numero_devis"


class DeviStatusUpdateView(BaseStatusUpdateView):
    model = Devi
    document_name = "devis"


class DeviConvertToFactureProformaView(BaseConversionView):
    model = Devi
    document_name = "devis"
    numero_generator = staticmethod(get_next_numero_facture_pro_forma)
    conversion_method = "convert_to_facture_proforma"


class DeviConvertToFactureClientView(BaseConversionView):
    model = Devi
    document_name = "devis"
    numero_generator = staticmethod(get_next_numero_facture_client)
    conversion_method = "convert_to_facture_client"


class DeviPDFGenerator(BasePDFGenerator):
    """PDF generator for Devis documents."""

    def _build_content(self) -> list:
        """Build PDF content for devis."""
        elements = []
        elements.append(
            self._build_doc_header(
                f"{self._('Quote_Number')} {self.document.numero_devis}",
                f"{self._('Quote_Date')} {self.document.date_devis.strftime('%d/%m/%Y')}",
            )
        )
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(
            self._build_parties_grid(
                Paragraph(
                    f"<b>{self._('Quote_Issued_By')}</b>",
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
                    self._("Quote_Amount_Words"),
                    default_remarks_key="Quote_Default_Remarks",
                    show_remise=show_remise,
                )
            )
        )
        return elements

    def _get_filename(self) -> str:
        """Get PDF filename for devis."""
        return f"devis_{self.document.numero_devis.replace('/', '_')}.pdf"

    def _get_pdf_title(self) -> str:
        """Get PDF document title for metadata."""
        client_name = (
            self.document.client.raison_sociale
            if self.document.client.raison_sociale
            else self._("Client")
        )
        doc_type = self._("Quote")
        return f"{doc_type} {self.document.numero_devis} - {client_name}"


class DeviPDFView(APIView):
    """Generate PDF for Devis with different variations."""

    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int, language: str = "fr"):
        """Generate and return PDF for the devis."""
        from core.permissions import can_print
        from rest_framework.exceptions import PermissionDenied
        from django.utils.translation import gettext_lazy as _

        company_id = request.query_params.get("company_id")
        pdf_type = request.query_params.get("type", "avec_remise")

        if not company_id:
            return Response(
                {"error": "company_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        devis = get_object_or_404(Devi, pk=pk, company_id=company_id)

        # Check if user has print permission
        if not can_print(request.user, company.pk):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = DeviPDFGenerator(devis, company, pdf_type, language)
        return pdf_generator.generate_pdf()


class BulkDeleteDeviView(BaseBulkDeleteView):
    model = Devi
    document_name = "devis"

    def get_queryset_with_related(self, ids):
        return Devi.objects.filter(pk__in=ids).select_related("client")

    def get_company_id(self, obj):
        return obj.client.company_id
