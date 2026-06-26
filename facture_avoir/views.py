from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import DecimalField, Sum as DjangoSum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from reportlab.lib.units import cm
from reportlab.platypus import Spacer, Paragraph, KeepTogether
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from company.models import Company
from core.authentication import JWTQueryParamAuthentication
from core.pdf_utils import BasePDFGenerator
from core.permissions import (
    can_change_document_status,
    can_create,
    can_update,
    can_print,
)
from core.views import (
    BaseDocumentDetailEditDeleteView,
    BaseDocumentListCreateView,
    BaseGenerateNumeroView,
    BaseStatusUpdateView,
    BaseBulkDeleteView,
)
from facture_client.models import FactureClient
from facturation_backend.utils import CustomPagination
from .filters import FactureAvoirFilter
from .models import FactureAvoir
from .serializers import (
    FactureAvoirDetailSerializer,
    FactureAvoirListSerializer,
    FactureAvoirSerializer,
)
from .stats import get_avoir_stats_by_currency
from .utils import get_next_numero_facture_avoir


class FactureAvoirListCreateView(BaseDocumentListCreateView):
    model = FactureAvoir
    filter_class = FactureAvoirFilter
    list_serializer_class = FactureAvoirListSerializer
    create_serializer_class = FactureAvoirSerializer
    detail_serializer_class = FactureAvoirDetailSerializer
    document_name = "la facture d'avoir"
    list_select_related = (
        "client",
        "mode_paiement",
        "created_by_user",
        "facture_origine",
    )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            "Aucune facture d'avoir ne correspond à la requête.",
        )
        self._check_company_access(request, company_id)

        base_queryset = (
            self.model.objects.filter(company_id=company_id)
            .select_related(*self.list_select_related)
            .prefetch_related(*self.list_prefetch_related)
        )
        filterset = self.filter_class(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        extra_stats = {"stats_by_currency": get_avoir_stats_by_currency(company_id)}

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
        return Response({"results": serializer.data, **extra_stats})

    def post(self, request, *args, **kwargs):
        facture_origine_id = request.data.get("facture_origine")

        if not facture_origine_id:
            raise ValidationError(
                {"facture_origine": _("Une facture d'origine est requise.")}
            )
        facture_origine = get_object_or_404(FactureClient, pk=facture_origine_id)
        company_id = facture_origine.company_id

        self._check_company_access(request, company_id)
        if not can_create(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer cette facture d'avoir.")
            )

        serializer = self.create_serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by_user=request.user)
        from notification.services import notify_document_created

        notify_document_created(
            instance,
            company_id=company_id,
            document_label="facture d'avoir",
            creator=request.user,
        )
        response_serializer = self.detail_serializer_class(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class FactureAvoirDetailEditView(BaseDocumentDetailEditDeleteView):
    model = FactureAvoir
    detail_serializer_class = FactureAvoirDetailSerializer
    document_name = "facture d'avoir"
    detail_select_related = (
        "client",
        "mode_paiement",
        "created_by_user",
        "facture_origine",
    )

    def put(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if object_.statut != "Brouillon":
            raise ValidationError(
                _("Seuls les avoirs en brouillon peuvent être modifiés.")
            )
        return super().put(request, pk, *args, **kwargs)


class GenerateNumeroFactureAvoirView(BaseGenerateNumeroView):
    numero_generator = get_next_numero_facture_avoir
    response_key = "numero_avoir"


class FactureAvoirStatusUpdateView(BaseStatusUpdateView):
    model = FactureAvoir
    document_name = "facture d'avoir"

    def patch(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cette facture d'avoir.")
            )
        if not can_update(request.user, object_.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cette facture d'avoir.")
            )
        if not can_change_document_status(request.user, object_.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour modifier le statut de cette facture d'avoir."
                )
            )

        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in self.model.STATUT_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})
        if new_status in ("Envoyé", "Accepté"):
            try:
                object_.validate_against_origin_total()
            except DjangoValidationError as exc:
                raise ValidationError({"total_ttc_apres_remise": exc.messages})
        object_.statut = new_status
        object_.save(update_fields=["statut"])
        return Response({"statut": object_.statut}, status=status.HTTP_200_OK)


class BulkDeleteFactureAvoirView(BaseBulkDeleteView):
    model = FactureAvoir
    document_name = "facture d'avoir"

    def get_queryset_with_related(self, ids):
        return FactureAvoir.objects.filter(pk__in=ids).select_related(
            "client", "facture_origine"
        )

    def get_company_id(self, obj):
        return obj.company_id


