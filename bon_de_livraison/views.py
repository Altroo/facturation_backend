from decimal import Decimal

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, number_to_french_words
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
                Paragraph(f"{line.quantity:.2f}", self.styles["CustomSmallCenter"])
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

        # ===== HEADER SECTION =====
        # Logo on the left, Document title + date on the right (no space between)
        logo_img = self._get_logo_image()

        # Document number and date together (line 1 and line 2, no space)
        doc_number = Paragraph(
            f"<b>{self._('Delivery_Number')} {self.document.numero_bon_livraison}</b>",
            self.styles["DocTitle"],
        )
        date_text = Paragraph(
            f"{self._('Delivery_Date')} {self.document.date_bon_livraison.strftime('%d/%m/%Y')}",
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
        left_header = Paragraph(
            f"<b>{self._('Delivery_Issued_By')}</b>", self.styles["SectionHeader"]
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

        # Livré par
        if self.document.livre_par:
            company_lines.append(
                Paragraph(
                    f"{self._('Delivered_By')}: {self.document.livre_par.nom}",
                    self.styles["CustomSmall"],
                )
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

        main_grid = Table([[left_table, right_table]], colWidths=[9 * cm, 9 * cm])
        main_grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        elements.append(main_grid)
        elements.append(Spacer(1, 0.7 * cm))

        # ===== ARTICLES TABLE =====
        if self.pdf_type == "quantity_only":
            articles_table = self._create_articles_table_quantity_only()
            elements.append(articles_table)
            elements.append(Spacer(1, 0.5 * cm))
        else:
            show_remise = self.pdf_type == "avec_remise"
            show_unite = self.pdf_type == "avec_unite"

            articles_table = self._create_articles_table(
                show_remise=show_remise, show_unite=show_unite
            )
            elements.append(articles_table)
            elements.append(Spacer(1, 0.5 * cm))

            # ===== PRICE IN WORDS SECTION =====
            elements.append(
                Paragraph(
                    f"<b>{self._('Delivery_Amount_Words')}</b>",
                    self.styles["SectionHeader"],
                )
            )
            elements.append(
                HRFlowable(width="100%", thickness=1, color=self.primary_color)
            )
            elements.append(Spacer(1, 0.2 * cm))

            total_price = (
                self.document.total_ttc_apres_remise
                if self.document.remise_type
                else self.document.total_ttc
            )
            from core.pdf_utils import number_to_english_words

            # Get the currency from the document
            currency = self.document.devise

            price_in_words = (
                number_to_english_words(total_price, currency)
                if self.language == "en"
                else number_to_french_words(total_price, currency)
            )
            elements.append(
                Paragraph(f"{price_in_words} TTC", self.styles["PriceWords"])
            )
            elements.append(Spacer(1, 0.5 * cm))

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
                Paragraph(f"{line.quantity:.2f}", self.styles["CustomSmallCenter"])
            )

            # TVA % - centered
            tva_pct = line.article.tva if line.article.tva else Decimal("0")
            row.append(Paragraph(f"{tva_pct:.0f}%", self.styles["CustomSmallCenter"]))

            # Prix unitaire HT - centered
            row.append(
                Paragraph(f"{line.prix_vente:.2f}", self.styles["CustomSmallCenter"])
            )

            # Unite (if showing) - centered
            if show_unite:
                unite_name = line.article.unite.nom if line.article.unite else "-"
                row.append(Paragraph(unite_name, self.styles["CustomSmallCenter"]))

            # Remise per article (if showing) - centered
            if show_remise:
                if line.remise_type == "Pourcentage" and line.remise:
                    remise_text = f"{line.remise:.2f}%"
                elif line.remise_type == "Fixe" and line.remise:
                    remise_text = f"{line.remise:.2f}"
                else:
                    remise_text = "-"
                row.append(Paragraph(remise_text, self.styles["CustomSmallCenter"]))

            # Total HT - centered
            total_ht = line.prix_vente * line.quantity
            if line.remise_type == "Pourcentage" and line.remise:
                total_ht -= total_ht * line.remise / Decimal("100")
            elif line.remise_type == "Fixe" and line.remise:
                total_ht -= line.remise
            row.append(Paragraph(f"{total_ht:.2f}", self.styles["CustomSmallCenter"]))

            table_data.append(row)

        # Add empty row for spacing before totals
        num_cols = len(headers)
        empty_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        table_data.append(empty_row)

        # Add totals rows (aligned to right columns) - NO MAD text
        # Total HT
        total_ht_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        total_ht_row[-2] = Paragraph(
            f"<b>{self._('Total_HT_Label')}</b>", self.styles["CustomSmall"]
        )
        total_ht_row[-1] = Paragraph(
            f"{self.document.total_ht:.2f}", self.styles["CustomSmallCenter"]
        )
        table_data.append(total_ht_row)

        # TVA
        tva_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        tva_row[-2] = Paragraph(
            f"<b>{self._('Total_TVA_Label')}</b>", self.styles["CustomSmall"]
        )
        tva_row[-1] = Paragraph(
            f"{self.document.total_tva:.2f}", self.styles["CustomSmallCenter"]
        )
        table_data.append(tva_row)

        # Total TTC
        total_ttc_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        total_ttc_row[-2] = Paragraph(
            f"<b>{self._('Total_TTC_Label')}</b>", self.styles["CustomSmall"]
        )
        total_ttc_row[-1] = Paragraph(
            f"{self.document.total_ttc:.2f}", self.styles["CustomSmallCenter"]
        )
        table_data.append(total_ttc_row)

        # Remise globale and Total TTC après remise (if applicable)
        if self.document.remise_type and self.document.remise > 0:
            remise_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
            if self.document.remise_type == "Pourcentage":
                remise_text = f"{self.document.remise:.2f}%"
            else:
                remise_text = f"{self.document.remise:.2f}"
            remise_type_label = (
                self._("Percentage")
                if self.document.remise_type == "Pourcentage"
                else self._("Fixed")
            )
            remise_row[-2] = Paragraph(
                f"<b>{self._('Discount_Label')} ({remise_type_label})</b>",
                self.styles["CustomSmall"],
            )
            remise_row[-1] = Paragraph(remise_text, self.styles["CustomSmallCenter"])
            table_data.append(remise_row)

            # Total TTC après remise
            final_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
            final_row[-2] = Paragraph(
                f"<b>{self._('Total_TTC_After_Discount')}</b>",
                self.styles["CustomSmall"],
            )
            final_row[-1] = Paragraph(
                f"{self.document.total_ttc_apres_remise:.2f}",
                self.styles["CustomSmallCenter"],
            )
            table_data.append(final_row)

        # Create table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Calculate row indices for styling
        num_articles = self.document.lignes.count()
        last_article_row = num_articles
        totals_start = num_articles + 2

        style_commands = [
            # Header styling - soft light gray background
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
            (
                "ALIGN",
                (1, 0),
                (-1, 0),
                "CENTER",
            ),  # Center all headers except Designation
            ("ALIGN", (0, 0), (0, 0), "LEFT"),  # Designation header stays left
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Body styling (articles)
            ("VALIGN", (0, 1), (-1, last_article_row), "TOP"),
            # Center align all numeric columns (Qté, TVA, PRIX UNIT. HT, Unité, Remise, Total HT)
            ("ALIGN", (1, 1), (-1, last_article_row), "CENTER"),
            ("ALIGN", (0, 1), (0, last_article_row), "LEFT"),  # Designation stays left
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
            # Totals section styling
            ("ALIGN", (-2, totals_start), (-1, -1), "RIGHT"),
            ("FONTNAME", (-2, totals_start), (-1, -1), "Helvetica"),
            (
                "LINEABOVE",
                (-2, totals_start),
                (-1, totals_start),
                1,
                colors.HexColor("#333333"),
            ),
            ("BACKGROUND", (-2, -1), (-1, -1), colors.HexColor("#f5f5f5")),
        ]

        table.setStyle(TableStyle(style_commands))

        return table

    def _get_filename(self) -> str:
        """Get PDF filename for bon de livraison."""
        return f"{self._('delivery')}_{self.document.numero_bon_livraison.replace('/', '_')}.pdf"

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
                {"error": "company_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        bon_de_livraison = get_object_or_404(BonDeLivraison, pk=pk)

        # Check if user has print permission
        if not can_print(request.user, int(company_id)):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = BonDeLivraisonPDFGenerator(
            bon_de_livraison, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()
