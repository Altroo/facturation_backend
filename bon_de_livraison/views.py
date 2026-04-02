from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle, KeepTogether
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, format_number_for_pdf
from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseBulkDeleteView,
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
    list_select_related = ("client", "mode_paiement", "created_by_user", "livre_par")


class BonDeLivraisonDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = BonDeLivraison
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "bon de livraison"


class GenerateNumeroBonDeLivraisonView(BaseGenerateNumeroView):
    numero_generator = get_next_numero_bon_livraison
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
    list_select_related = ("client", "mode_paiement", "created_by_user", "livre_par")

    def get(self, request, *args, **kwargs):
        """Get list of uninvoiced bons de livraison."""
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

        # Get BLs that are not yet invoiced (excluding 'Facturé' status if it exists)
        # For now, we'll show all BLs - you can add more specific filtering later
        base_queryset = (
            self.model.objects.filter(client__company_id=company_id)
            .select_related(*self.list_select_related)
            .prefetch_related(*self.list_prefetch_related)
            .exclude(statut="Facturé")  # Exclude if there's a "Facturé" status
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


class BonDeLivraisonPDFGenerator(BasePDFGenerator):
    """PDF generator for BonDeLivraison documents."""

    def _create_articles_table_quantity_only(self):
        """Create a simplified articles table showing only designation and quantity."""
        headers = [self._("Designation"), self._("Quantity")]
        col_widths = [14 * cm, 4 * cm]

        # Create header row - Designation left, Qté centered
        table_data = [
            [
                Paragraph(f"<b>{headers[0]}</b>", self.styles["CustomSmall"]),
                Paragraph(f"<b>{headers[1]}</b>", self.styles["CustomSmallCenter"]),
            ]
        ]

        # Add article lines
        for line in (
            self.document.lignes.select_related("article")
            .order_by("article__reference")
            .all()
        ):
            row = []

            # Designation
            designation_text = (
                line.article.designation if line.article.designation else "-"
            )
            if line.article.reference:
                designation_text = (
                    f"<b>{line.article.reference}</b><br/>{designation_text}"
                )
            row.append(Paragraph(designation_text, self.styles["CustomSmall"]))

            # Quantity - centered
            row.append(
                Paragraph(
                    format_number_for_pdf(line.quantity),
                    self.styles["CustomSmallCenter"],
                )
            )

            table_data.append(row)

        # Create table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    # Header styling - soft light gray background
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
                    ("ALIGN", (1, 0), (-1, 0), "CENTER"),  # Center Qté header
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),  # Designation header stays left
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    # Body styling
                    ("VALIGN", (0, 1), (-1, -1), "TOP"),
                    ("ALIGN", (1, 1), (1, -1), "CENTER"),  # Center Qté values
                    ("ALIGN", (0, 1), (0, -1), "LEFT"),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 1), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ]
            )
        )

        return table

    def _build_content(self) -> list:
        """Build PDF content for bon de livraison."""
        elements = []
        elements.append(
            self._build_doc_header(
                f"{self._('Delivery_Number')} {self.document.numero_bon_livraison}",
                f"{self._('Delivery_Date')} {self.document.date_bon_livraison.strftime('%d/%m/%Y')}",
            )
        )
        elements.append(Spacer(1, 0.5 * cm))
        extra_company_lines = None
        if self.document.livre_par:
            extra_company_lines = [
                Paragraph(
                    f"{self._('Delivered_By')}: {self.document.livre_par.nom}",
                    self.styles["CustomSmall"],
                )
            ]
        elements.append(
            self._build_parties_grid(
                Paragraph(
                    f"<b>{self._('Delivery_Issued_By')}</b>",
                    self.styles["SectionHeader"],
                ),
                extra_company_lines=extra_company_lines,
            )
        )
        elements.append(Spacer(1, 0.7 * cm))
        if self.pdf_type == "quantity_only":
            elements.append(self._create_articles_table_quantity_only())
            elements.append(Spacer(1, 0.5 * cm))
        else:
            show_remise = self.pdf_type == "avec_remise"
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
                        self._("Delivery_Amount_Words"),
                        show_remise=show_remise,
                    )
                )
            )
            elements.append(Spacer(1, 0.5 * cm))
        return elements

    def _get_filename(self) -> str:
        """Get PDF filename for bon de livraison."""
        return f"bl_{self.document.numero_bon_livraison.replace('/', '_')}.pdf"

    def _get_pdf_title(self) -> str:
        """Get PDF document title for metadata."""
        client_name = (
            self.document.client.raison_sociale
            if self.document.client.raison_sociale
            else self._("Client")
        )
        return (
            f"{self._('Delivery')} {self.document.numero_bon_livraison} - {client_name}"
        )


class BonDeLivraisonPDFView(APIView):
    """Generate PDF for BonDeLivraison with different variations."""

    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int, language: str = "fr"):
        """Generate and return PDF for the bon de livraison."""
        from core.permissions import can_print
        from rest_framework.exceptions import PermissionDenied
        from django.utils.translation import gettext_lazy as _

        company_id = request.query_params.get("company_id")
        pdf_type = request.query_params.get("type", "normal")

        if not company_id:
            return Response(
                {"error": _("company_id query parameter is required")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        bon_de_livraison = get_object_or_404(
            BonDeLivraison, pk=pk, company_id=company_id
        )

        # Check if user has print permission
        if not can_print(request.user, company.pk):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = BonDeLivraisonPDFGenerator(
            bon_de_livraison, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()


class BulkDeleteBonDeLivraisonView(BaseBulkDeleteView):
    model = BonDeLivraison
    document_name = "bon de livraison"

    def get_queryset_with_related(self, ids):
        return BonDeLivraison.objects.filter(pk__in=ids).select_related("client")

    def get_company_id(self, obj):
        return obj.client.company_id
