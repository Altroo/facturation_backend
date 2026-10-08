from xml.sax.saxutils import escape

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle, KeepTogether
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import (
    BasePDFGenerator,
    format_multiline_pdf_text,
    format_number_for_pdf,
)
from core.permissions import can_delete, can_print
from core.views import (
    BaseDocumentListCreateView,
    BaseDocumentDetailEditDeleteView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseBulkDeleteView,
)
from facturation_backend.utils import CustomPagination
from stock.services import delete_deliveries_with_stock, delete_delivery_with_stock, sync_delivery_stock
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
    list_select_related = (
        "client",
        "mode_paiement",
        "created_by_user",
        "livre_par",
        "source_facture_client",
    )


class BonDeLivraisonDetailEditDeleteView(BaseDocumentDetailEditDeleteView):
    model = BonDeLivraison
    detail_serializer_class = BonDeLivraisonDetailSerializer
    document_name = "bon de livraison"
    detail_select_related = (
        "client",
        "mode_paiement",
        "created_by_user",
        "livre_par",
        "source_facture_client",
    )

    @transaction.atomic
    def put(self, request, pk, *args, **kwargs):
        delivery = get_object_or_404(self.model.objects.select_for_update(), pk=pk)
        if delivery.statut in {"Accepté", "Facturé"} and "lignes" in request.data:
            raise ValidationError(
                {
                    "lignes": _(
                        "Repassez le bon à un statut non comptabilisé avant de modifier ses lignes."
                    )
                }
            )
        return super().put(request, pk, *args, **kwargs)

    @transaction.atomic
    def delete(self, request, pk, *args, **kwargs):
        delivery = get_object_or_404(
            self.model.objects.select_for_update(of=("self",)).select_related("client"),
            pk=pk,
        )
        company_id = delivery.client.company_id
        if not self._has_membership(request.user, company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à supprimer ce bon de livraison."))
        if not can_delete(request.user, company_id):
            raise PermissionDenied(_("Vous n'avez pas les droits pour supprimer ce bon de livraison."))
        delete_delivery_with_stock(delivery, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def apply_status_change(self, request, object_, old_status, new_status):
        sync_delivery_stock(object_, old_status, new_status, request.user)


class GenerateNumeroBonDeLivraisonView(BaseGenerateNumeroView):
    numero_generator = get_next_numero_bon_livraison
    response_key = "numero_bon_livraison"


class BonDeLivraisonStatusUpdateView(BaseStatusUpdateView):
    model = BonDeLivraison
    document_name = "bon de livraison"

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        get_object_or_404(self.model.objects.select_for_update(), pk=pk)
        return super().patch(request, pk, *args, **kwargs)

    def apply_status_change(self, request, object_, old_status, new_status):
        sync_delivery_stock(object_, old_status, new_status, request.user)


class BonDeLivraisonUninvoicedListView(BaseDocumentListCreateView):
    """
    List bons de livraison that haven't been invoiced yet.
    GET only - returns BLs with statut='Brouillon' or 'Validé' (not yet converted to facture).
    """

    model = BonDeLivraison
    filter_class = BonDeLivraisonFilter
    list_serializer_class = BonDeLivraisonListSerializer
    document_name = "le bon de livraison"
    list_select_related = (
        "client",
        "mode_paiement",
        "created_by_user",
        "livre_par",
        "source_facture_client",
    )

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

    def _create_delivery_articles_table(self):
        """Delivery quantities, with space for handwritten receiving remarks."""
        headers = (
            ["Référence", "Désignation", "Quantité", "Remarque"]
            if self.language == "fr"
            else (
                ["Reference", "Description", "Quantity", "Remark"]
                if self.language == "en"
                else [
                    self._(key)
                    for key in ("Reference", "Designation", "Quantity", "Remark")
                ]
            )
        )
        styles = [
            self.styles["CustomSmall"],
            self.styles["CustomSmall"],
            self.styles["CustomSmallCenter"],
            self.styles["CustomSmall"],
        ]
        rows = [
            [
                Paragraph(f"<b>{label}</b>", style)
                for label, style in zip(headers, styles)
            ]
        ]
        for line in self.document.lignes.select_related("article").order_by(
            "article__reference", "pk"
        ):
            rows.append(
                [
                    Paragraph(escape(line.article.reference or ""), styles[0]),
                    Paragraph(
                        format_multiline_pdf_text(self._text(line.article.designation)),
                        styles[1],
                    ),
                    Paragraph(format_number_for_pdf(line.quantity), styles[2]),
                    "",
                ]
            )
        table = Table(
            rows,
            colWidths=[3 * cm, 8.8 * cm, 2 * cm, self.CONTENT_WIDTH - 13.8 * cm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return table

    def _build_delivery_signatures(self):
        company_label = f"{self._('Signature')} {self.company.raison_sociale}".strip()
        client_label = self._("Client_Signature")
        signatures = Table(
            [
                [
                    Paragraph(
                        f"<b>{escape(company_label)}</b>", self.styles["CustomNormal"]
                    ),
                    Paragraph(f"<b>{client_label}</b>", self.styles["CustomRight"]),
                ],
                ["", ""],
            ],
            colWidths=[self.HALF_WIDTH, self.HALF_WIDTH],
            rowHeights=[None, 3 * cm],
        )
        signatures.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return KeepTogether([Spacer(1, 0.8 * cm), signatures])

    def _build_content(self) -> list:
        """All delivery-note variants use the same price-free layout."""
        if self._uses_nectar_layout():
            elements = [
                *self._build_nectar_header(),
                Spacer(1, 1.5 * cm),
                self._build_nectar_client_block(),
                Spacer(1, 0.8 * cm),
                Paragraph(
                    f"{self._('Delivery')} {escape(self._nectar_display_number(self.document.numero_bon_livraison))}",
                    self.styles["NectarTitle"],
                ),
                Spacer(1, 0.35 * cm),
                Paragraph(
                    f"<b>{self._('Delivery_Date')}</b> {self.document.date_bon_livraison.strftime('%d/%m/%Y')}",
                    self.styles["CustomNormal"],
                ),
                Spacer(1, 0.8 * cm),
            ]
        else:
            extra_company_lines = None
            if self.document.livre_par:
                extra_company_lines = [
                    Paragraph(
                        f"{self._('Delivered_By')}: {escape(self.document.livre_par.nom)}",
                        self.styles["CustomSmall"],
                    )
                ]
            elements = [
                self._build_doc_header(
                    f"{self._('Delivery_Number')} {self.document.numero_bon_livraison}",
                    f"{self._('Delivery_Date')} {self.document.date_bon_livraison.strftime('%d/%m/%Y')}",
                ),
                Spacer(1, 0.5 * cm),
                self._build_parties_grid(
                    Paragraph(
                        f"<b>{self._('Delivery_Issued_By')}</b>",
                        self.styles["SectionHeader"],
                    ),
                    extra_company_lines=extra_company_lines,
                ),
                Spacer(1, 0.7 * cm),
            ]
        elements.append(self._create_delivery_articles_table())
        if self.document.remarque:
            label = self._("Remark")
            elements.extend(
                [
                    Spacer(1, 0.3 * cm),
                    Paragraph(
                        f"<b>{label} :</b> {format_multiline_pdf_text(self._text(self.document.remarque))}",
                        self.styles["CustomNormal"],
                    ),
                ]
            )
        elements.append(self._build_delivery_signatures())
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

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        ids = request.data.get("ids")
        if not ids or not isinstance(ids, list):
            raise ValidationError({"ids": _("Une liste d'identifiants est requise.")})
        try:
            ids = [int(identifier) for identifier in ids]
        except (TypeError, ValueError):
            raise ValidationError({"ids": _("Les identifiants doivent être des entiers.")})
        deliveries = list(
            self.get_queryset_with_related(ids).select_for_update(of=("self",)).order_by("pk")
        )
        if len(deliveries) != len(ids):
            raise Http404(_("Certains bons de livraison sont introuvables."))
        # Validate the whole selection before any ledger or document is changed.
        for delivery in deliveries:
            company_id = self.get_company_id(delivery)
            if not self._has_membership(request.user, company_id):
                raise PermissionDenied(_("Vous n'êtes pas autorisé à supprimer ce bon de livraison."))
            if not can_delete(request.user, company_id):
                raise PermissionDenied(_("Vous n'avez pas les droits pour supprimer ce bon de livraison."))
        self.validate_bulk_delete(deliveries)
        delete_deliveries_with_stock(deliveries, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
