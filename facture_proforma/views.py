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
from .filters import FactureProFormaFilter
from .models import FactureProForma
from .serializers import (
    FactureProformaSerializer,
    FactureProformaDetailSerializer,
    FactureProformaListSerializer,
)
from .utils import get_next_numero_facture_pro_forma


class FactureProFormaListCreateView(BaseDocumentListCreateView):
    model = FactureProForma
    filter_class = FactureProFormaFilter
    list_serializer_class = FactureProformaListSerializer
    create_serializer_class = FactureProformaSerializer
    detail_serializer_class = FactureProformaDetailSerializer
    document_name = "la facture proforma"


class FactureProFormaDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = FactureProForma
    detail_serializer_class = FactureProformaDetailSerializer
    document_name = "facture proforma"


class GenerateNumeroFactureView(BaseGenerateNumeroView):
    numero_generator = get_next_numero_facture_pro_forma
    response_key = "numero_facture"


class FactureProFormaStatusUpdateView(BaseStatusUpdateView):
    model = FactureProForma
    document_name = "facture proforma"


class FactureProFormaConvertToFactureClientView(BaseConversionView):
    model = FactureProForma
    document_name = "facture pro-forma"
    numero_generator = staticmethod(get_next_numero_facture_client)
    conversion_method = "convert_to_facture_client"


class FactureProFormaPDFGenerator(BasePDFGenerator):
    """PDF generator for FactureProForma documents."""

    def _build_content(self) -> list:
        """Build PDF content for facture pro-forma."""
        elements = []
        elements.append(
            self._build_doc_header(
                f"{self._('Proforma_Number')} {self.document.numero_facture}",
                f"{self._('Proforma_Date')} {self.document.date_facture.strftime('%d/%m/%Y')}",
            )
        )
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(
            self._build_parties_grid(
                Paragraph(
                    f"<b>{self._('Proforma_Issued_By')}</b>",
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
                    self._("Proforma_Amount_Words"),
                    default_remarks_key="Proforma_Default_Remarks",
                    show_remise=show_remise,
                )
            )
        )
        return elements

    def _get_filename(self) -> str:
        """Get PDF filename for facture pro-forma."""
        return f"facture_proforma_{self.document.numero_facture.replace('/', '_')}.pdf"

    def _get_pdf_title(self) -> str:
        """Get PDF document title for metadata."""
        client_name = (
            self.document.client.raison_sociale
            if self.document.client.raison_sociale
            else self._("Client")
        )
        return f"{self._('Proforma')} {self.document.numero_facture} - {client_name}"


class FactureProFormaPDFView(APIView):
    """Generate PDF for FactureProForma with different variations."""

    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int, language: str = "fr"):
        """Generate and return PDF for the facture pro forma."""
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
        facture_proforma = get_object_or_404(
            FactureProForma, pk=pk, company_id=company_id
        )

        # Check if user has print permission
        if not can_print(request.user, company.pk):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = FactureProFormaPDFGenerator(
            facture_proforma, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()


class BulkDeleteFactureProFormaView(BaseBulkDeleteView):
    model = FactureProForma
    document_name = "facture pro forma"

    def get_queryset_with_related(self, ids):
        return FactureProForma.objects.filter(pk__in=ids).select_related("client")

    def get_company_id(self, obj):
        return obj.client.company_id
