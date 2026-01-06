from decimal import Decimal
from io import BytesIO
from typing import Optional

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)


def number_to_french_words(number: Decimal) -> str:
    """Convert a number to French words."""
    units = [
        "",
        "un",
        "deux",
        "trois",
        "quatre",
        "cinq",
        "six",
        "sept",
        "huit",
        "neuf",
        "dix",
        "onze",
        "douze",
        "treize",
        "quatorze",
        "quinze",
        "seize",
        "dix-sept",
        "dix-huit",
        "dix-neuf",
    ]
    tens = [
        "",
        "",
        "vingt",
        "trente",
        "quarante",
        "cinquante",
        "soixante",
        "soixante",
        "quatre-vingt",
        "quatre-vingt",
    ]

    def convert_below_100(n: int) -> str:
        if n < 20:
            return units[n]
        elif n < 70:
            ten, unit = divmod(n, 10)
            if unit == 1 and ten != 8:
                return f"{tens[ten]} et un"
            elif unit == 0:
                if ten == 8:
                    return "quatre-vingts"
                return tens[ten]
            else:
                return f"{tens[ten]}-{units[unit]}"
        elif n < 80:
            unit = n - 60
            if unit == 11:
                return "soixante et onze"
            return f"soixante-{units[unit]}"
        else:
            unit = n - 80
            if unit == 0:
                return "quatre-vingts"
            return f"quatre-vingt-{units[unit]}"

    def convert_below_1000(n: int) -> str:
        if n < 100:
            return convert_below_100(n)
        hundred, remainder = divmod(n, 100)
        if hundred == 1:
            if remainder == 0:
                return "cent"
            return f"cent {convert_below_100(remainder)}"
        else:
            if remainder == 0:
                return f"{units[hundred]} cents"
            return f"{units[hundred]} cent {convert_below_100(remainder)}"

    def convert_full(n: int) -> str:
        if n == 0:
            return "zéro"

        result_parts = []

        # Millions
        if n >= 1_000_000:
            millions, n = divmod(n, 1_000_000)
            if millions == 1:
                result_parts.append("un million")
            else:
                result_parts.append(f"{convert_below_1000(millions)} millions")

        # Thousands
        if n >= 1000:
            thousands, n = divmod(n, 1000)
            if thousands == 1:
                result_parts.append("mille")
            else:
                result_parts.append(f"{convert_below_1000(thousands)} mille")

        # Hundreds and below
        if n > 0:
            result_parts.append(convert_below_1000(n))

        return " ".join(result_parts)

    # Convert to integer (whole dirhams)
    int_part = int(number)
    # Get centimes
    centimes = int((number - int_part) * 100)

    result = convert_full(int_part).upper()
    if centimes > 0:
        result += f" DIRHAMS ET {convert_full(centimes).upper()} CENTIMES"
    else:
        result += " DIRHAMS"

    return result