class FactureAvoirFromFactureView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int):
        facture = get_object_or_404(
            FactureClient.objects.select_related("client", "mode_paiement", "company"),
            pk=pk,
        )
        from account.models import Membership

        if not Membership.objects.filter(
            user=request.user, company_id=facture.company_id
        ).exists():
            raise PermissionDenied(_("Vous n'avez pas accès à cette société."))

        credited = (
            FactureAvoir.objects.filter(facture_origine=facture)
            .exclude(statut__in=["Brouillon", "Annulé", "Refusé", "Expiré"])
            .aggregate(
                total=Coalesce(
                    DjangoSum("total_ttc_apres_remise"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=10, decimal_places=2),
                )
            )
        )["total"]

        lignes = []
        for line in facture.lignes.select_related("article").all():
            lignes.append(
                {
                    "article": line.article_id,
                    "reference": line.article.reference,
                    "designation": line.article.designation,
                    "prix_achat": str(line.prix_achat),
                    "devise_prix_achat": line.devise_prix_achat,
                    "prix_vente": str(line.prix_vente),
                    "devise_prix_vente": line.devise_prix_vente,
                    "quantity": str(line.quantity),
                    "remise_type": line.remise_type,
                    "remise": str(line.remise),
                }
            )

        return Response(
            {
                "facture_origine": facture.id,
                "facture_origine_numero": facture.numero_facture,
                "facture_origine_date": facture.date_facture,
                "client": facture.client_id,
                "client_name": str(facture.client),
                "mode_paiement": facture.mode_paiement_id,
                "date_avoir": timezone.localdate(),
                "numero_bon_commande_client": facture.numero_bon_commande_client,
                "devise": facture.devise,
                "remise_type": facture.remise_type,
                "remise": str(facture.remise),
                "facture_total": str(facture.total_ttc_apres_remise),
                "already_credited_total": str(credited or Decimal("0.00")),
                "lignes": lignes,
            }
        )


class FactureAvoirPDFGenerator(BasePDFGenerator):
    def _label(self, fr_value: str, en_value: str) -> str:
        return en_value if self.language == "en" else fr_value

    def _build_content(self) -> list:
        elements = []
        number_label = self._label("FACTURE D'AVOIR N°", "CREDIT NOTE NO.")
        date_label = self._label("DATE DE L'AVOIR:", "CREDIT NOTE DATE:")
        elements.append(
            self._build_doc_header(
                f"{number_label} {self.document.numero_avoir}",
                f"{date_label} {self.document.date_avoir.strftime('%d/%m/%Y')}",
            )
        )
        elements.append(Spacer(1, 0.5 * cm))

        extra_lines = []
        if self.document.facture_origine:
            original_invoice_label = self._label(
                "Facture d'origine", "Original invoice"
            )
            extra_lines.append(
                Paragraph(
                    f"{original_invoice_label}: "
                    f"{self.document.facture_origine.numero_facture} - "
                    f"{self.document.facture_origine.date_facture.strftime('%d/%m/%Y')}",
                    self.styles["CustomSmall"],
                )
            )
        else:
            extra_lines.append(
                Paragraph(
                    self._label("Avoir libre sans facture d'origine", "Free credit note without original invoice"),
                    self.styles["CustomSmall"],
                )
            )
        extra_lines.append(
            Paragraph(
                f"{self._label('Motif', 'Reason')}: {self.document.get_motif_avoir_display()}",
                self.styles["CustomSmall"],
            )
        )
        extra_lines.append(
            Paragraph(
                self._label("Montants à déduire", "Amounts to deduct"),
                self.styles["CustomSmall"],
            )
        )

        issued_by_label = self._label(
            "FACTURE D'AVOIR EMISE PAR", "CREDIT NOTE ISSUED BY"
        )
        elements.append(
            self._build_parties_grid(
                Paragraph(f"<b>{issued_by_label}</b>", self.styles["SectionHeader"]),
                extra_company_lines=extra_lines,
            )
        )
        elements.append(Spacer(1, 0.7 * cm))
        show_remise = self._should_show_remise()
        show_unite = self._should_show_unite()
        elements.append(
            self._build_standard_articles_table(
                show_remise=show_remise, show_unite=show_unite
            )
        )
        elements.append(Spacer(1, 0.3 * cm))
        elements.append(
            KeepTogether(
                self._build_tail(
                    self._label(
                        "ARRÊTÉE LA PRÉSENTE FACTURE D'AVOIR À DÉDUIRE À LA SOMME DE",
                        "THIS CREDIT NOTE TO DEDUCT IS SET AT THE AMOUNT OF",
                    ),
                    default_remarks_key=None,
                    show_remise=show_remise,
                )
            )
        )
        return elements

    def _get_filename(self) -> str:
        return f"facture_avoir_{self.document.numero_avoir.replace('/', '_')}.pdf"

    def _get_pdf_title(self) -> str:
        client_name = self.document.client.raison_sociale or self._label("Client", "Client")
        return f"{self._label('Facture d avoir', 'Credit note')} {self.document.numero_avoir} - {client_name}"


class FactureAvoirPDFView(APIView):
    authentication_classes = [JWTQueryParamAuthentication]
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, pk: int, language: str = "fr"):
        company_id = request.query_params.get("company_id")
        pdf_type = request.query_params.get("type", "avec_remise")
        if not company_id:
            return Response(
                {"error": _("company_id query parameter is required")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company = get_object_or_404(Company, pk=company_id)
        facture_avoir = get_object_or_404(
            FactureAvoir.objects.select_related("client", "facture_origine"),
            pk=pk,
            company_id=company_id,
        )

        if not can_print(request.user, company.pk):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour imprimer ce document.")
            )
        if facture_avoir.statut == "Brouillon":
            raise PermissionDenied(
                _("Impossible d'imprimer un document en brouillon.")
            )
        if not facture_avoir.facture_origine_id:
            raise PermissionDenied(
                _("Une facture d'origine est requise pour imprimer cet avoir.")
            )

        pdf_generator = FactureAvoirPDFGenerator(
            facture_avoir, company, pdf_type, language
        )
        return pdf_generator.generate_pdf()
