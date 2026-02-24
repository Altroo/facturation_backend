from decimal import Decimal

from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle, KeepTogether
from reportlab.platypus.flowables import HRFlowable
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, number_to_french_words, number_to_english_words, format_number_for_pdf
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

        # ===== HEADER SECTION =====
        # Logo on the left, Document title + date on the right (no space between)
        logo_img = self._get_logo_image()

        # Document number and date together (line 1 and line 2, no space)
        doc_number = Paragraph(
            f"<b>{self._('Quote_Number')} {self.document.numero_devis}</b>",
            self.styles["DocTitle"],
        )
        date_text = Paragraph(
            f"{self._('Quote_Date')} {self.document.date_devis.strftime('%d/%m/%Y')}",
            self.styles["DocDate"],
        )

        # Stack title and date in a single cell
        title_date_table = Table([[doc_number], [date_text]], colWidths=[9 * cm])
        title_date_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        if logo_img:
            header_data = [[logo_img, title_date_table]]
            header_table = Table(header_data, colWidths=[9 * cm, 9 * cm])
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                )
            )
        else:
            header_data = [["", title_date_table]]
            header_table = Table(header_data, colWidths=[9 * cm, 9 * cm])
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                )
            )

        elements.append(header_table)
        elements.append(Spacer(1, 0.5 * cm))

        # ===== COMPANY / CLIENT INFO GRID =====
        # Two columns: DEVIS ÉMIS PAR (left) | DESTINATAIRE (right)

        # Left column - Company info
        left_header = Paragraph(
            f"<b>{self._('Quote_Issued_By')}</b>", self.styles["SectionHeader"]
        )

        company_lines = []
        # Raison sociale
        raison = self.company.raison_sociale if self.company.raison_sociale else "-"
        company_lines.append(Paragraph(f"<b>{raison}</b>", self.styles["CustomNormal"]))
        # ICE
        ice = self.company.ICE if self.company.ICE else "-"
        company_lines.append(
            Paragraph(f"{self._('ICE')}: {ice}", self.styles["CustomSmall"])
        )
        # Adresse
        adresse = self.company.adresse if self.company.adresse else "-"
        company_lines.append(
            Paragraph(f"{self._('Address')}: {adresse}", self.styles["CustomSmall"])
        )

        # RC, IF, CNSS on one line - always show with - if empty
        rc = (
            self.company.registre_de_commerce
            if self.company.registre_de_commerce
            else "-"
        )
        if_val = (
            self.company.identifiant_fiscal if self.company.identifiant_fiscal else "-"
        )
        cnss = self.company.CNSS if self.company.CNSS else "-"
        company_lines.append(
            Paragraph(
                f"{self._('RC')}: {rc} - {self._('IF')}: {if_val} - "
                f"{self._('CNSS')}: {cnss}",
                self.styles["CustomSmall"],
            )
        )

        # RIB Compte on separate line
        rib = self.company.numero_du_compte if self.company.numero_du_compte else "-"
        company_lines.append(
            Paragraph(f"{self._('RIB_Account')}: {rib}", self.styles["CustomSmall"])
        )

        # Right column - Client info
        right_header = Paragraph(
            f"<b>{self._('Recipient')}</b>", self.styles["SectionHeader"]
        )

        client = self.document.client
        client_lines = []

        # Client name based on type
        if client.client_type == "PM" and client.raison_sociale:
            client_lines.append(
                Paragraph(
                    f"<b>{client.raison_sociale}</b>", self.styles["CustomNormal"]
                )
            )
        else:
            name = f"{client.prenom or ''} {client.nom or ''}".strip()
            client_lines.append(
                Paragraph(
                    f"<b>{name if name else '-'}</b>", self.styles["CustomNormal"]
                )
            )

        # ICE
        client_ice = client.ICE if client.ICE else "-"
        client_lines.append(
            Paragraph(f"{self._('ICE')}: {client_ice}", self.styles["CustomSmall"])
        )
        # Adresse
        client_adresse = client.adresse if client.adresse else "-"
        client_lines.append(
            Paragraph(
                f"{self._('Address')}: {client_adresse}", self.styles["CustomSmall"]
            )
        )
        # Téléphone
        client_tel = client.tel if client.tel else "-"
        client_lines.append(
            Paragraph(
                f"{self._('Phone')}: {client_tel}", self.styles["CustomSmall"]
            )
        )

        # Build left column content
        left_content = [
            [left_header],
            [HRFlowable(width="100%", thickness=1, color=self.primary_color)],
        ]
        for line in company_lines:
            left_content.append([line])

        left_table = Table(left_content, colWidths=[8.5 * cm])
        left_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        # Build right column content
        right_content = [
            [right_header],
            [HRFlowable(width="100%", thickness=1, color=self.primary_color)],
        ]
        for line in client_lines:
            right_content.append([line])

        right_table = Table(right_content, colWidths=[8.5 * cm])
        right_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        # Main grid with both columns
        main_grid = Table([[left_table, right_table]], colWidths=[9 * cm, 9 * cm])
        main_grid.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )

        elements.append(main_grid)
        elements.append(Spacer(1, 0.7 * cm))

        # ===== ARTICLES TABLE =====
        show_remise = self.pdf_type != "sans_remise"
        show_unite = self.pdf_type == "avec_unite"

        articles_table = self._create_articles_table(
            show_remise=show_remise, show_unite=show_unite
        )
        elements.append(articles_table)
        elements.append(Spacer(1, 0.3 * cm))

        # ===== TAIL: totals + price-in-words + remarks (kept together) =====
        tail_elements = []

        # Totals table
        tail_elements.append(self._create_totals_table(show_remise=show_remise))
        tail_elements.append(Spacer(1, 0.3 * cm))

        # Price in words
        tail_elements.append(
            Paragraph(
                f"<b>{self._('Quote_Amount_Words')}</b>",
                self.styles["SectionHeader"],
            )
        )
        tail_elements.append(HRFlowable(width="100%", thickness=1, color=self.primary_color))
        tail_elements.append(Spacer(1, 0.2 * cm))

        total_price = (
            self.document.total_ttc_apres_remise
            if self.document.remise_type
            else self.document.total_ttc
        )
        price_in_words = (
            number_to_english_words(total_price)
            if self.language == "en"
            else number_to_french_words(total_price)
        )
        tail_elements.append(Paragraph(f"{price_in_words} TTC", self.styles["PriceWords"]))
        tail_elements.append(Spacer(1, 0.5 * cm))

        # Remarks
        tail_elements.append(
            Paragraph(f"<b>{self._('Remarks')} :</b>", self.styles["SectionHeader"])
        )
        remarks_text = self._("Quote_Default_Remarks")
        if self.document.remarque:
            remarks_text = self.document.remarque + "\n\n" + remarks_text
        tail_elements.append(
            Paragraph(remarks_text.replace("\n", "<br/>"), self.styles["Remarks"])
        )

        elements.append(KeepTogether(tail_elements))

        return elements

    def _create_articles_table(
        self, show_remise: bool = True, show_unite: bool = False
    ) -> Table:
        """Create articles table with lines from document."""
        # Define columns based on options
        if show_remise and show_unite:
            headers = [
                self._("Designation"),
                self._("Quantity"),
                self._("TVA"),
                self._("Unit_Price_HT"),
                self._("Unit"),
                self._("Discount"),
                self._("Total_HT"),
            ]
            col_widths = [
                5.5 * cm,
                1.5 * cm,
                1.3 * cm,
                2.5 * cm,
                2 * cm,
                2.2 * cm,
                3 * cm,
            ]
        elif show_remise:
            headers = [
                self._("Designation"),
                self._("Quantity"),
                self._("TVA"),
                self._("Unit_Price_HT"),
                self._("Discount"),
                self._("Total_HT"),
            ]
            col_widths = [6.5 * cm, 1.8 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm, 3.2 * cm]
        elif show_unite:
            headers = [
                self._("Designation"),
                self._("Quantity"),
                self._("TVA"),
                self._("Unit_Price_HT"),
                self._("Unit"),
                self._("Total_HT"),
            ]
            col_widths = [6.5 * cm, 1.8 * cm, 1.5 * cm, 2.7 * cm, 2 * cm, 3.5 * cm]
        else:
            headers = [
                self._("Designation"),
                self._("Quantity"),
                self._("TVA"),
                self._("Unit_Price_HT"),
                self._("Total_HT"),
            ]
            col_widths = [7.5 * cm, 2 * cm, 1.8 * cm, 3 * cm, 3.7 * cm]

        # Create header row - Designation left, others centered
        header_cells = [Paragraph(f"<b>{headers[0]}</b>", self.styles["CustomSmall"])]
        for h in headers[1:]:
            header_cells.append(
                Paragraph(f"<b>{h}</b>", self.styles["CustomSmallCenter"])
            )
        table_data = [header_cells]

        # Add article lines
        for line in self.document.lignes.all():
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
                Paragraph(format_number_for_pdf(line.quantity), self.styles["CustomSmallCenter"])
            )

            # TVA % - centered
            tva_pct = line.article.tva if line.article.tva else Decimal("0")
            row.append(Paragraph(f"{tva_pct:.0f}%", self.styles["CustomSmallCenter"]))

            # Prix unitaire HT - centered
            devise = self.document.devise or "MAD"
            row.append(
                Paragraph(f"{format_number_for_pdf(line.prix_vente)} {devise}", self.styles["CustomSmallCenter"])
            )

            # Unite (if showing) - centered
            if show_unite:
                unite_name = line.article.unite.nom if line.article.unite else "-"
                row.append(Paragraph(unite_name, self.styles["CustomSmallCenter"]))

            # Remise per article (if showing) - centered
            if show_remise:
                if line.remise_type == "Pourcentage" and line.remise:
                    remise_text = f"{format_number_for_pdf(line.remise)}%"
                elif line.remise_type == "Fixe" and line.remise:
                    remise_text = format_number_for_pdf(line.remise)
                else:
                    remise_text = "-"
                row.append(Paragraph(remise_text, self.styles["CustomSmallCenter"]))

            # Total HT - centered
            total_ht = line.prix_vente * line.quantity
            if line.remise_type == "Pourcentage" and line.remise:
                total_ht -= total_ht * line.remise / Decimal("100")
            elif line.remise_type == "Fixe" and line.remise:
                total_ht -= line.remise
            row.append(Paragraph(f"{format_number_for_pdf(total_ht)} {devise}", self.styles["CustomSmallCenter"]))

            table_data.append(row)

        # Create table (articles only - no totals)
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        num_articles = self.document.lignes.count()
        last_article_row = num_articles

        style_commands = [
            # Header styling - soft light gray background
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
            ("ALIGN", (1, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Body styling (articles)
            ("VALIGN", (0, 1), (-1, last_article_row), "TOP"),
            ("ALIGN", (1, 1), (-1, last_article_row), "CENTER"),
            ("ALIGN", (0, 1), (0, last_article_row), "LEFT"),
            ("FONTSIZE", (0, 1), (-1, last_article_row), 8),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, last_article_row),
                [colors.white, colors.HexColor("#fafafa")],
            ),
            ("GRID", (0, 0), (-1, last_article_row), 0.5, colors.HexColor("#e0e0e0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ]

        table.setStyle(TableStyle(style_commands))

        return table

    def _get_filename(self) -> str:
        """Get PDF filename for devis."""
        doc_type = self._("quote")
        return f"{doc_type}_{self.document.numero_devis.replace('/', '_')}.pdf"

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
