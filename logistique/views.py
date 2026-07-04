from decimal import Decimal

from django.db.models import Count, Sum, Q, DecimalField
from django.db.models.functions import Coalesce
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from core.constants import ROLE_CAISSIER, ROLE_COMPTABLE, ROLE_LOGISTIQUE
from core.permissions import can_create, can_delete, can_update, get_user_role
from core.views import BaseBulkDeleteView, CompanyAccessMixin
from facturation_backend.utils import CustomPagination

from .filters import LogisticsOrderFilter
from .models import LogisticsOrder
from .serializers import (
    LogisticsOrderCreateSerializer,
    LogisticsOrderDetailSerializer,
    LogisticsOrderListSerializer,
    LogisticsOrderUpdateSerializer,
    LogisticsPaymentRejectSerializer,
    LogisticsPaymentValidationSerializer,
    LogisticsStatusSerializer,
)
from .services import create_orders_from_proformas, send_payment_request_email
from .utils import get_next_numero_logistique


def _money_field():
    return DecimalField(max_digits=12, decimal_places=2)


def _has_payment_validation_permission(user, company_id):
    if getattr(user, "is_superuser", False):
        return True
    return get_user_role(user, company_id) in {ROLE_CAISSIER, ROLE_COMPTABLE}


def _can_manage_logistics(user, company_id):
    return (
        can_update(user, company_id)
        or get_user_role(user, company_id) == ROLE_LOGISTIQUE
    )


def _can_create_logistics(user, company_id):
    return (
        can_create(user, company_id)
        or get_user_role(user, company_id) == ROLE_LOGISTIQUE
    )


def _notify_logistics_responsible(order, message):
    if not order.responsable_id:
        return
    from notification.models import Notification

    Notification.objects.create(
        user=order.responsable,
        title=_("Paiement logistique validé"),
        message=message,
        notification_type="status_change",
        object_id=order.id,
        target_url=f"/dashboard/logistique/{order.id}?company_id={order.company_id}",
    )


def get_logistics_stats(company_id):
    base = LogisticsOrder.objects.filter(company_id=company_id)
    today = timezone.localdate()
    active = base.exclude(statut__in=["Clôture", "Annulé"])
    delayed = active.filter(date_prevue__lt=today)
    pending_payments = base.filter(statut_paiement="En attente")
    delivered = base.filter(statut__in=["Livraison client", "Clôture"])

    stats = {
        "commandes_en_cours": active.count(),
        "total_commandes": base.count(),
        "retards": delayed.count(),
        "paiements_en_attente": pending_payments.count(),
        "livraisons": delivered.count(),
        "couts_logistiques": base.aggregate(
            total=Coalesce(Sum("cout_total"), Decimal("0"), output_field=_money_field())
        )["total"],
        "swift_manquant": base.filter(statut_paiement="Validé")
        .filter(Q(swift_file="") | Q(swift_file__isnull=True))
        .count(),
        "documents_non_recus": base.filter(
            statut__in=["Documents originaux", "Transit"],
        )
        .filter(
            Q(documents_originaux_file="") | Q(documents_originaux_file__isnull=True)
        )
        .count(),
        "transit_non_lance": base.filter(
            statut__in=["Expédition", "Documents originaux"]
        ).count(),
    }
    stats["kpi_fournisseurs"] = list(
        base.values("fournisseur")
        .exclude(fournisseur="")
        .annotate(
            total_commandes=Count("id"),
            cout_total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        )
        .order_by("-total_commandes")[:5]
    )
    return stats


class LogisticsOrderListCreateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            error_message="company_id est requis.",
        )
        self._check_company_access(request, company_id)
        queryset = (
            LogisticsOrder.objects.filter(company_id=company_id)
            .select_related("company", "marque", "responsable", "created_by_user")
            .prefetch_related("proformas", "lignes", "lignes__client")
        )
        filterset = LogisticsOrderFilter(request.GET, queryset=queryset)
        ordered_qs = filterset.qs.order_by("-id")
        stats = {"stats": get_logistics_stats(company_id)}

        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = LogisticsOrderListSerializer(
                page, many=True, context={"request": request}
            )
            response = paginator.get_paginated_response(serializer.data)
            response.data.update(stats)
            return response

        serializer = LogisticsOrderListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(
            {"results": serializer.data, **stats}, status=status.HTTP_200_OK
        )

    def post(self, request, *args, **kwargs):
        company_id = request.data.get("company_id") or request.query_params.get(
            "company_id"
        )
        company_id = self._parse_company_id(
            company_id, error_message="company_id est requis."
        )
        self._check_company_access(request, company_id)
        if not _can_create_logistics(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer une commande logistique.")
            )

        serializer = LogisticsOrderCreateSerializer(
            data=request.data,
            context={"company_id": company_id, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        defaults = serializer.validated_data.copy()
        proforma_ids = defaults.pop("proformas")
        orders = create_orders_from_proformas(
            company_id=company_id,
            proforma_ids=proforma_ids,
            user=request.user,
            defaults=defaults,
        )
        response_serializer = LogisticsOrderDetailSerializer(
            orders, many=True, context={"request": request}
        )
        return Response(
            {"created": len(orders), "orders": response_serializer.data},
            status=status.HTTP_201_CREATED,
        )


class LogisticsOrderDetailEditDeleteView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @staticmethod
    def get_object(pk):
        try:
            return (
                LogisticsOrder.objects.select_related(
                    "company",
                    "marque",
                    "responsable",
                    "created_by_user",
                    "demande_paiement_envoyee_par",
                    "paiement_valide_par",
                )
                .prefetch_related(
                    "proformas",
                    "lignes",
                    "lignes__client",
                    "lignes__article",
                    "events",
                )
                .get(pk=pk)
            )
        except LogisticsOrder.DoesNotExist:
            raise Http404(_("Aucune commande logistique ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        order = self.get_object(pk)
        self._check_company_access(request, order.company_id)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        order = self.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cette commande logistique.")
            )
        serializer = LogisticsOrderUpdateSerializer(
            order,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        response_serializer = LogisticsOrderDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        order = self.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not can_delete(request.user, order.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour supprimer cette commande logistique."
                )
            )
        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateNumeroLogistiqueView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            error_message="company_id est requis.",
        )
        self._check_company_access(request, company_id)
        return Response(
            {"numero_commande": get_next_numero_logistique(company_id)},
            status=status.HTTP_200_OK,
        )


class LogisticsResponsibleOptionsView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            error_message="company_id est requis.",
        )
        self._check_company_access(request, company_id)
        memberships = (
            Membership.objects.filter(company_id=company_id, user__is_active=True)
            .select_related("user", "role")
            .order_by("user__first_name", "user__last_name", "user__email")
        )
        results = []
        for membership in memberships:
            user = membership.user
            display_name = f"{user.first_name} {user.last_name}".strip() or user.email
            role_name = membership.role.name if membership.role else ""
            results.append(
                {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "role": role_name,
                    "label": (
                        f"{display_name} - {role_name}" if role_name else display_name
                    ),
                }
            )
        return Response(results, status=status.HTTP_200_OK)


class LogisticsOrderStatusUpdateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def patch(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cette commande logistique.")
            )
        serializer = LogisticsStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.set_status(serializer.validated_data["statut"], user=request.user)
        return Response({"statut": order.statut}, status=status.HTTP_200_OK)


class LogisticsPaymentRequestView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour demander ce paiement.")
            )
        order = send_payment_request_email(order, request_user=request.user)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentValidateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _has_payment_validation_permission(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour valider ce paiement.")
            )
        serializer = LogisticsPaymentValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        old_status = order.statut_paiement
        order.statut_paiement = "Validé"
        order.statut = "Paiement effectué"
        order.paiement_valide_le = timezone.now()
        order.paiement_valide_par = request.user
        order.date_paiement = data.get("date_paiement") or timezone.localdate()
        order.montant_paiement = data.get("montant_paiement") or order.montant_paiement
        order.reference_paiement = data.get(
            "reference_paiement", order.reference_paiement
        )
        order.methode_paiement = data.get("methode_paiement") or order.methode_paiement
        if data.get("swift_file"):
            order.swift_file = data["swift_file"]
            order.date_upload_swift = timezone.now()
        order.save()
        order.add_event(
            user=request.user,
            action="Validation paiement",
            old_value=old_status,
            new_value="Validé",
        )
        _notify_logistics_responsible(
            order,
            _("Le paiement de la commande %(numero)s a été validé.")
            % {"numero": order.numero_commande},
        )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentRejectView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _has_payment_validation_permission(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour rejeter ce paiement.")
            )
        serializer = LogisticsPaymentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_status = order.statut_paiement
        order.statut_paiement = "Rejeté"
        order.save(update_fields=["statut_paiement", "date_updated"])
        order.add_event(
            user=request.user,
            action="Rejet paiement",
            old_value=old_status,
            new_value="Rejeté",
            note=serializer.validated_data.get("note", ""),
        )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsSwiftSentView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour envoyer ce SWIFT.")
            )
        order.swift_envoye_fournisseur_le = timezone.now()
        order.statut = "Envoi SWIFT / Draft LC"
        order.save(
            update_fields=["swift_envoye_fournisseur_le", "statut", "date_updated"]
        )
        order.add_event(
            user=request.user,
            action="Envoi SWIFT fournisseur",
            new_value="Envoyé",
        )
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsDashboardView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            error_message="company_id est requis.",
        )
        self._check_company_access(request, company_id)
        return Response(get_logistics_stats(company_id), status=status.HTTP_200_OK)


class BulkDeleteLogisticsOrderView(BaseBulkDeleteView):
    model = LogisticsOrder
    document_name = "commande logistique"

    def get_queryset_with_related(self, ids):
        return LogisticsOrder.objects.filter(pk__in=ids).select_related("company")

    def get_company_id(self, obj):
        return obj.company_id