class BasePDFGenerator:
    """Base class for generating PDF documents."""

    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = 1.5 * cm

    def __init__(self, document, company, pdf_type: str = "normal"):
        """
        Initialize PDF generator.

        Args:
            document: The document model instance (Devi, FactureClient, etc.)
            company: The Company model instance
            pdf_type: Type of PDF to generate (avec_remise, sans_remise, avec_unite, etc.)
        """
        self.total_pages = 1
        self.document = document
        self.company = company
        self.pdf_type = pdf_type
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Setup custom paragraph styles."""
        # Primary color for titles and headers
        self.primary_color = colors.HexColor("#1976d2")

        # Title style for document number
        self.styles.add(
            ParagraphStyle(
                name="DocTitle",
                parent=self.styles["Heading1"],
                fontSize=14,
                fontName="Helvetica-Bold",
                textColor=self.primary_color,
                alignment=TA_RIGHT,
            )
        )
        # Date style - primary color
        self.styles.add(
            ParagraphStyle(
                name="DocDate",
                parent=self.styles["Normal"],
                fontSize=10,
                fontName="Helvetica-Bold",
                textColor=self.primary_color,
                alignment=TA_RIGHT,
            )
        )
        # Section header style - primary color
        self.styles.add(
            ParagraphStyle(
                name="SectionHeader",
                parent=self.styles["Normal"],
                fontSize=10,
                fontName="Helvetica-Bold",
                textColor=self.primary_color,
                spaceAfter=4,
            )
        )
        # Normal text
        self.styles.add(
            ParagraphStyle(
                name="CustomNormal",
                parent=self.styles["Normal"],
                fontSize=9,
                leading=12,
            )
        )
        # Small text
        self.styles.add(
            ParagraphStyle(
                name="CustomSmall",
                parent=self.styles["Normal"],
                fontSize=8,
                leading=10,
            )
        )
        # Small text centered
        self.styles.add(
            ParagraphStyle(
                name="CustomSmallCenter",
                parent=self.styles["Normal"],
                fontSize=8,
                leading=10,
                alignment=TA_CENTER,
            )
        )
        # Right aligned
        self.styles.add(
            ParagraphStyle(
                name="CustomRight",
                parent=self.styles["Normal"],
                fontSize=9,
                alignment=TA_RIGHT,
            )
        )
        # Center aligned
        self.styles.add(
            ParagraphStyle(
                name="CustomCenter",
                parent=self.styles["Normal"],
                fontSize=9,
                alignment=TA_CENTER,
            )
        )
        # Footer style
        self.styles.add(
            ParagraphStyle(
                name="Footer",
                parent=self.styles["Normal"],
                fontSize=8,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#666666"),
            )
        )
        # Price in words style
        self.styles.add(
            ParagraphStyle(
                name="PriceWords",
                parent=self.styles["Normal"],
                fontSize=9,
                fontName="Helvetica-Bold",
                leading=12,
            )
        )
        # Remarks style
        self.styles.add(
            ParagraphStyle(
                name="Remarks",
                parent=self.styles["Normal"],
                fontSize=8,
                leading=11,
                textColor=colors.HexColor("#444444"),
            )
        )

    def _get_logo_image(
        self, width: float = 3.5 * cm, height: float = 2 * cm
    ) -> Optional[Image]:
        """Get company logo as reportlab Image."""
        if self.company.logo:
            try:
                logo_path = self.company.logo.path
                img = Image(logo_path, width=width, height=height)
                return img
            except Exception:
                return None
        return None

    def _get_cachet_image(
        self, width: float = 3 * cm, height: float = 3 * cm
    ) -> Optional[Image]:
        """Get company cachet (stamp) as reportlab Image."""
        if self.company.cachet:
            try:
                cachet_path = self.company.cachet.path
                img = Image(cachet_path, width=width, height=height)
                return img
            except Exception:
                return None
        return None

    def generate_pdf(self) -> HttpResponse:
        """Generate and return PDF as HTTP response."""

        # Create PDF document with page number tracking
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=self.MARGIN,
            leftMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=2 * cm,
        )

        # Build content
        elements = self._build_content()

        # First pass to count pages
        from io import BytesIO

        temp_buffer = BytesIO()
        temp_doc = SimpleDocTemplate(
            temp_buffer,
            pagesize=A4,
            rightMargin=self.MARGIN,
            leftMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=2 * cm,
        )

        # Count pages using a dummy build
        page_counter = [0]

        def count_pages(canvas, pdf_doc):
            page_counter[0] = canvas.getPageNumber()

        temp_doc.build(elements[:], onFirstPage=count_pages, onLaterPages=count_pages)
        self.total_pages = page_counter[0]

        # Rebuild elements for final document
        elements = self._build_content()

        # Generate PDF with page numbers
        doc.build(
            elements,
            onFirstPage=self._add_page_footer,
            onLaterPages=self._add_page_footer,
        )

        # Prepare response
        self.buffer.seek(0)
        response = HttpResponse(self.buffer, content_type="application/pdf")
        filename = self._get_filename()
        response["Content-Disposition"] = f'inline; filename="{filename}"'

        return response

    def _add_page_footer(self, canvas, doc):
        """Add footer with company info and page number at the bottom."""
        canvas.saveState()

        # Build footer text - always show all fields with - if empty
        raison = self.company.raison_sociale if self.company.raison_sociale else "-"
        tel = self.company.telephone if self.company.telephone else "-"
        site = self.company.site_web if self.company.site_web else "-"

        footer_text = f"{raison} - Tél: {tel} - Site web: {site}"

        page_num = canvas.getPageNumber()
        total = getattr(self, "total_pages", 1)
        page_text = f"Page {page_num} sur {total}"

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))

        # Draw footer text on the left side
        canvas.drawString(self.MARGIN, 1 * cm, footer_text)

        # Draw page number on the right side
        canvas.drawRightString(self.PAGE_WIDTH - self.MARGIN, 1 * cm, page_text)

        canvas.restoreState()

    def _build_content(self) -> list:
        """Build PDF content. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _build_content()")

    def _get_filename(self) -> str:
        """Get PDF filename. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _get_filename()")

    def _create_header(self, title: str) -> list:
        """Create standard header with logo and title."""

        elements = []
        logo_img = self._get_logo_image()

        doc_title = Paragraph(f"<b>{title}</b>", self.styles["DocTitle"])

        if logo_img:
            header_data = [[logo_img, doc_title]]
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
            header_data = [["", doc_title]]
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
        elements.append(Spacer(1, 0.3 * cm))
        return elements

    def _create_info_grid(self, left_data: list, right_data: list) -> Table:
        """Create a two-column info grid."""
        from reportlab.platypus.flowables import HRFlowable

        # Build left column
        left_content = [
            [Paragraph("<b>ÉMIS PAR</b>", self.styles["SectionHeader"])],
            [HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc"))],
        ]

        # Company info
        if self.company.raison_sociale:
            left_content.append(
                [
                    Paragraph(
                        f"<b>{self.company.raison_sociale}</b>",
                        self.styles["CustomNormal"],
                    )
                ]
            )
        if self.company.ICE:
            left_content.append(
                [Paragraph(f"ICE: {self.company.ICE}", self.styles["CustomSmall"])]
            )
        if self.company.adresse:
            left_content.append(
                [
                    Paragraph(
                        f"Adresse: {self.company.adresse}", self.styles["CustomSmall"]
                    )
                ]
            )

        # Administrative info
        admin_parts = []
        if self.company.registre_de_commerce:
            admin_parts.append(f"RC: {self.company.registre_de_commerce}")
        if self.company.identifiant_fiscal:
            admin_parts.append(f"IF: {self.company.identifiant_fiscal}")
        if self.company.CNSS:
            admin_parts.append(f"CNSS: {self.company.CNSS}")
        if admin_parts:
            left_content.append(
                [Paragraph(", ".join(admin_parts), self.styles["CustomSmall"])]
            )

        if self.company.numero_du_compte:
            left_content.append(
                [
                    Paragraph(
                        f"RIB: {self.company.numero_du_compte}",
                        self.styles["CustomSmall"],
                    )
                ]
            )

        # Add document-specific left data
        for label, value in left_data:
            left_content.append(
                [Paragraph(f"<b>{label}:</b> {value}", self.styles["CustomSmall"])]
            )

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

        # Build right column
        right_content = [
            [Paragraph("<b>DESTINATAIRE</b>", self.styles["SectionHeader"])],
            [HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc"))],
        ]

        # Add client info from right_data
        for label, value in right_data:
            if label == "Client":
                right_content.append(
                    [Paragraph(f"<b>{value}</b>", self.styles["CustomNormal"])]
                )
            else:
                right_content.append(
                    [Paragraph(f"<b>{label}:</b> {value}", self.styles["CustomSmall"])]
                )

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

        # Main grid
        main_grid = Table([[left_table, right_table]], colWidths=[9 * cm, 9 * cm])
        main_grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        return main_grid

    def _create_articles_table(
        self, show_remise: bool = True, show_unite: bool = False
    ) -> Table:
        """Create articles table with lines from document."""
        from decimal import Decimal

        # Define columns
        if show_unite:
            headers = [
                "Désignation",
                "Quantité",
                "TVA (%)",
                "Prix Unit. HT",
                "Unité",
                "Total HT",
            ]
            col_widths = [5.5 * cm, 1.8 * cm, 1.5 * cm, 2.5 * cm, 2 * cm, 2.7 * cm]
        else:
            headers = [
                "Désignation",
                "Quantité",
                "TVA (%)",
                "Prix Unit. HT",
                "Total HT",
            ]
            col_widths = [7 * cm, 2 * cm, 1.8 * cm, 2.7 * cm, 2.5 * cm]

        # Header row
        header_cells = [
            Paragraph(f"<b>{h}</b>", self.styles["CustomSmall"]) for h in headers
        ]
        table_data = [header_cells]

        # Article lines
        for line in self.document.lignes.all():
            row = []

            # Designation
            designation_text = line.article.designation
            if line.article.reference:
                designation_text = (
                    f"<b>{line.article.reference}</b><br/>{designation_text}"
                )
            row.append(Paragraph(designation_text, self.styles["CustomSmall"]))

            # Quantity
            row.append(Paragraph(f"{line.quantity:.2f}", self.styles["CustomSmall"]))

            # TVA %
            tva_pct = line.article.tva if line.article.tva else Decimal("0")
            row.append(Paragraph(f"{tva_pct:.0f}%", self.styles["CustomSmall"]))

            # Prix unitaire HT
            row.append(Paragraph(f"{line.prix_vente:.2f}", self.styles["CustomSmall"]))

            # Unite (if showing)
            if show_unite:
                unite_name = line.article.unite.nom if line.article.unite else ""
                row.append(Paragraph(unite_name, self.styles["CustomSmall"]))

            # Total HT
            total_ht = line.prix_vente * line.quantity
            if hasattr(line, "remise_type") and line.remise_type:
                if line.remise_type == "Pourcentage":
                    total_ht -= total_ht * line.remise / Decimal("100")
                elif line.remise_type == "Fixe":
                    total_ht -= line.remise
            row.append(Paragraph(f"{total_ht:.2f}", self.styles["CustomSmall"]))

            table_data.append(row)

        # Empty row for spacing
        num_cols = len(headers)
        table_data.append([""] * num_cols)

        # Totals rows
        total_ht_row = [""] * num_cols
        total_ht_row[-2] = Paragraph("<b>Total HT</b>", self.styles["CustomSmall"])
        total_ht_row[-1] = Paragraph(
            f"{self.document.total_ht:.2f} MAD", self.styles["CustomSmall"]
        )
        table_data.append(total_ht_row)

        tva_row = [""] * num_cols
        tva_row[-2] = Paragraph("<b>TVA</b>", self.styles["CustomSmall"])
        tva_row[-1] = Paragraph(
            f"{self.document.total_tva:.2f} MAD", self.styles["CustomSmall"]
        )
        table_data.append(tva_row)

        total_ttc_row = [""] * num_cols
        total_ttc_row[-2] = Paragraph("<b>Total TTC</b>", self.styles["CustomSmall"])
        total_ttc_row[-1] = Paragraph(
            f"{self.document.total_ttc:.2f} MAD", self.styles["CustomSmall"]
        )
        table_data.append(total_ttc_row)

        # Remise and final total
        if show_remise and self.document.remise_type and self.document.remise > 0:
            remise_row = [""] * num_cols
            if self.document.remise_type == "Pourcentage":
                remise_text = f"{self.document.remise:.2f}%"
            else:
                remise_text = f"{self.document.remise:.2f} MAD"
            remise_row[-2] = Paragraph(
                f"<b>Remise ({self.document.remise_type})</b>",
                self.styles["CustomSmall"],
            )
            remise_row[-1] = Paragraph(remise_text, self.styles["CustomSmall"])
            table_data.append(remise_row)

            final_row = [""] * num_cols
            final_row[-2] = Paragraph(
                "<b>Total TTC après remise</b>", self.styles["CustomSmall"]
            )
            final_row[-1] = Paragraph(
                f"{self.document.total_ttc_apres_remise:.2f} MAD",
                self.styles["CustomSmall"],
            )
            table_data.append(final_row)

        # Create table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Calculate styling indices
        num_articles = self.document.lignes.count()
        last_article_row = num_articles
        totals_start = num_articles + 2

        style_commands = [
            # Header styling
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a4a4a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Body styling
            ("VALIGN", (0, 1), (-1, last_article_row), "TOP"),
            ("ALIGN", (1, 1), (-1, last_article_row), "RIGHT"),
            ("ALIGN", (0, 1), (0, last_article_row), "LEFT"),
            ("FONTSIZE", (0, 1), (-1, last_article_row), 8),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, last_article_row),
                [colors.white, colors.HexColor("#f9f9f9")],
            ),
            ("GRID", (0, 0), (-1, last_article_row), 0.5, colors.HexColor("#dddddd")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            # Totals section
            ("ALIGN", (-2, totals_start), (-1, -1), "RIGHT"),
            ("FONTNAME", (-2, totals_start), (-1, -1), "Helvetica"),
            (
                "LINEABOVE",
                (-2, totals_start),
                (-1, totals_start),
                1,
                colors.HexColor("#333333"),
            ),
            ("BACKGROUND", (-2, -1), (-1, -1), colors.HexColor("#f0f0f0")),
        ]

        table.setStyle(TableStyle(style_commands))

        return table

    def _create_totals_section(self, show_remise: bool = True) -> Table:
        """Create totals section table."""
        totals_data = [
            [
                Paragraph("<b>Total HT:</b>", self.styles["CustomNormal"]),
                Paragraph(
                    f"{self.document.total_ht:.2f} MAD", self.styles["CustomRight"]
                ),
            ],
            [
                Paragraph("<b>TVA:</b>", self.styles["CustomNormal"]),
                Paragraph(
                    f"{self.document.total_tva:.2f} MAD", self.styles["CustomRight"]
                ),
            ],
            [
                Paragraph("<b>Total TTC:</b>", self.styles["CustomNormal"]),
                Paragraph(
                    f"{self.document.total_ttc:.2f} MAD", self.styles["CustomRight"]
                ),
            ],
        ]

        if show_remise and self.document.remise_type and self.document.remise > 0:
            if self.document.remise_type == "Pourcentage":
                remise_text = f"{self.document.remise:.2f}%"
            else:
                remise_text = f"{self.document.remise:.2f} MAD"
            totals_data.append(
                [
                    Paragraph(
                        f"<b>Remise ({self.document.remise_type}):</b>",
                        self.styles["CustomNormal"],
                    ),
                    Paragraph(remise_text, self.styles["CustomRight"]),
                ]
            )
            totals_data.append(
                [
                    Paragraph(
                        "<b>Total TTC après remise:</b>", self.styles["CustomNormal"]
                    ),
                    Paragraph(
                        f"{self.document.total_ttc_apres_remise:.2f} MAD",
                        self.styles["CustomRight"],
                    ),
                ]
            )

        totals_table = Table(totals_data, colWidths=[12 * cm, 6 * cm])
        totals_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEABOVE", (0, 0), (-1, 0), 1, colors.HexColor("#333333")),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#333333")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
                ]
            )
        )

        return totals_table

    def _create_price_in_words_section(
        self, price_label: str = "ARRÊTÉ À LA SOMME DE"
    ) -> list:
        """Create price in words section."""
        from reportlab.platypus.flowables import HRFlowable

        elements = [
            Paragraph(f"<b>{price_label}</b>", self.styles["SectionHeader"]),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")),
            Spacer(1, 0.2 * cm),
        ]

        total_price = (
            self.document.total_ttc_apres_remise
            if hasattr(self.document, "remise_type") and self.document.remise_type
            else self.document.total_ttc
        )
        price_in_words = number_to_french_words(total_price)
        elements.append(Paragraph(f"{price_in_words} TTC", self.styles["PriceWords"]))
        elements.append(Spacer(1, 0.5 * cm))

        return elements

    def _create_remarks_section(self, custom_remarks: str = "") -> list:
        """Create remarks section."""
        elements = [Paragraph("<b>Remarques :</b>", self.styles["SectionHeader"])]

        remarks_text = custom_remarks
        if self.document.remarque:
            if remarks_text:
                remarks_text = self.document.remarque + "\n\n" + remarks_text
            else:
                remarks_text = self.document.remarque

        if remarks_text:
            elements.append(
                Paragraph(remarks_text.replace("\n", "<br/>"), self.styles["Remarks"])
            )

        return elements
