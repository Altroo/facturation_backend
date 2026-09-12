from html import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from core.pdf_utils import BasePDFGenerator


def _text(value, fallback="-"):
    if value in (None, ""):
        return fallback
    return escape(str(value))


def _date(value):
    return value.strftime("%d/%m/%Y") if value else "-"


def _amount(value, currency):
    if value is None:
        return "-"
    formatted = f"{value:,.2f}".replace(",", " ")
    return f"{formatted} {_text(currency)}"


class LogisticsPaymentRequestPDFGenerator(BasePDFGenerator):
    """Internal accounting payment request generated from logistics data."""

    def _should_show_draft_watermark(self):
        return False

    def _get_filename(self):
        reference = self.document.numero_commande.replace("/", "_")
        return f"demande_paiement_{reference}.pdf"

    def _get_pdf_title(self):
        return f"Demande de paiement fournisseur {self.document.numero_commande}"

    def _section(self, title, rows):
        label_style = ParagraphStyle(
            name=f"PaymentLabel{title}",
            parent=self.styles["CustomSmall"],
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#455A64"),
        )
        value_style = ParagraphStyle(
            name=f"PaymentValue{title}",
            parent=self.styles["CustomSmall"],
            textColor=colors.HexColor("#172B4D"),
        )
        table_rows = [
            [Paragraph(_text(label), label_style), Paragraph(_text(value), value_style)]
            for label, value in rows
        ]
        table = Table(
            table_rows,
            colWidths=[5.4 * cm, self.CONTENT_WIDTH - 5.4 * cm],
            repeatRows=0,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F7FB")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6E1EE")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6E1EE")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return KeepTogether(
            [
                Paragraph(title, self.styles["SectionHeader"]),
                Spacer(1, 0.08 * cm),
                table,
            ]
        )

    def _schedule(self):
        header_style = ParagraphStyle(
            name="PaymentScheduleHeader",
            parent=self.styles["CustomSmallCenter"],
            fontName="Helvetica-Bold",
            textColor=colors.white,
        )
        cell_style = ParagraphStyle(
            name="PaymentScheduleCell",
            parent=self.styles["CustomSmallCenter"],
            textColor=colors.HexColor("#172B4D"),
        )
        rows = [
            [
                Paragraph("Échéance", header_style),
                Paragraph("Montant prévu", header_style),
                Paragraph("Statut", header_style),
            ]
        ]
        installments = list(self.document.echeances_paiement.all())
        if installments:
            for installment in installments:
                rows.append(
                    [
                        Paragraph(_date(installment.date_echeance), cell_style),
                        Paragraph(
                            _amount(installment.montant_prevu, installment.devise),
                            cell_style,
                        ),
                        Paragraph(_text(installment.statut_traitement), cell_style),
                    ]
                )
        else:
            rows.append(
                [
                    Paragraph("-", cell_style),
                    Paragraph("Aucune échéance enregistrée", cell_style),
                    Paragraph("-", cell_style),
                ]
            )
        table = Table(
            rows,
            colWidths=[4.2 * cm, 5.5 * cm, self.CONTENT_WIDTH - 9.7 * cm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.primary_color),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6E1EE")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6E1EE")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return KeepTogether(
            [
                Paragraph("Échéancier de paiement", self.styles["SectionHeader"]),
                Spacer(1, 0.08 * cm),
                table,
            ]
        )

    def _build_content(self):
        order = self.document
        responsible = order.responsable.get_full_name() if order.responsable else "-"
        responsible = responsible or (
            order.responsable.email if order.responsable else "-"
        )
        source_references = (
            ", ".join(proforma.numero_facture for proforma in order.proformas.all())
            or "-"
        )

        notice_style = ParagraphStyle(
            name="PaymentNotice",
            parent=self.styles["CustomSmall"],
            fontSize=8.5,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0D47A1"),
        )
        notice = Table(
            [
                [
                    Paragraph(
                        "<b>Document interne généré par Facturation</b><br/>"
                        "Cette fiche centralise les données validées du dossier pour "
                        "le traitement par le Service Comptable.",
                        notice_style,
                    )
                ]
            ],
            colWidths=[self.CONTENT_WIDTH],
        )
        notice.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF3FF")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#90CAF9")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        return [
            self._build_doc_header(
                "DEMANDE DE PAIEMENT FOURNISSEUR",
                f"DOSSIER {escape(order.numero_commande)} - GÉNÉRÉ LE "
                f"{timezone.localdate().strftime('%d/%m/%Y')}",
            ),
            Spacer(1, 0.35 * cm),
            notice,
            Spacer(1, 0.45 * cm),
            self._section(
                "Références du dossier",
                [
                    ("Référence dossier", order.numero_commande),
                    ("Pro forma source acceptée", source_references),
                    ("Fournisseur", order.fournisseur),
                    ("Responsable du dossier", responsible),
                    ("Date prévue", _date(order.date_prevue)),
                ],
            ),
            Spacer(1, 0.4 * cm),
            self._section(
                "Pro forma fournisseur",
                [
                    ("Numéro", order.numero_proforma_fournisseur),
                    ("Date", _date(order.date_proforma_fournisseur)),
                    (
                        "Montant",
                        _amount(
                            order.montant_proforma_fournisseur,
                            order.devise_proforma_fournisseur,
                        ),
                    ),
                    ("Incoterm", order.incoterm),
                    ("Conditions de paiement", order.conditions_paiement),
                    (
                        "Délai fournisseur",
                        (
                            f"{order.delai_proforma_jours} jours"
                            if order.delai_proforma_jours is not None
                            else "-"
                        ),
                    ),
                ],
            ),
            Spacer(1, 0.4 * cm),
            self._section(
                "Titre d'importation",
                [
                    ("Numéro de domiciliation", order.numero_domiciliation),
                    ("Banque", order.banque),
                    (
                        "Montant",
                        _amount(
                            order.montant_titre_importation,
                            order.devise_titre_importation,
                        ),
                    ),
                    ("Date", _date(order.date_titre_importation)),
                    ("Méthode de paiement", order.methode_paiement),
                ],
            ),
            Spacer(1, 0.4 * cm),
            self._schedule(),
        ]


def build_accounting_payment_pdf(order):
    generator = LogisticsPaymentRequestPDFGenerator(order, order.company)
    response = generator.generate_pdf()
    return generator._get_filename(), response.content, "application/pdf"
