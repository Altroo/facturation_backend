from collections import Counter
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
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
from core.constants import ROLE_COMPTABLE, ROLE_LOGISTIQUE
from core.permissions import (
    can_change_document_status,
    can_create,
    can_delete,
    can_update,
    get_user_role,
)
from core.views import BaseBulkDeleteView, CompanyAccessMixin
from facturation_backend.utils import CustomPagination

from .filters import LogisticsOrderFilter
from .models import LogisticsOrder, LogisticsPaymentInstallment
from .serializers import (
    LOGISTICS_IMPORT_TITLE_FIELDS,
    LogisticsOrderCreateSerializer,
    LogisticsOrderDetailSerializer,
    LogisticsOrderListSerializer,
    LogisticsOrderUpdateSerializer,
    LogisticsGlobalStatusSerializer,
    LogisticsLaunchStatusSerializer,
    LogisticsPaymentRejectSerializer,
    LogisticsPaymentExecutionSerializer,
    LogisticsPaymentInstallmentActionSerializer,
    LogisticsPaymentRequestSerializer,
    LogisticsPaymentValidationSerializer,
    LogisticsProformaRequestSerializer,
    LogisticsSupplierProformaReviewSerializer,
    LogisticsStatusSerializer,
)
from .services import (
    build_proforma_source_preview,
    create_orders_from_proformas,
    send_payment_request_email,
)
from .utils import get_next_numero_logistique


def _money_field():
    return DecimalField(max_digits=12, decimal_places=2)


def _add_months(date_value, months):
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    return date_value.replace(year=year, month=month, day=1)


def _month_start_datetime(date_value):
    return timezone.make_aware(datetime.combine(date_value, time.min))


def _has_payment_validation_permission(user, company_id):
    if getattr(user, "is_superuser", False):
        return True
    return get_user_role(user, company_id) == ROLE_COMPTABLE


def _is_order_responsible(user, order):
    return bool(
        getattr(user, "is_superuser", False)
        or (order.responsable_id and order.responsable_id == user.id)
    )


def _can_process_assigned_payment(user, order):
    return bool(
        getattr(user, "is_superuser", False)
        or (
            _has_payment_validation_permission(user, order.company_id)
            and order.paiement_assigne_a_id == user.id
        )
    )


def _get_locked_installment(order, installment_id):
    try:
        return order.echeances_paiement.select_for_update().get(pk=installment_id)
    except LogisticsPaymentInstallment.DoesNotExist:
        raise ValidationError(
            {"echeance_id": _("Cette échéance n'appartient pas au dossier.")}
        )


def _clear_payment_installment_cache(order):
    getattr(order, "_prefetched_objects_cache", {}).pop("echeances_paiement", None)


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


def _ensure_order_active(order):
    if order.statut_global == "Annulé":
        raise ValidationError(
            {"statut_global": _("Rouvrez le dossier avant de poursuivre le workflow.")}
        )


