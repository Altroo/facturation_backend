from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, Table, TableStyle
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, number_to_french_words
from facturation_backend.utils import CustomPagination
from facture_client.models import FactureClient
from .filters import ReglementFilter
from .models import Reglement
from .serializers import (
    ReglementCreateSerializer,
    ReglementDetailSerializer,
    ReglementListSerializer,
    ReglementUpdateSerializer,
)


class ReglementListCreateView(APIView):
    """
    GET: List règlements with pagination and aggregated stats.
    POST: Create a new règlement.

    Extra fields returned with pagination:
    - chiffre_affaire_total: Total TTC après remise of all factures for the company
    - total_reglements: Sum of all valid règlements for the company
    - total_impayes: chiffre_affaire_total - total_reglements
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _check_company_access(request, company_id: int) -> None:
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")

        if not company_id_str:
            raise Http404(_("company_id est requis."))

        company_id = int(company_id_str)
        self._check_company_access(request, company_id)

        # Get règlements for factures belonging to this company
        base_queryset = Reglement.objects.filter(
            facture_client__client__company_id=company_id
        ).select_related(
            "facture_client",
            "facture_client__client",
            "mode_reglement",
        )

        filterset = ReglementFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")

        # Calculate aggregated stats for the company
        # Chiffre d'affaire total = sum of all factures' total_ttc_apres_remise
        factures = FactureClient.objects.filter(client__company_id=company_id)
        chiffre_affaire_total = factures.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")

        # Total des règlements = sum of all valid règlements
        total_reglements = Reglement.objects.filter(
            facture_client__client__company_id=company_id, statut="Valide"
        ).aggregate(total=Sum("montant"))["total"] or Decimal("0.00")

        # Total des impayés = CA - règlements
        total_impayes = chiffre_affaire_total - total_reglements

        extra_stats = {
            "chiffre_affaire_total": str(chiffre_affaire_total),
            "total_reglements": str(total_reglements),
            "total_impayes": str(total_impayes),
        }

        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = ReglementListSerializer(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)
            response.data.update(extra_stats)
            return response

        serializer = ReglementListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(
            {
                "results": serializer.data,
                **extra_stats,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def post(request, *args, **kwargs):
        facture_client_id = request.data.get("facture_client")

        if not facture_client_id:
            raise PermissionDenied(
                _("Une facture client doit être spécifiée pour le règlement.")
            )

        try:
            facture_client = FactureClient.objects.get(pk=facture_client_id)
        except FactureClient.DoesNotExist:
            raise Http404(_("Facture client introuvable."))

        if not Membership.objects.filter(
            user=request.user, company_id=facture_client.client.company_id
        ).exists():
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer un règlement pour cette société.")
            )

        serializer = ReglementCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()

        response_serializer = ReglementDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ReglementDetailEditDeleteView(APIView):
    """
    GET: Retrieve a règlement with invoice-specific financial info.
    PUT: Update a règlement.
    DELETE: Delete a règlement.

    Extra fields returned:
    - montant_facture: Total TTC après remise of the associated invoice
    - total_reglements_facture: Sum of all valid règlements for the invoice
    - reste_a_payer: montant_facture - total_reglements_facture
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Reglement.objects.select_related(
                "facture_client",
                "facture_client__client",
                "mode_reglement",
            ).get(pk=pk)
        except Reglement.DoesNotExist:
            raise Http404(_("Aucun règlement ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à consulter ce règlement.")
            )

        serializer = ReglementDetailSerializer(reglement, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce règlement.")
            )

        serializer = ReglementUpdateSerializer(
            reglement, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à supprimer ce règlement.")
            )

        reglement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReglementStatusUpdateView(APIView):
    """
    PATCH: Update the status of a règlement (Valide/Annulé).
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Reglement.objects.select_related(
                "facture_client",
                "facture_client__client",
            ).get(pk=pk)
        except Reglement.DoesNotExist:
            raise Http404(_("Aucun règlement ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        reglement = self.get_object(pk)

        if not self._has_membership(
            request.user, reglement.facture_client.client.company_id
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce règlement.")
            )

        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in Reglement.STATUT_CHOICES]

        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})

        # If changing from Annulé to Valide, validate that the montant
        # doesn't exceed the remaining amount and facture status is valid
        if reglement.statut == "Annulé" and new_status == "Valide":
            # Check facture status
            allowed_statuses = ["Envoyé", "Accepté"]
            if reglement.facture_client.statut not in allowed_statuses:
                raise ValidationError(
                    {
                        "statut": f"Impossible de valider un règlement pour une facture "
                        f"avec le statut '{reglement.facture_client.statut}'. "
                        f"Statuts autorisés: {', '.join(allowed_statuses)}."
                    }
                )

            reste_a_payer = Reglement.get_reste_a_payer(
                reglement.facture_client, exclude_reglement_id=reglement.id
            )
            if reglement.montant > reste_a_payer:
                raise ValidationError(
                    {
                        "statut": f"Impossible de valider ce règlement. "
                        f"Le montant ({reglement.montant} MAD) dépasse "
                        f"le reste à payer ({reste_a_payer} MAD)."
                    }
                )

        reglement.statut = new_status
        reglement.save()

        return Response({"statut": reglement.statut}, status=status.HTTP_200_OK)


class ReglementPDFGenerator(BasePDFGenerator):
    """PDF generator for Reglement (payment receipt) documents."""

    def _build_single_receipt(self) -> list:
        """Build content for a single receipt."""
        elements = []

        # ===== HEADER SECTION =====
        # Logo on the left, styled title box on the right
        logo_img = self._get_logo_image()

        # Styled title box: light gray background, thin border, one line title
        title_style = ParagraphStyle(
            name="TitleBox",
            parent=self.styles["Normal"],
            fontSize=12,
            fontName="Helvetica-Bold",
            textColor=colors.black,
            alignment=TA_CENTER,  # type: ignore[arg-type]
        )
        title_para = Paragraph("REÇU DE RÈGLEMENT", title_style)
        title_box = Table([[title_para]], colWidths=[5.5 * cm])
        title_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ]
            )
        )

        if logo_img:
            header_data = [[logo_img, title_box]]
            header_table = Table(header_data, colWidths=[12 * cm, 6 * cm])
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                )
            )
        else:
            header_data = [["", title_box]]
            header_table = Table(header_data, colWidths=[12 * cm, 6 * cm])
            header_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                )
            )

        elements.append(header_table)
        elements.append(Spacer(1, 0.5 * cm))

        # ===== INFO FIELDS SECTION =====
        # Date
        date_text = self.document.date_reglement.strftime("%d/%m/%Y")

        # Client name
        client = self.document.facture_client.client
        if client.client_type == "PM" and client.raison_sociale:
            client_name = client.raison_sociale
        else:
            client_name = f"{client.prenom or ''} {client.nom or ''}".strip()
            if not client_name:
                client_name = "Client"

        # Facture reference
        facture_ref = self.document.facture_client.numero_facture

        # Amount and price in words
        amount = self.document.montant
        price_in_words = number_to_french_words(amount)

        # Create info table
        info_data = [
            [
                Paragraph("<b>Date :</b>", self.styles["CustomNormal"]),
                Paragraph(date_text, self.styles["CustomNormal"]),
            ],
            [
                Paragraph("<b>Reçu de :</b>", self.styles["CustomNormal"]),
                Paragraph(client_name, self.styles["CustomNormal"]),
            ],
            [
                Paragraph("<b>Pour :</b>", self.styles["CustomNormal"]),
                Paragraph(
                    f"Règlement de la facture N° {facture_ref}",
                    self.styles["CustomNormal"],
                ),
            ],
            [
                Paragraph("<b>La somme de :</b>", self.styles["CustomNormal"]),
                Paragraph(f"{amount:.2f} MAD", self.styles["CustomNormal"]),
            ],
        ]

        # Mode de règlement
        if self.document.mode_reglement:
            info_data.append(
                [
                    Paragraph(
                        "<b>Mode de règlement :</b>", self.styles["CustomNormal"]
                    ),
                    Paragraph(
                        self.document.mode_reglement.nom, self.styles["CustomNormal"]
                    ),
                ]
            )

        info_table = Table(info_data, colWidths=[5 * cm, 13 * cm])
        info_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        elements.append(info_table)
        elements.append(Spacer(1, 0.3 * cm))

        # ===== PRICE IN WORDS SECTION =====
        price_box_data = [
            [
                Paragraph(
                    f"<b>Soit :</b> {price_in_words}",
                    self.styles["PriceWords"],
                )
            ]
        ]
        price_box = Table(price_box_data, colWidths=[18 * cm])
        price_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
                ]
            )
        )

        elements.append(price_box)
        elements.append(Spacer(1, 0.3 * cm))

        # Libellé
        if self.document.libelle:
            elements.append(Paragraph("<b>Libellé :</b>", self.styles["CustomNormal"]))
            elements.append(
                Paragraph(self.document.libelle, self.styles["CustomSmall"])
            )
            elements.append(Spacer(1, 0.3 * cm))

        # ===== SIGNATURE AND CACHET SECTION =====
        elements.append(Spacer(1, 0.5 * cm))

        cachet_img = self._get_cachet_image()
        if cachet_img:
            signature_data = [
                [
                    "",
                    Paragraph("<b>Signature et cachet</b>", self.styles["CustomRight"]),
                ],
                ["", cachet_img],
            ]
            signature_table = Table(signature_data, colWidths=[11 * cm, 5.5 * cm])
            signature_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            elements.append(signature_table)
        else:
            # Just show signature label if no cachet
            signature_data = [
                [
                    "",
                    Paragraph("<b>Signature et cachet</b>", self.styles["CustomRight"]),
                ],
                ["", Spacer(1, 2 * cm)],
            ]
            signature_table = Table(signature_data, colWidths=[11 * cm, 5.5 * cm])
            signature_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("BOX", (1, 1), (1, 1), 0.5, colors.HexColor("#cccccc")),
                    ]
                )
            )
            elements.append(signature_table)

        return elements

    def _build_content(self) -> list:
        """Build PDF content with two copies of the receipt - each on its own page."""
        from reportlab.platypus import PageBreak
        from reportlab.platypus.flowables import HRFlowable

        elements = []

        # First copy
        receipt_elements_1 = self._build_single_receipt()
        elements.extend(receipt_elements_1)

        # Dotted line separator then page break
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(
            HRFlowable(
                width="100%", thickness=1, color=colors.HexColor("#999999"), dash=[4, 4]
            )
        )
        elements.append(PageBreak())

        # Second copy on new page
        receipt_elements_2 = self._build_single_receipt()
        elements.extend(receipt_elements_2)

        return elements

    def _get_filename(self) -> str:
        """Get PDF filename for reglement receipt."""
        return f"recu_reglement_{self.document.id}.pdf"

    def _get_pdf_title(self) -> str:
        """Get PDF document title for metadata."""
        client_name = self.document.facture_client.client.raison_sociale if self.document.facture_client.client.raison_sociale else "Client"
        facture_numero = self.document.facture_client.numero_facture
        return f"Reçu de Règlement - Facture {facture_numero} - {client_name}"


class ReglementPDFView(APIView):
    """Generate PDF receipt for Reglement."""

    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk, *args, **kwargs):
        """Generate and return PDF receipt for the reglement."""
        company_id = request.query_params.get("company_id")

        if not company_id:
            return Response(
                {"error": "company_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        reglement = get_object_or_404(Reglement, pk=pk)

        # Generate PDF
        pdf_generator = ReglementPDFGenerator(reglement, company, "normal")
        return pdf_generator.generate_pdf()
