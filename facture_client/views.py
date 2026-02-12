from decimal import Decimal

from django.db.models import Q, F, Sum as DjangoSum, Value
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from bon_de_livraison.utils import get_next_numero_bon_livraison
from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, number_to_french_words, format_number_for_pdf
from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseConversionView,
)
from facturation_backend.utils import CustomPagination
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
        base_queryset = self.model.objects.filter(
            client__company_id=company_id
        ).select_related(
            *self.list_select_related
        ).prefetch_related(
            *self.list_prefetch_related
        )
        filterset = self.filter_class(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        # Calculate aggregated stats per currency for the company
        factures = FactureClient.objects.filter(client__company_id=company_id)

        # Get company to check uses_foreign_currency flag
        company = Company.objects.get(id=company_id)

        # Group by currency
        stats_by_currency = {}
        if company.uses_foreign_currency:
            # Send stats for all currencies if company uses foreign currency
            for devise in ["MAD", "EUR", "USD"]:
                factures_devise = factures.filter(devise=devise)
                chiffre_affaire = factures_devise.aggregate(
                    total=Sum("total_ttc_apres_remise")
                )["total"] or Decimal("0.00")

                reglements = Reglement.objects.filter(
                    facture_client__client__company_id=company_id,
                    facture_client__devise=devise,
                    statut="Valide",
                ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

                impayes = chiffre_affaire - reglements

                stats_by_currency[devise] = {
                    "chiffre_affaire_total": str(chiffre_affaire),
                    "total_reglements": str(reglements),
                    "total_impayes": str(impayes),
                }
        else:
            # Only send MAD stats if company doesn't use foreign currency
            chiffre_affaire = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
                "total"
            ] or Decimal("0.00")

            reglements = Reglement.objects.filter(
                facture_client__client__company_id=company_id, statut="Valide"
            ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

            impayes = chiffre_affaire - reglements

            stats_by_currency["MAD"] = {
                "chiffre_affaire_total": str(chiffre_affaire),
                "total_reglements": str(reglements),
                "total_impayes": str(impayes),
            }
            # Initialize EUR and USD to zeros for consistency
            stats_by_currency["EUR"] = {
                "chiffre_affaire_total": "0.00",
                "total_reglements": "0.00",
                "total_impayes": "0.00",
            }
            stats_by_currency["USD"] = {
                "chiffre_affaire_total": "0.00",
                "total_reglements": "0.00",
                "total_impayes": "0.00",
            }

        extra_stats = {
            "stats_by_currency": stats_by_currency,
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
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)

        # Get all factures for the company
        base_queryset = self.model.objects.filter(client__company_id=company_id)

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

        # Calculate aggregated stats for the company (same as main list)
        factures = FactureClient.objects.filter(client__company_id=company_id)
        chiffre_affaire_total = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")

        total_reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

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

        company_id = int(company_id_str)

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

        # ===== HEADER SECTION =====
        logo_img = self._get_logo_image()

        # Document number and date together (line 1 and line 2, no space)
        doc_number = Paragraph(
            f"<b>{self._('Invoice_Number')} {self.document.numero_facture}</b>",
            self.styles["DocTitle"],
        )
        date_text = Paragraph(
            f"{self._('Invoice_Date')} {self.document.date_facture.strftime('%d/%m/%Y')}",
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
            f"<b>{self._('Invoice_Issued_By')}</b>", self.styles["SectionHeader"]
        )

        company_lines = []
        # Always show fields with - if empty
        raison = self.company.raison_sociale if self.company.raison_sociale else "-"
        company_lines.append(Paragraph(f"<b>{raison}</b>", self.styles["CustomNormal"]))
        ice = self.company.ICE if self.company.ICE else "-"
        company_lines.append(
            Paragraph(f"{self._('ICE')}: {ice}", self.styles["CustomSmall"])
        )
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

        client_ice = client.ICE if client.ICE else "-"
        client_lines.append(
            Paragraph(f"{self._('ICE')}: {client_ice}", self.styles["CustomSmall"])
        )
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
        show_remise = self.pdf_type != "sans_remise"
        show_unite = self.pdf_type == "avec_unite"

        articles_table = self._create_articles_table(
            show_remise=show_remise, show_unite=show_unite
        )
        elements.append(articles_table)
        elements.append(Spacer(1, 0.5 * cm))

        # ===== PRICE IN WORDS SECTION =====
        elements.append(
            Paragraph(
                f"<b>{self._('Invoice_Amount_Words')}</b>",
                self.styles["SectionHeader"],
            )
        )
        elements.append(HRFlowable(width="100%", thickness=1, color=self.primary_color))
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
        elements.append(Paragraph(f"{price_in_words} TTC", self.styles["PriceWords"]))
        elements.append(Spacer(1, 0.5 * cm))

        # ===== REMARKS SECTION =====
        elements.append(
            Paragraph(f"<b>{self._('Remarks')} :</b>", self.styles["SectionHeader"])
        )
        remarks_text = self._("Invoice_Default_Remarks")
        if self.document.remarque:
            remarks_text = self.document.remarque + "\n\n" + remarks_text
        elements.append(
            Paragraph(remarks_text.replace("\n", "<br/>"), self.styles["Remarks"])
        )

        return elements

    def _create_articles_table(
        self, show_remise: bool = True, show_unite: bool = False
    ) -> Table:
        """Create articles table with lines from document."""
        # Define columns based on options
        if show_remise and show_unite:
            headers = [
                "Désignation",
                "Qté",
                "TVA",
                "PRIX UNIT. HT",
                "Unité",
                "Remise",
                "Total HT",
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
                "Désignation",
                "Qté",
                "TVA",
                "PRIX UNIT. HT",
                "Remise",
                "Total HT",
            ]
            col_widths = [6.5 * cm, 1.8 * cm, 1.5 * cm, 2.5 * cm, 2.5 * cm, 3.2 * cm]
        elif show_unite:
            headers = [
                "Désignation",
                "Qté",
                "TVA",
                "PRIX UNIT. HT",
                "Unité",
                "Total HT",
            ]
            col_widths = [6.5 * cm, 1.8 * cm, 1.5 * cm, 2.7 * cm, 2 * cm, 3.5 * cm]
        else:
            headers = ["Désignation", "Qté", "TVA", "PRIX UNIT. HT", "Total HT"]
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
            row.append(
                Paragraph(format_number_for_pdf(line.prix_vente), self.styles["CustomSmallCenter"])
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
            row.append(Paragraph(format_number_for_pdf(total_ht), self.styles["CustomSmallCenter"]))

            table_data.append(row)

        # Add empty row for spacing before totals
        num_cols = len(headers)
        empty_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        table_data.append(empty_row)

        # Add totals rows - NO MAD text
        total_ht_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        total_ht_row[-2] = Paragraph("<b>Total HT</b>", self.styles["CustomSmall"])
        total_ht_row[-1] = Paragraph(
            format_number_for_pdf(self.document.total_ht), self.styles["CustomSmallCenter"]
        )
        table_data.append(total_ht_row)

        tva_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        tva_row[-2] = Paragraph("<b>TVA</b>", self.styles["CustomSmall"])
        tva_row[-1] = Paragraph(
            format_number_for_pdf(self.document.total_tva), self.styles["CustomSmallCenter"]
        )
        table_data.append(tva_row)

        total_ttc_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
        total_ttc_row[-2] = Paragraph("<b>Total TTC</b>", self.styles["CustomSmall"])
        total_ttc_row[-1] = Paragraph(
            format_number_for_pdf(self.document.total_ttc), self.styles["CustomSmallCenter"]
        )
        table_data.append(total_ttc_row)

        # Remise globale and Total TTC après remise (if applicable)
        if self.document.remise_type and self.document.remise > 0:
            remise_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
            if self.document.remise_type == "Pourcentage":
                remise_text = f"{format_number_for_pdf(self.document.remise)}%"
            else:
                remise_text = format_number_for_pdf(self.document.remise)
            remise_row[-2] = Paragraph(
                f"<b>Remise ({self.document.remise_type})</b>",
                self.styles["CustomSmall"],
            )
            remise_row[-1] = Paragraph(remise_text, self.styles["CustomSmallCenter"])
            table_data.append(remise_row)

            final_row = [Paragraph("", self.styles["CustomSmall"])] * num_cols
            final_row[-2] = Paragraph(
                "<b>Total TTC après remise</b>", self.styles["CustomSmall"]
            )
            final_row[-1] = Paragraph(
                format_number_for_pdf(self.document.total_ttc_apres_remise),
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
            # Body styling - center align numeric columns
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
        """Get PDF filename for facture client."""
        doc_type = self._("invoice")
        return f"{doc_type}_{self.document.numero_facture.replace('/', '_')}.pdf"

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
        facture_client = get_object_or_404(FactureClient, pk=pk)

        # Check if user has print permission
        if not can_print(request.user, int(company_id)):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )

        # Generate PDF
        pdf_generator = FactureClientPDFGenerator(
            facture_client, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()