def _invalidate_or_block_active_email_deliveries(order, *, reason):
    installments = list(order.echeances_paiement.select_for_update())
    if order.demande_paiement_email_statut == "Envoi en cours" or any(
        item.preuve_email_statut == "Envoi en cours" for item in installments
    ):
        raise ValidationError(
            {
                "email": _(
                    "Attendez la fin de l'envoi e-mail en cours avant cette action."
                )
            }
        )
    if order.demande_paiement_email_statut == "En attente":
        order.demande_paiement_email_statut = "Échec"
        order.demande_paiement_email_erreur = reason
        order.demande_paiement_email_file_token = ""
        order.demande_paiement_email_mis_en_file_le = None
        order.save(
            update_fields=[
                "demande_paiement_email_statut",
                "demande_paiement_email_erreur",
                "demande_paiement_email_file_token",
                "demande_paiement_email_mis_en_file_le",
                "date_updated",
            ]
        )
    for installment in installments:
        if installment.preuve_email_statut != "En attente":
            continue
        installment.preuve_email_statut = "Échec"
        installment.preuve_email_erreur = reason
        installment.preuve_email_file_token = ""
        installment.preuve_email_mise_en_file_le = None
        installment.save(
            update_fields=[
                "preuve_email_statut",
                "preuve_email_erreur",
                "preuve_email_file_token",
                "preuve_email_mise_en_file_le",
                "date_updated",
            ]
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


def _assign_payment_task(order):
    membership = (
        Membership.objects.filter(
            company_id=order.company_id,
            role__name=ROLE_COMPTABLE,
            user__is_active=True,
        )
        .exclude(user__email="")
        .select_related("user")
        .order_by("user_id")
        .first()
    )
    if not membership:
        raise ValidationError(
            {
                "paiement": _(
                    "Aucun utilisateur actif du Service Comptable n'est disponible."
                )
            }
        )
    from notification.models import Notification

    order.paiement_assigne_a = membership.user
    Notification.objects.create(
        user=membership.user,
        title=_("Effectuer le paiement fournisseur"),
        message=_("Le dossier import %(reference)s est prêt pour paiement.")
        % {"reference": order.numero_commande},
        notification_type="status_change",
        object_id=order.id,
        target_url=f"/dashboard/logistique/{order.id}?company_id={order.company_id}",
    )
    return membership.user


def get_logistics_stats(company_id):
    base = LogisticsOrder.objects.filter(company_id=company_id)
    global_status_counts = Counter(
        order.calculate_global_status() for order in base.iterator()
    )
    today = timezone.localdate()
    current_month = today.replace(day=1)
    months = [_add_months(current_month, offset) for offset in range(-5, 1)]
    active_count = sum(
        total
        for global_status, total in global_status_counts.items()
        if global_status not in {"Clôturé", "Annulé"}
    )
    pending_payments = base.filter(statut_paiement="En attente")
    delivered = base.filter(
        Q(statut_global__in=["À clôturer", "Clôturé"])
        | Q(statut__in=["Livraison client", "Clôture"])
    ).distinct()
    monthly_flow = []

    for month_start in months:
        month_end = _add_months(month_start, 1)
        month_start_dt = _month_start_datetime(month_start)
        month_end_dt = _month_start_datetime(month_end)
        created_in_month = base.filter(
            date_created__gte=month_start_dt,
            date_created__lt=month_end_dt,
        )
        monthly_flow.append(
            {
                "month": month_start.strftime("%Y-%m"),
                "commandes": created_in_month.count(),
                "livraisons": delivered.filter(
                    date_reelle__gte=month_start,
                    date_reelle__lt=month_end,
                ).count(),
                "paiements": base.filter(
                    statut_paiement="Validé",
                    paiement_valide_le__gte=month_start_dt,
                    paiement_valide_le__lt=month_end_dt,
                ).count(),
                "cout_total": created_in_month.aggregate(
                    total=Coalesce(
                        Sum("cout_total"), Decimal("0"), output_field=_money_field()
                    )
                )["total"],
            }
        )

    stats = {
        "commandes_en_cours": active_count,
        "total_commandes": base.count(),
        "retards": global_status_counts.get("En retard", 0),
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
        "statuts_workflow": [
            {"statut": global_status, "total": total}
            for global_status, total in sorted(global_status_counts.items())
        ],
        "statuts_paiement": list(
            base.values("statut_paiement")
            .annotate(total=Count("id"))
            .order_by("statut_paiement")
        ),
        "couts_detail": base.aggregate(
            achat=Coalesce(
                Sum("cout_achat"), Decimal("0"), output_field=_money_field()
            ),
            transport=Coalesce(
                Sum("cout_transport"), Decimal("0"), output_field=_money_field()
            ),
            transit=Coalesce(
                Sum("frais_transit"), Decimal("0"), output_field=_money_field()
            ),
            douane=Coalesce(
                Sum("frais_douane"), Decimal("0"), output_field=_money_field()
            ),
            tva=Coalesce(Sum("tva"), Decimal("0"), output_field=_money_field()),
            livraison_locale=Coalesce(
                Sum("livraison_locale"), Decimal("0"), output_field=_money_field()
            ),
            autres=Coalesce(
                Sum("autres_frais"), Decimal("0"), output_field=_money_field()
            ),
            total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        ),
        "monthly_flow": monthly_flow,
    }
    stats["marques"] = [
        {"id": brand["marque"], "nom": brand["marque__nom"]}
        for brand in base.exclude(marque__isnull=True)
        .exclude(marque__nom="")
        .order_by("marque__nom")
        .values("marque", "marque__nom")
        .distinct()[:100]
    ]
    stats["kpi_marques"] = list(
        base.exclude(marque__isnull=True)
        .exclude(marque__nom="")
        .values("marque", "marque__nom")
        .annotate(
            total_commandes=Count("id"),
            cout_total=Coalesce(
                Sum("cout_total"), Decimal("0"), output_field=_money_field()
            ),
        )
        .order_by("-total_commandes")[:5]
    )
    stats["fournisseurs"] = list(
        base.exclude(fournisseur="")
        .order_by("fournisseur")
        .values("fournisseur")
        .distinct()[:100]
    )
    stats["kpi_fournisseurs"] = list(
        base.exclude(fournisseur="")
        .values("fournisseur")
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
            .prefetch_related(
                "proformas", "lignes", "lignes__client", "echeances_paiement"
            )
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
                _("Vous n'avez pas les droits pour créer un dossier logistique.")
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


class LogisticsOrderSourcePreviewView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser,)

    def post(self, request, *args, **kwargs):
        company_id = request.data.get("company_id") or request.query_params.get(
            "company_id"
        )
        company_id = self._parse_company_id(
            company_id, error_message="company_id est requis."
        )
        self._check_company_access(request, company_id)

        proformas = request.data.get("proformas") or []
        preview = build_proforma_source_preview(
            company_id=company_id,
            proforma_ids=proformas,
        )
        return Response(preview, status=status.HTTP_200_OK)


class LogisticsOrderDetailEditDeleteView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @staticmethod
    def get_object(pk, *, for_update=False):
        try:
            queryset = LogisticsOrder.objects
            if for_update:
                queryset = queryset.select_for_update(of=("self",))
            return (
                queryset.select_related(
                    "company",
                    "marque",
                    "responsable",
                    "created_by_user",
                    "demande_paiement_envoyee_par",
                    "proforma_demandee_par",
                    "proforma_controlee_par",
                    "proforma_validee_par",
                    "paiement_valide_par",
                    "paiement_assigne_a",
                )
                .prefetch_related(
                    "proformas",
                    "lignes",
                    "lignes__client",
                    "lignes__article",
                    "events",
                    "echeances_paiement",
                    "echeances_paiement__execution_enregistree_par",
                    "echeances_paiement__paiement_valide_par",
                    "echeances_paiement__reception_confirmee_par",
                )
                .get(pk=pk)
            )
        except LogisticsOrder.DoesNotExist:
            raise Http404(_("Aucun dossier logistique ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        order = self.get_object(pk)
        self._check_company_access(request, order.company_id)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def put(self, request, pk, *args, **kwargs):
        order = self.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        can_manage = _can_manage_logistics(request.user, order.company_id)
        is_responsible = _is_order_responsible(request.user, order)
        requested_fields = set(request.data.keys())
        if not can_manage and not is_responsible:
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce dossier logistique.")
            )
        if requested_fields & LOGISTICS_IMPORT_TITLE_FIELDS and not is_responsible:
            raise PermissionDenied(
                _("Seul le Responsable Commande peut modifier le titre d'importation.")
            )
        if not can_manage and requested_fields - LOGISTICS_IMPORT_TITLE_FIELDS:
            raise PermissionDenied(
                _(
                    "Le Responsable Commande peut uniquement modifier le titre d'importation."
                )
            )
        _ensure_order_active(order)
        serializer = LogisticsOrderUpdateSerializer(
            order,
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        instance.sync_global_status(preserve_manual=True)
        response_serializer = LogisticsOrderDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        order = self.get_object(pk)
        self._check_company_access(request, order.company_id)
        if not can_delete(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour supprimer ce dossier logistique.")
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

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce dossier logistique.")
            )
        _ensure_order_active(order)
        serializer = LogisticsStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data["statut"]
        if requested_status == "Annulé":
            raise ValidationError(
                {"statut": _("Utilisez l'action dédiée pour annuler ce dossier.")}
            )
        if (
            requested_status in LogisticsOrder.LEGACY_PROFORMA_COMPLETE_STATUSES
            and not order.is_proforma_step_complete
        ):
            raise ValidationError(
                {"statut": _("Validez d'abord la pro forma fournisseur.")}
            )
        if (
            requested_status in LogisticsOrder.PAYMENT_COMPLETE_REQUIRED_STATUSES
            and not order.is_payment_step_complete
        ):
            raise ValidationError(
                {"statut": _("Validez d'abord la totalité du paiement requis.")}
            )
        order.set_status(requested_status, user=request.user)
        order.sync_global_status(preserve_manual=False)
        return Response(
            {"statut": order.statut, "statut_global": order.statut_global},
            status=status.HTTP_200_OK,
        )


class LogisticsOrderGlobalStatusUpdateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_change_document_status(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce dossier logistique.")
            )
        serializer = LogisticsGlobalStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data["statut"]
        if requested_status not in {"Annulé", "Rouvert"}:
            raise ValidationError(
                {
                    "statut": _(
                        "Le statut global est calculé automatiquement. Seuls Annulé et Rouvert peuvent être appliqués manuellement."
                    )
                }
            )
        if requested_status == "Rouvert" and order.statut_global != "Annulé":
            raise ValidationError(
                {"statut": _("Seul un dossier annulé peut être rouvert.")}
            )
        if requested_status == "Annulé" and order.statut_global == "Annulé":
            raise ValidationError({"statut": _("Ce dossier est déjà annulé.")})
        if requested_status == "Annulé":
            _invalidate_or_block_active_email_deliveries(
                order,
                reason=_("Envoi annulé car le dossier a été annulé."),
            )
        old_status = order.statut_global
        order.statut_global = requested_status
        order.save(update_fields=["statut_global", "date_updated"])
        order.add_event(
            user=request.user,
            action="Changement de statut global",
            old_value=old_status,
            new_value=requested_status,
        )
        return Response(
            {"statut_global": order.statut_global}, status=status.HTTP_200_OK
        )


class LogisticsProformaRequestView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour enregistrer cette demande de pro forma fournisseur."
                )
            )
        _ensure_order_active(order)
        if order.is_launch_step_complete:
            raise ValidationError(
                {
                    "proforma": _(
                        "La demande de pro forma fournisseur est déjà enregistrée."
                    )
                }
            )

        serializer = LogisticsProformaRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        old_status = order.statut_commande_lancement
        order.proforma_demandee_le = timezone.now()
        order.proforma_demandee_par = request.user
        order.prochaine_relance_proforma = serializer.validated_data[
            "prochaine_relance_proforma"
        ]
        order.statut_commande_lancement = "Terminée"
        order.statut = "Proforma"
        order.sync_global_status(preserve_manual=False, commit=False)
        order.save(
            update_fields=[
                "proforma_demandee_le",
                "proforma_demandee_par",
                "prochaine_relance_proforma",
                "statut_commande_lancement",
                "statut",
                "statut_global",
                "date_updated",
            ]
        )
        order.add_event(
            user=request.user,
            action="Demande de pro forma fournisseur",
            old_value=old_status,
            new_value="Terminée",
            note=_("Prochaine relance: %(date)s")
            % {"date": order.prochaine_relance_proforma.isoformat()},
        )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsLaunchStatusUpdateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cette étape.")
            )
        _ensure_order_active(order)
        serializer = LogisticsLaunchStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_status = serializer.validated_data["statut"]
        if order.is_launch_step_complete and requested_status != "Terminée":
            raise ValidationError(
                {
                    "statut": _(
                        "L'étape terminée ne peut plus être réouverte après le lancement de la suite du workflow."
                    )
                }
            )
        if requested_status == "Terminée" and not order.proforma_demandee_le:
            raise ValidationError(
                {
                    "statut": _(
                        "Enregistrez la demande de pro forma fournisseur pour terminer cette étape."
                    )
                }
            )

        old_status = order.statut_commande_lancement
        if requested_status != old_status:
            order.statut_commande_lancement = requested_status
            order.sync_global_status(preserve_manual=False, commit=False)
            order.save(
                update_fields=[
                    "statut_commande_lancement",
                    "statut_global",
                    "date_updated",
                ]
            )
            order.add_event(
                user=request.user,
                action="Changement statut Commande & lancement",
                old_value=old_status,
                new_value=requested_status,
            )

        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsSupplierProformaReviewView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour contrôler cette pro forma fournisseur."
                )
            )
        _ensure_order_active(order)
        if not order.is_launch_step_complete:
            raise ValidationError(
                {"proforma": _("Terminez d'abord l'étape Commande & lancement.")}
            )
        if order.is_proforma_step_complete:
            raise ValidationError(
                {"proforma": _("La pro forma fournisseur est déjà validée.")}
            )

        serializer = LogisticsSupplierProformaReviewSerializer(
            data=request.data,
            context={"order": order},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data.copy()
        action = data.pop("action")
        old_status = order.statut_proforma_conformite

        editable_fields = {
            "numero_proforma_fournisseur",
            "date_proforma_fournisseur",
            "montant_proforma_fournisseur",
            "devise_proforma_fournisseur",
            "incoterm",
            "conditions_paiement",
            "delai_proforma_jours",
            "ecart_prix_proforma",
            "ecart_quantite_proforma",
            "notes_ecarts_proforma",
            "proforma_fournisseur_file",
        }
        updated_fields = []
        for field in editable_fields:
            if field in data:
                setattr(order, field, data[field])
                updated_fields.append(field)

        status_by_action = {
            "control": "En contrôle",
            "request_correction": "Correction demandée",
            "validate": "Validée",
            "reject": "Refusée",
        }
        event_action_by_action = {
            "control": "Contrôle pro forma fournisseur",
            "request_correction": "Correction de la pro forma fournisseur demandée",
            "validate": "Validation de la pro forma fournisseur",
            "reject": "Refus de la pro forma fournisseur",
        }

        order.statut_proforma_conformite = status_by_action[action]
        order.statut = "Validation" if action == "validate" else "Proforma"
        order.proforma_controlee_le = timezone.now()
        order.proforma_controlee_par = request.user
        updated_fields.extend(
            [
                "statut_proforma_conformite",
                "statut_global",
                "statut",
                "proforma_controlee_le",
                "proforma_controlee_par",
            ]
        )
        if action == "validate":
            order.proforma_validee_le = timezone.now()
            order.proforma_validee_par = request.user
            updated_fields.extend(["proforma_validee_le", "proforma_validee_par"])

        order.sync_global_status(preserve_manual=False, commit=False)
        updated_fields.append("statut_global")

        order.save(update_fields=[*updated_fields, "date_updated"])
        order.add_event(
            user=request.user,
            action=event_action_by_action[action],
            old_value=old_status,
            new_value=order.statut_proforma_conformite,
            note=order.notes_ecarts_proforma,
        )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentRequestView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _is_order_responsible(request.user, order):
            raise PermissionDenied(
                _(
                    "Seul le Responsable Commande peut transmettre ce dossier au Service Comptable."
                )
            )
        _ensure_order_active(order)
        if not order.is_proforma_step_complete:
            raise ValidationError(
                {"paiement": _("Validez d'abord la pro forma fournisseur.")}
            )
        if order.statut_paiement != "Non demandé":
            raise ValidationError(
                {"paiement": _("La demande de paiement a déjà été traitée.")}
            )
        title_errors = {}
        if not (order.numero_domiciliation or "").strip():
            title_errors["numero_domiciliation"] = _("Ce champ est obligatoire.")
        if not (order.banque or "").strip():
            title_errors["banque"] = _("Ce champ est obligatoire.")
        if order.montant_titre_importation <= 0:
            title_errors["montant_titre_importation"] = _(
                "Le montant doit être supérieur à zéro."
            )
        if not order.date_titre_importation:
            title_errors["date_titre_importation"] = _("Ce champ est obligatoire.")
        if not order.methode_paiement:
            title_errors["methode_paiement"] = _("Ce champ est obligatoire.")
        if not order.titre_importation_file:
            title_errors["titre_importation_file"] = _(
                "Joignez le titre d'importation validé."
            )
        if title_errors:
            raise ValidationError(title_errors)
        request_serializer = LogisticsPaymentRequestSerializer(
            data=request.data,
            context={"order": order},
        )
        request_serializer.is_valid(raise_exception=True)
        order.echeances_paiement.all().delete()
        LogisticsPaymentInstallment.objects.bulk_create(
            [
                LogisticsPaymentInstallment(commande=order, **item)
                for item in request_serializer.validated_data["echeancier"]
            ]
        )
        _clear_payment_installment_cache(order)
        _assign_payment_task(order)
        order.date_validation_titre_importation = (
            order.date_validation_titre_importation or timezone.localdate()
        )
        order.statut_titre_importation = (
            "Titre d'import validé – En attente de paiement"
        )
        order.statut_banque_paiement = "En validation"
        order.statut_traitement_paiement = "Paiement à traiter"
        order.save(
            update_fields=[
                "date_validation_titre_importation",
                "statut_titre_importation",
                "statut_banque_paiement",
                "statut_traitement_paiement",
                "paiement_assigne_a",
                "date_updated",
            ]
        )
        order = send_payment_request_email(order, request_user=request.user)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentEmailRetryView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _is_order_responsible(request.user, order):
            raise PermissionDenied(
                _("Seul le Responsable Commande peut relancer cet e-mail.")
            )
        _ensure_order_active(order)
        if not order.demande_paiement_email_relance_disponible:
            raise ValidationError(
                {
                    "paiement": _(
                        "Cet e-mail n'est pas en échec, historique non vérifié ou bloqué."
                    )
                }
            )
        if order.statut_paiement != "En attente":
            raise ValidationError(
                {"paiement": _("Aucune demande de paiement n'est en attente.")}
            )

        delivery_token = uuid4().hex
        order.demande_paiement_email_statut = "En attente"
        order.demande_paiement_email_erreur = ""
        order.demande_paiement_email_task_id = ""
        order.demande_paiement_email_prise_en_charge_le = None
        order.demande_paiement_email_file_token = delivery_token
        order.demande_paiement_email_mis_en_file_le = timezone.now()
        order.demande_paiement_envoyee_le = None
        order.save(
            update_fields=[
                "demande_paiement_email_statut",
                "demande_paiement_email_erreur",
                "demande_paiement_email_task_id",
                "demande_paiement_email_prise_en_charge_le",
                "demande_paiement_email_file_token",
                "demande_paiement_email_mis_en_file_le",
                "demande_paiement_envoyee_le",
                "date_updated",
            ]
        )
        from .tasks import queue_accounting_payment_email

        transaction.on_commit(
            lambda order_id=order.id, token=delivery_token: queue_accounting_payment_email(
                order_id, token
            )
        )
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentStartView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        _ensure_order_active(order)
        serializer = LogisticsPaymentInstallmentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installment = _get_locked_installment(
            order, serializer.validated_data["echeance_id"]
        )
        if installment.statut_traitement != "Paiement à traiter":
            raise ValidationError(
                {"paiement": _("Cette échéance n'est plus à traiter.")}
            )
        installment.statut_traitement = "Paiement en cours"
        installment.save(update_fields=["statut_traitement", "date_updated"])
        _clear_payment_installment_cache(order)
        order.statut_banque_paiement = "Banque en cours"
        order.statut_traitement_paiement = "Paiement en cours"
        order.save(
            update_fields=[
                "statut_banque_paiement",
                "statut_traitement_paiement",
                "date_updated",
            ]
        )
        order.add_event(
            user=request.user,
            action="Démarrage paiement",
            new_value=f"Échéance {installment.id}",
        )
        return Response(
            LogisticsOrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class LogisticsPaymentExecutionView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        _ensure_order_active(order)
        serializer = LogisticsPaymentExecutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        installment = _get_locked_installment(order, data["echeance_id"])
        if installment.statut_traitement != "Paiement en cours":
            raise ValidationError(
                {"paiement": _("Commencez d'abord le traitement de cette échéance.")}
            )
        if data["devise_paiement"] != installment.devise:
            raise ValidationError(
                {"devise_paiement": _("La devise doit correspondre à l'échéance.")}
            )
        if data["montant_paye"] > installment.montant_prevu:
            raise ValidationError(
                {"montant_paye": _("Le montant payé dépasse le montant de l'échéance.")}
            )

        remaining_installment_amount = installment.montant_prevu - data["montant_paye"]
        if remaining_installment_amount > 0:
            LogisticsPaymentInstallment.objects.create(
                commande=order,
                date_echeance=installment.date_echeance,
                montant_prevu=remaining_installment_amount,
                devise=installment.devise,
            )
            installment.montant_prevu = data["montant_paye"]

        installment.date_paiement = data["date_paiement"]
        installment.montant_paye = data["montant_paye"]
        installment.banque = data["banque_paiement"]
        installment.reference_bancaire = data["reference_paiement"]
        installment.methode_paiement = data["methode_paiement"]
        installment.commentaire = data["commentaire_paiement"]
        installment.execution_enregistree_le = timezone.now()
        installment.execution_enregistree_par = request.user
        installment.statut_traitement = "Paiement effectué – Justificatif à joindre"
        installment.save()
        _clear_payment_installment_cache(order)

        order.date_paiement = installment.date_paiement
        order.montant_paiement = installment.montant_paye
        order.devise_paiement = installment.devise
        order.banque_paiement = installment.banque
        order.reference_paiement = installment.reference_bancaire
        order.commentaire_paiement = installment.commentaire
        order.statut_banque_paiement = "Banque en cours"
        order.statut_traitement_paiement = installment.statut_traitement
        order.save()
        order.add_event(
            user=request.user,
            action="Enregistrement exécution paiement",
            new_value=f"{installment.montant_paye} {installment.devise}",
        )
        return Response(
            LogisticsOrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class LogisticsPaymentValidateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        _ensure_order_active(order)
        if order.statut_paiement != "En attente":
            raise ValidationError(
                {"paiement": _("Aucune demande de paiement n'est en attente.")}
            )
        serializer = LogisticsPaymentValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        installment = _get_locked_installment(order, data["echeance_id"])
        if (
            installment.statut_traitement
            != "Paiement effectué – Justificatif à joindre"
        ):
            raise ValidationError(
                {"paiement": _("Enregistrez d'abord l'exécution du paiement.")}
            )
        old_status = order.statut_paiement
        installment.justificatif_file = data["swift_file"]
        installment.paiement_valide_le = timezone.now()
        installment.paiement_valide_par = request.user
        installment.statut_traitement = "Paiement validé"
        installment.save()
        _clear_payment_installment_cache(order)

        order.swift_file = data["swift_file"]
        order.date_upload_swift = timezone.now()
        remaining_balance = order.solde_restant
        if remaining_balance == 0:
            order.statut_paiement = "Validé"
            order.statut = "Paiement effectué"
            order.statut_banque_paiement = "Exécuté"
            order.statut_traitement_paiement = "Paiement validé"
            order.paiement_valide_le = timezone.now()
            order.paiement_valide_par = request.user
            order.paiement_assigne_a = None
        else:
            order.statut_paiement = "En attente"
            order.statut = "Paiement demandé"
            order.statut_banque_paiement = "Partiel"
            order.statut_traitement_paiement = "Paiement à traiter"
        order.sync_global_status(preserve_manual=False, commit=False)
        order.save()
        order.add_event(
            user=request.user,
            action="Validation paiement",
            old_value=old_status,
            new_value=(
                "Validé"
                if remaining_balance == 0
                else f"Partiel – solde {remaining_balance}"
            ),
        )
        if remaining_balance == 0:
            _notify_logistics_responsible(
                order,
                _(
                    "Le paiement du dossier %(reference)s a été validé par le Service Comptable. Le SWIFT / LC est disponible. Vous pouvez poursuivre le traitement de la commande."
                )
                % {"reference": order.numero_commande},
            )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentRejectView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        _ensure_order_active(order)
        if order.statut_paiement != "En attente":
            raise ValidationError(
                {"paiement": _("Aucune demande de paiement n'est en attente.")}
            )
        serializer = LogisticsPaymentRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if order.echeances_paiement.exclude(
            statut_traitement="Paiement à traiter"
        ).exists():
            raise ValidationError(
                {
                    "paiement": _(
                        "Une échéance déjà commencée ne peut pas être supprimée. Poursuivez son traitement afin de conserver la traçabilité."
                    )
                }
            )
        _invalidate_or_block_active_email_deliveries(
            order,
            reason=_("Envoi annulé car le paiement a été retourné pour correction."),
        )
        old_status = order.statut_paiement
        order.statut_paiement = "Non demandé"
        order.statut_banque_paiement = "Bloqué"
        order.statut_traitement_paiement = "Paiement à traiter"
        order.statut_titre_importation = "À préparer"
        order.date_validation_titre_importation = None
        order.paiement_assigne_a = None
        order.sync_global_status(preserve_manual=False, commit=False)
        order.save(
            update_fields=[
                "statut_paiement",
                "statut_banque_paiement",
                "statut_traitement_paiement",
                "statut_titre_importation",
                "date_validation_titre_importation",
                "paiement_assigne_a",
                "statut_global",
                "date_updated",
            ]
        )
        order.add_event(
            user=request.user,
            action="Blocage paiement",
            old_value=old_status,
            new_value="Bloqué – correction requise",
            note=serializer.validated_data.get("note", ""),
        )
        response_serializer = LogisticsOrderDetailSerializer(
            order, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LogisticsSwiftSentView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _is_order_responsible(request.user, order):
            raise PermissionDenied(
                _("Seul le Responsable Commande peut envoyer la preuve au fournisseur.")
            )
        _ensure_order_active(order)
        action_serializer = LogisticsPaymentInstallmentActionSerializer(
            data=request.data
        )
        action_serializer.is_valid(raise_exception=True)
        installment = _get_locked_installment(
            order, action_serializer.validated_data["echeance_id"]
        )
        if not installment.paiement_valide_le or not installment.justificatif_file:
            raise ValidationError(
                {
                    "swift": _(
                        "Validez le paiement et joignez son justificatif avant l'envoi."
                    )
                }
            )
        if installment.preuve_email_statut == "Envoyé":
            raise ValidationError(
                {"swift": _("La preuve a déjà été envoyée au fournisseur.")}
            )
        supplier_email = (order.fournisseur_email or "").strip()
        if not supplier_email:
            raise ValidationError(
                {
                    "fournisseur_email": _(
                        "Renseignez l'e-mail du fournisseur sur la commande client source avant l'envoi."
                    )
                }
            )
        if installment.preuve_email_statut == "En attente" or (
            installment.preuve_email_statut == "Envoi en cours"
            and not installment.preuve_email_relance_disponible
        ):
            raise ValidationError(
                {"swift": _("L'envoi de la preuve au fournisseur est déjà en cours.")}
            )
        delivery_token = uuid4().hex
        installment.preuve_email_statut = "En attente"
        installment.preuve_email_destinataire = supplier_email
        installment.preuve_email_erreur = ""
        installment.preuve_email_demandee_par = request.user
        installment.preuve_email_task_id = ""
        installment.preuve_email_prise_en_charge_le = None
        installment.preuve_email_file_token = delivery_token
        installment.preuve_email_mise_en_file_le = timezone.now()
        installment.preuve_envoyee_fournisseur_le = None
        installment.save(
            update_fields=[
                "preuve_email_statut",
                "preuve_email_destinataire",
                "preuve_email_erreur",
                "preuve_email_demandee_par",
                "preuve_email_task_id",
                "preuve_email_prise_en_charge_le",
                "preuve_email_file_token",
                "preuve_email_mise_en_file_le",
                "preuve_envoyee_fournisseur_le",
                "date_updated",
            ]
        )
        from .tasks import queue_supplier_payment_proof_email

        transaction.on_commit(
            lambda installment_id=installment.id, token=delivery_token: queue_supplier_payment_proof_email(
                installment_id, token
            )
        )
        _clear_payment_installment_cache(order)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentReceiptConfirmView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = LogisticsOrderDetailEditDeleteView.get_object(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not _is_order_responsible(request.user, order):
            raise PermissionDenied(
                _(
                    "Seul le Responsable Commande peut confirmer la réception de la preuve par le fournisseur."
                )
            )
        _ensure_order_active(order)
        serializer = LogisticsPaymentInstallmentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installment = _get_locked_installment(
            order, serializer.validated_data["echeance_id"]
        )
        if (
            installment.preuve_email_statut != "Envoyé"
            or not installment.preuve_envoyee_fournisseur_le
        ):
            raise ValidationError(
                {"paiement": _("Envoyez d'abord la preuve au fournisseur.")}
            )
        if installment.reception_confirmee_le:
            raise ValidationError(
                {
                    "paiement": _(
                        "La réception de la preuve par le fournisseur est déjà confirmée."
                    )
                }
            )
        installment.reception_confirmee_le = timezone.now()
        installment.reception_confirmee_par = request.user
        installment.save(
            update_fields=[
                "reception_confirmee_le",
                "reception_confirmee_par",
                "date_updated",
            ]
        )
        _clear_payment_installment_cache(order)
        if (
            order.solde_restant == 0
            and not order.echeances_paiement.filter(
                paiement_valide_le__isnull=False,
                reception_confirmee_le__isnull=True,
            ).exists()
        ):
            order.statut_banque_paiement = "Confirmé"
            order.paiement_confirme_reception_le = timezone.now()
            order.paiement_confirme_reception_par = request.user
            order.save(
                update_fields=[
                    "statut_banque_paiement",
                    "paiement_confirme_reception_le",
                    "paiement_confirme_reception_par",
                    "date_updated",
                ]
            )
        order.add_event(
            user=request.user,
            action="Confirmation de la réception de la preuve par le fournisseur",
            new_value=f"Échéance {installment.id}",
        )
        return Response(
            LogisticsOrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


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
    document_name = "dossier logistique"

    def get_queryset_with_related(self, ids):
        return LogisticsOrder.objects.filter(pk__in=ids).select_related("company")

    def get_company_id(self, obj):
        return obj.company_id
