from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator, format_number_for_pdf
from core.permissions import can_create, can_delete, can_update, can_print
from core.views import CompanyAccessMixin, BaseBulkDeleteView, BaseBulkArchiveView
from devi.models import Devi
from devi.serializers import DeviListSerializer
from facturation_backend.utils import CustomPagination
from facture_avoir.models import FactureAvoir
from facture_avoir.serializers import FactureAvoirListSerializer
from facture_client.models import FactureClient
from facture_client.serializers import FactureClientListSerializer
from facture_client.views import annotate_payment_and_avoir_totals
from reglement.models import Reglement
from reglement.serializers import ReglementListSerializer
from .filters import ClientFilter
from .models import Client
from .serializers import (
    ClientSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
    ClientStatementQuerySerializer,
)
from .utils import get_next_client_code


class ClientListCreateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        archived_param = request.query_params.get("archived")
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
        qs_filter = {"company_id": company_id}
        if archived_param is not None:
            qs_filter["archived"] = archived_param.lower() == "true"
        base_queryset = Client.objects.filter(**qs_filter).select_related(
            "company", "ville"
        )
        filterset = ClientFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = ClientListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ClientListSerializer(ordered_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        # the client must be created for a company the user belongs to
        company_id = request.data.get("company")
        if (
            not company_id
            or not Membership.objects.filter(
                user=request.user, company_id=company_id
            ).exists()
        ):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer un client pour cette société.")
            )

        # Check if user has created permission
        if not can_create(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer un client.")
            )

        serializer = ClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ClientDetailEditDeleteView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get_object(pk):
        try:
            return Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            raise Http404(_("Aucun client ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à consulter ce client."))
        serializer = ClientDetailSerializer(client)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à modifier ce client."))

        # Check if user has update permission
        if not can_update(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce client.")
            )

        serializer = ClientDetailSerializer(client, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à supprimer ce client."))

        # Check if user has deleted permission
        if not can_delete(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour supprimer ce client.")
            )

        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à modifier ce client."))

        # Check if user has update permission
        if not can_update(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce client.")
            )

        serializer = ClientDetailSerializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class ClientHistoryView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get_object(pk):
        try:
            return Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            raise Http404(_("Aucun client ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à consulter ce client."))
        devis = (
            Devi.objects.filter(client=client)
            .select_related("client", "mode_paiement", "created_by_user")
            .prefetch_related("lignes")
            .order_by("-date_devis", "-id")
        )
        factures = annotate_payment_and_avoir_totals(
            FactureClient.objects.filter(client=client)
            .select_related("client", "mode_paiement", "created_by_user")
            .prefetch_related("lignes")
        ).order_by("-date_facture", "-id")
        avoirs = (
            FactureAvoir.objects.filter(client=client)
            .select_related(
                "client",
                "mode_paiement",
                "created_by_user",
                "facture_origine",
            )
            .prefetch_related("lignes")
            .order_by("-date_avoir", "-id")
        )
        reglements = (
            Reglement.objects.filter(facture_client__client=client)
            .select_related(
                "facture_client",
                "facture_client__client",
                "mode_reglement",
            )
            .order_by("-date_reglement", "-id")
        )

        context = {"request": request}
        return Response(
            {
                "devis": DeviListSerializer(devis, many=True, context=context).data,
                "factures": FactureClientListSerializer(
                    factures, many=True, context=context
                ).data,
                "avoirs": FactureAvoirListSerializer(
                    avoirs, many=True, context=context
                ).data,
                "reglements": ReglementListSerializer(
                    reglements, many=True, context=context
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ClientStatementPDFGenerator(BasePDFGenerator):
    """Client account statement using the shared document PDF layout."""

    def __init__(self, client, company, language, filters):
        super().__init__(client, company, "normal", language)
        self.filters = filters
        self.client_name = (
            client.raison_sociale
            or " ".join(filter(None, [client.nom, client.prenom]))
            or client.code_client
            or "-"
        )
        self.rows = self._get_rows()

    def _get_client(self):
        return self.document

    def _setup_custom_styles(self):
        super()._setup_custom_styles()
        self.styles.add(
            ParagraphStyle(
                name="StatementAmount",
                parent=self.styles["CustomSmall"],
                alignment=TA_RIGHT,
            )
        )
        self.styles.add(
            ParagraphStyle(
                name="StatementBalance",
                parent=self.styles["StatementAmount"],
                textColor=colors.white if self._uses_nectar_layout() else colors.black,
            )
        )

    def _prepare_text_translations(self):
        # Statements contain fixed labels and original document identifiers.
        pass

    def _balance_elements(self, elements):
        # The statement is one repeating table, without an invoice totals tail.
        return elements

    def _get_rows(self):
        rows = []
        sources = [
            (
                "invoice",
                FactureClient.objects.filter(client=self.document),
                "date_facture",
            ),
            (
                "credit_note",
                FactureAvoir.objects.filter(client=self.document).select_related(
                    "facture_origine"
                ),
                "date_avoir",
            ),
            (
                "payment",
                Reglement.objects.filter(
                    facture_client__client=self.document
                ).select_related("facture_client"),
                "date_reglement",
            ),
        ]
        for order, (kind, queryset, date_field) in enumerate(sources):
            if self.filters["type"] not in ("all", kind):
                continue
            if self.filters.get("date_from"):
                queryset = queryset.filter(
                    **{f"{date_field}__gte": self.filters["date_from"]}
                )
            if self.filters.get("date_to"):
                queryset = queryset.filter(
                    **{f"{date_field}__lte": self.filters["date_to"]}
                )
            for document in queryset:
                date = getattr(document, date_field)
                debit = credit = Decimal("0")
                if kind == "invoice":
                    piece = self._("Invoice")
                    label = f"N° : {document.numero_facture}"
                    debit = document.total_ttc_apres_remise or Decimal("0")
                elif kind == "credit_note":
                    piece = self._("Credit_Note")
                    label = (
                        f"{self._('Invoice_Credit_Note')} N°({document.facture_origine.numero_facture})"
                        if document.facture_origine
                        else f"N° : {document.numero_avoir}"
                    )
                    credit = document.total_ttc_apres_remise or Decimal("0")
                else:
                    piece = self._("Payment")
                    label = f"{self._('Invoice_Payment')} N°({document.facture_client.numero_facture}) {self.client_name}"
                    credit = document.montant or Decimal("0")
                rows.append(
                    {
                        "date": date,
                        "due_date": getattr(document, "date_echeance", None) or date,
                        "piece": piece,
                        "label": label,
                        "devise": (
                            document.facture_client.devise
                            if kind == "payment"
                            else document.devise
                        )
                        or "MAD",
                        "debit": debit,
                        "credit": credit,
                        "order": order,
                    }
                )
        rows.sort(key=lambda row: (row["date"], row["order"], row["label"]))
        if self.filters.get("date_from") and self.filters["type"] == "all":
            rows.insert(
                0,
                {
                    "date": self.filters["date_from"],
                    "due_date": None,
                    "piece": "",
                    "label": "",
                    "devise": rows[0]["devise"] if rows else "MAD",
                    "debit": Decimal("0"),
                    "credit": Decimal("0"),
                    "order": -1,
                },
            )
        return rows

    def _get_filename(self):
        return f"extrait_compte_client_{self.document.pk}.pdf"

    def _get_pdf_title(self):
        return f"{self._('Statement')} - {self.client_name}"

    def _build_content(self):
        def paragraph(value, style="CustomSmall", bold=False):
            text = escape(str(value))
            return Paragraph(f"<b>{text}</b>" if bold else text, self.styles[style])

        def date_label(value):
            return value.strftime("%d/%m/%Y") if value else "-"

        totals = {}
        for row in self.rows:
            total = totals.setdefault(
                row["devise"], {"debit": Decimal("0"), "credit": Decimal("0")}
            )
            total["debit"] += row["debit"]
            total["credit"] += row["credit"]

        def amount(value, currency):
            text = format_number_for_pdf(value)
            return f"{text} {currency}" if len(totals) > 1 else text

        dated_rows = [row for row in self.rows if row["order"] >= 0]
        period_from = self.filters.get("date_from") or (
            dated_rows[0]["date"] if dated_rows else None
        )
        period_to = self.filters.get("date_to") or (
            dated_rows[-1]["date"] if dated_rows else timezone.localdate()
        )
        title = f"{self._('Statement')} {self.document.code_client or ''}".strip()
        generated_date = f"{self._('Date')} : {date_label(timezone.localdate())}"
        nectar = self._uses_nectar_layout()
        if nectar:
            elements = [
                *self._build_nectar_header(),
                Spacer(1, 1 * cm),
                self._build_nectar_client_block(),
                Spacer(1, 0.6 * cm),
                paragraph(title, "NectarTitle"),
                paragraph(generated_date, "CustomNormal"),
                Spacer(1, 0.3 * cm),
            ]
        else:
            elements = [
                self._build_doc_header(escape(title), escape(generated_date)),
                Spacer(1, 0.5 * cm),
                self._build_parties_grid(
                    paragraph(self._("Statement_Issued_By"), "SectionHeader", bold=True)
                ),
                Spacer(1, 0.5 * cm),
            ]

        period = Table(
            [
                [
                    paragraph(
                        f"{self._('Statement_Currency')} : {', '.join(totals) or '-'}"
                    ),
                    paragraph(
                        f"{self._('From')} : {date_label(period_from)} | {self._('To')} : {date_label(period_to)}",
                        "CustomRight",
                    ),
                ]
            ],
            colWidths=[self.CONTENT_WIDTH * 0.35, self.CONTENT_WIDTH * 0.65],
        )
        period.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.extend([period, Spacer(1, 0.3 * cm)])
        data = [
            [
                paragraph(self._(key), "CustomSmallCenter", bold=True)
                for key in (
                    "Date",
                    "Statement_Due_Date",
                    "Piece",
                    "Label",
                    "Debit",
                    "Credit",
                )
            ]
        ]
        for row in self.rows:
            data.append(
                [
                    paragraph(date_label(row["date"]), "CustomSmallCenter"),
                    paragraph(
                        date_label(row["due_date"]) if row["due_date"] else "",
                        "CustomSmallCenter",
                    ),
                    paragraph(row["piece"]),
                    paragraph(row["label"]),
                    paragraph(amount(row["debit"], row["devise"]), "StatementAmount"),
                    paragraph(amount(row["credit"], row["devise"]), "StatementAmount"),
                ]
            )
        if not self.rows:
            data.append(
                [
                    paragraph(self._("Statement_Empty"), "CustomSmallCenter"),
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
        last_entry = len(data) - 1
        summary_rows = []
        for currency, total in totals.items():
            total_row = len(data)
            data.append(
                [
                    paragraph(
                        f"{self._('Statement_Total')} ({currency})",
                        "StatementAmount",
                        bold=True,
                    ),
                    "",
                    "",
                    "",
                    paragraph(
                        amount(total["debit"], currency), "StatementAmount", bold=True
                    ),
                    paragraph(
                        amount(total["credit"], currency), "StatementAmount", bold=True
                    ),
                ]
            )
            data.append(
                [
                    paragraph(
                        f"{self._('Balance')} ({currency})",
                        "StatementBalance",
                        bold=True,
                    ),
                    "",
                    "",
                    "",
                    "",
                    paragraph(
                        amount(total["debit"] - total["credit"], currency),
                        "StatementBalance",
                        bold=True,
                    ),
                ]
            )
            summary_rows.append(total_row)

        table = Table(
            data,
            colWidths=[
                2 * cm,
                2 * cm,
                2.5 * cm,
                self.CONTENT_WIDTH - 11.5 * cm,
                2.5 * cm,
                2.5 * cm,
            ],
            repeatRows=1,
        )
        border = colors.HexColor("#4f5964" if nectar else "#e0e0e0")
        styles = [
            ("GRID", (0, 0), (-1, last_entry), 0.6 if nectar else 0.5, border),
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.white if nectar else colors.HexColor("#f5f5f5"),
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, last_entry),
                [colors.white, colors.HexColor("#fafafa")],
            ),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 7 if nectar else 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 7 if nectar else 5),
        ]
        if not self.rows:
            styles.append(("SPAN", (0, 1), (-1, 1)))
        elif nectar:
            styles.append(
                ("BACKGROUND", (4, 1), (-1, last_entry), colors.HexColor("#e6e6e6"))
            )
        if self.rows and summary_rows:
            styles.append(("NOSPLIT", (0, last_entry), (-1, summary_rows[0] + 1)))
        for total_row in summary_rows:
            balance_row = total_row + 1
            styles.extend(
                [
                    ("SPAN", (0, total_row), (3, total_row)),
                    ("SPAN", (0, balance_row), (4, balance_row)),
                    ("NOSPLIT", (0, total_row), (-1, balance_row)),
                    ("LINEABOVE", (0, total_row), (-1, total_row), 0.7, border),
                    ("LINEBELOW", (0, balance_row), (-1, balance_row), 0.7, border),
                    (
                        "BACKGROUND",
                        (0, balance_row),
                        (-1, balance_row),
                        colors.HexColor("#6d6d6d" if nectar else "#f0f0f0"),
                    ),
                ]
            )
        table.setStyle(TableStyle(styles))
        elements.append(table)
        return elements


class ClientStatementPDFView(APIView):
    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk, language="fr", *args, **kwargs):
        query = ClientStatementQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        client = get_object_or_404(
            Client.objects.select_related("company"),
            pk=pk,
            company_id=filters["company_id"],
        )
        if not can_print(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )
        return ClientStatementPDFGenerator(
            client, client.company, language, filters
        ).generate_pdf()


class GenerateClientCodeView(CompanyAccessMixin, APIView):
    """Return the next available ``code_client`` (e.g. ``CLT0018``).
    Automatically increases digit count when 9999 is reached."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("company_id manquant dans les paramètres."))

        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise Http404(_("company_id doit être un entier valide."))

        if not self._has_membership(request.user, company_id):
            raise PermissionDenied(_("Vous n'avez pas accès à cette société."))

        new_code = get_next_client_code(company_id)
        return Response({"code_client": new_code}, status=status.HTTP_200_OK)


class ArchiveToggleClientView(CompanyAccessMixin, APIView):
    """Toggle ``archived`` status for a client.
    - PATCH with ``{"archived": true}`` → archive
    - PATCH with ``{"archived": false}`` → un‑archive
    - If the field is omitted, the status is simply toggled.
    """

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _to_bool(value):
        """Convert common string/number representations to a bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "y")
        return None

    @staticmethod
    def get_object(pk):
        try:
            return Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            raise Http404(_("Aucun client ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier l'état de ce client.")
            )

        # Check if user has update permission
        if not can_update(request.user, client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier l'état de ce client.")
            )

        # Determine the desired state
        if "archived" in request.data:
            new_state = self._to_bool(request.data["archived"])
        else:
            # toggle when not explicitly provided
            new_state = not client.archived
        client.archived = new_state
        client.save(update_fields=["archived"])
        serializer = ClientDetailSerializer(client)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BulkDeleteClientView(BaseBulkDeleteView):
    model = Client
    document_name = "client"

    def get_queryset_with_related(self, ids):
        return Client.objects.filter(pk__in=ids)

    def get_company_id(self, obj):
        return obj.company_id


class BulkArchiveClientView(BaseBulkArchiveView):
    model = Client
    document_name = "client"

    def get_queryset_with_related(self, ids):
        return Client.objects.filter(pk__in=ids)

    def get_company_id(self, obj):
        return obj.company_id
