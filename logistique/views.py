from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from core.ordering import apply_list_ordering
from core.pagination import CustomPagination
from core.permissions import (
    can_change_document_status,
    can_delete,
)
from core.views import BaseBulkDeleteView, CompanyAccessMixin
from stock.services import activate_incoming

from .corrections import authorize_step, consume_approval
from .filters import LogisticsOrderFilter
from .historical_services import authorize_historical_edit
from .models import LogisticsOrder, LogisticsPaymentInstallment
from .permissions import (
    can_create_logistics,
    can_manage_logistics,
    can_process_assigned_payment,
    is_order_responsible,
)
from .purchase import payment_blocker, validate_purchase_transition
from .purchase_services import create_purchase_dossier, request_purchase_payment
from .selectors import get_order
from .serializers import (
    LOGISTICS_IMPORT_TITLE_FIELDS,
    LogisticsGlobalStatusSerializer,
    LogisticsLaunchStatusSerializer,
    LogisticsOrderCreateSerializer,
    LogisticsOrderDetailSerializer,
    LogisticsOrderListSerializer,
    LogisticsOrderUpdateSerializer,
    LogisticsPaymentExecutionSerializer,
    LogisticsPaymentInstallmentActionSerializer,
    LogisticsPaymentProofEmailStatusSerializer,
    LogisticsPaymentRejectSerializer,
    LogisticsPaymentRequestSerializer,
    LogisticsPaymentValidationSerializer,
    LogisticsProcessNoteSerializer,
    LogisticsProformaRequestSerializer,
    LogisticsStatusSerializer,
    LogisticsSupplierProformaReviewSerializer,
)
from .services import (
    assign_payment_task,
    build_proforma_source_preview,
    clear_payment_installment_cache,
    create_orders_from_proformas,
    ensure_order_active,
    get_locked_installment,
    invalidate_or_block_active_email_deliveries,
    notify_logistics_responsible,
    send_payment_request_email,
)
from .stats import get_logistics_stats
from .tasks import (
    queue_accounting_payment_email,
    queue_purchase_creator_email,
)
from .utils import get_next_numero_logistique


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
                "marques",
                "proformas",
                "lignes",
                "lignes__client",
                "echeances_paiement",
            )
        )
        filterset = LogisticsOrderFilter(request.GET, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        # Use the same public-column ordering as paginated lists for exports
        # and select-all requests too, including calculated workflow statuses.
        ordered_qs = apply_list_ordering(
            filterset.qs.order_by("-id"), request.query_params
        )
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
        if not can_create_logistics(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer un dossier logistique.")
            )

        if not request.data.get("proformas"):
            orders = create_purchase_dossier(company_id, request.user, request.data)
            return Response(
                {
                    "created": 1,
                    "orders": LogisticsOrderDetailSerializer(
                        orders, many=True, context={"request": request}
                    ).data,
                },
                status=status.HTTP_201_CREATED,
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
    protected_delete_message = _(
        "Ce dossier est lié à une réception de stock. La suppression est bloquée "
        "pour conserver la traçabilité des mouvements de stock."
    )

    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get(self, request, pk, *args, **kwargs):
        order = get_order(pk)
        self._check_company_access(request, order.company_id)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def put(self, request, pk, *args, **kwargs):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if order.is_supplier_purchase:
            if not can_manage_logistics(request.user, order.company_id):
                raise PermissionDenied(
                    "Votre rôle permet uniquement la lecture de ce dossier."
                )
            raise ValidationError(
                {
                    "dossier": "Utilisez les formulaires du dossier fournisseur pour modifier ces informations."
                }
            )
        can_manage = can_manage_logistics(request.user, order.company_id)
        is_responsible = is_order_responsible(request.user, order)
        requested_fields = set(request.data.keys()) - {"etape", "correction_id"}
        if not can_manage and not is_responsible:
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce dossier logistique.")
            )
        if (
            requested_fields & LOGISTICS_IMPORT_TITLE_FIELDS
            and not is_responsible
            and not request.data.get("correction_id")
        ):
            raise PermissionDenied(
                _("Seul le Responsable Commande peut modifier le titre d'importation.")
            )
        if not can_manage and requested_fields - LOGISTICS_IMPORT_TITLE_FIELDS:
            raise PermissionDenied(
                _(
                    "Le Responsable Commande peut uniquement modifier le titre d'importation."
                )
            )
        ensure_order_active(order)
        approval = authorize_historical_edit(order, request)
        if requested_fields & LOGISTICS_IMPORT_TITLE_FIELDS and not (
            is_responsible or approval
        ):
            raise PermissionDenied(
                "Seul le responsable ou le demandeur autorisé peut corriger le titre."
            )
        serializer = LogisticsOrderUpdateSerializer(
            order,
            data=request.data,
            context={"request": request, "approved_correction": bool(approval)},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        consume_approval(instance, approval, request.user)
        instance.sync_global_status(preserve_manual=True)
        response_serializer = LogisticsOrderDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        order = get_order(pk)
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce dossier logistique.")
            )
        ensure_order_active(order)
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
            not order.is_supplier_purchase
            and requested_status in LogisticsOrder.PAYMENT_COMPLETE_REQUIRED_STATUSES
            and not order.is_payment_step_complete
        ):
            raise ValidationError(
                {"statut": _("Validez d'abord la totalité du paiement requis.")}
            )
        if order.is_supplier_purchase:
            step = {"Livraison client": "reception", "Clôture": "couts"}.get(
                requested_status
            )
            if not step:
                raise ValidationError(
                    {"statut": "Utilisez le formulaire de l’étape en cours."}
                )
            authorize_step(order, request, step)
        else:
            authorize_historical_edit(order, request)
        validate_purchase_transition(order, requested_status)
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
        order = get_order(pk, for_update=True)
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
                        "Le statut global est calculé automatiquement. Seuls Annulé "
                        "et Rouvert peuvent être appliqués manuellement."
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
            invalidate_or_block_active_email_deliveries(
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour enregistrer cette demande de pro forma fournisseur."
                )
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            raise ValidationError(
                {"dossier": "Utilisez les actions du dossier d’achat fournisseur."}
            )
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
        activate_incoming(order)
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier cette étape.")
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            raise ValidationError(
                {"dossier": "Utilisez les actions du dossier d’achat fournisseur."}
            )
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
            if requested_status == "Terminée":
                activate_incoming(order)
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                _(
                    "Vous n'avez pas les droits pour contrôler cette pro forma fournisseur."
                )
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            raise ValidationError(
                {"dossier": "Utilisez les actions du dossier d’achat fournisseur."}
            )
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
            "ecart_autre_proforma",
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not is_order_responsible(request.user, order):
            raise PermissionDenied(
                _(
                    "Seul le Responsable Commande peut transmettre ce dossier au Service Comptable."
                )
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            if not can_manage_logistics(request.user, order.company_id):
                raise PermissionDenied(
                    "Votre rôle permet uniquement la lecture du dossier."
                )
            request_purchase_payment(order, request)
            return Response(
                LogisticsOrderDetailSerializer(order, context={"request": request}).data
            )
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
        clear_payment_installment_cache(order)
        assign_payment_task(order)
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not is_order_responsible(request.user, order):
            raise PermissionDenied(
                _("Seul le Responsable Commande peut relancer cet e-mail.")
            )
        ensure_order_active(order)
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
        transaction.on_commit(
            lambda order_id=order.id, token=delivery_token: (
                queue_accounting_payment_email(order_id, token)
            )
        )
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsPaymentStartView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        ensure_order_active(order)
        serializer = LogisticsPaymentInstallmentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installment = get_locked_installment(
            order, serializer.validated_data["echeance_id"]
        )
        if order.is_supplier_purchase:
            reason = payment_blocker(order, installment)
            if not installment.demandee_le or reason:
                raise ValidationError(
                    {
                        "paiement": reason
                        or "Transmettez d’abord cette échéance au comptable."
                    }
                )
        if installment.statut_traitement != "Paiement à traiter":
            raise ValidationError(
                {"paiement": _("Cette échéance n'est plus à traiter.")}
            )
        installment.statut_traitement = "Paiement en cours"
        installment.save(update_fields=["statut_traitement", "date_updated"])
        clear_payment_installment_cache(order)
        order.statut_banque_paiement = "Banque en cours"
        order.statut_traitement_paiement = "Paiement en cours"
        order.save(
            update_fields=[
                "statut_banque_paiement",
                "statut_traitement_paiement",
                "date_updated",
            ]
        )
        payment_history = f"Échéance {installment.id}"
        if order.is_supplier_purchase:
            label = (
                "Avance"
                if installment.declencheur == "advance"
                else "Solde"
                if installment.pourcentage < 100
                else "Paiement"
            )
            percentage = format(installment.pourcentage.normalize(), "f")
            amount = f"{installment.montant_prevu:,.2f}".replace(",", " ").replace(
                ".", ","
            )
            payment_history = f"{label} {percentage} % : {amount} {installment.devise}"
        order.add_event(
            user=request.user,
            action="Démarrage paiement",
            new_value=payment_history,
        )
        return Response(
            LogisticsOrderDetailSerializer(order, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class LogisticsPaymentExecutionView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        ensure_order_active(order)
        execution_data = request.data.copy()
        if order.is_supplier_purchase:
            try:
                due = order.echeances_paiement.get(pk=request.data.get("echeance_id"))
            except (ValueError, TypeError, LogisticsPaymentInstallment.DoesNotExist):
                raise ValidationError({"echeance_id": "Échéance introuvable."})
            execution_data["devise_paiement"] = due.devise
            execution_data["banque_paiement"] = order.banque
            execution_data.setdefault("methode_paiement", due.methode_paiement)
        serializer = LogisticsPaymentExecutionSerializer(data=execution_data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        installment = get_locked_installment(order, data["echeance_id"])
        if order.is_supplier_purchase:
            reason = payment_blocker(order, installment)
            if not installment.demandee_le or reason:
                raise ValidationError(
                    {
                        "paiement": reason
                        or "Transmettez d’abord cette échéance au comptable."
                    }
                )
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
            paid_percentage = (
                installment.pourcentage
                * data["montant_paye"]
                / installment.montant_prevu
            ).quantize(Decimal("0.01"))
            LogisticsPaymentInstallment.objects.create(
                commande=order,
                date_echeance=installment.date_echeance,
                montant_prevu=remaining_installment_amount,
                pourcentage=installment.pourcentage - paid_percentage,
                devise=installment.devise,
                methode_paiement=installment.methode_paiement,
                declencheur=installment.declencheur,
                demandee_le=installment.demandee_le,
            )
            installment.montant_prevu = data["montant_paye"]
            installment.pourcentage = paid_percentage

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
        clear_payment_installment_cache(order)

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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        ensure_order_active(order)
        if order.statut_paiement != "En attente":
            raise ValidationError(
                {"paiement": _("Aucune demande de paiement n'est en attente.")}
            )
        serializer = LogisticsPaymentValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        installment = get_locked_installment(order, data["echeance_id"])
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
        clear_payment_installment_cache(order)

        order.swift_file = data["swift_file"]
        order.date_upload_swift = timezone.now()
        remaining_balance = order.solde_restant
        if remaining_balance == 0:
            order.statut_paiement = "Validé"
            if not order.is_supplier_purchase:
                order.statut = "Paiement effectué"
            order.statut_banque_paiement = "Exécuté"
            order.statut_traitement_paiement = "Paiement validé"
            order.paiement_valide_le = timezone.now()
            order.paiement_valide_par = request.user
            order.paiement_assigne_a = None
        else:
            order.statut_paiement = "En attente"
            if not order.is_supplier_purchase:
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
        if order.is_supplier_purchase:
            transaction.on_commit(
                lambda installment_id=installment.pk: queue_purchase_creator_email(
                    installment_id
                )
            )
        elif remaining_balance == 0:
            notify_logistics_responsible(
                order,
                _(
                    "Le paiement du dossier %(reference)s a été validé par le "
                    "Service Comptable. Le SWIFT / LC est disponible. Vous pouvez "
                    "poursuivre le traitement de la commande."
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not can_process_assigned_payment(request.user, order):
            raise PermissionDenied(
                _(
                    "Ce paiement est réservé à l'utilisateur du Service Comptable affecté."
                )
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            raise ValidationError(
                {
                    "paiement": "Le retour global pour correction est désactivé pour ce dossier fournisseur."
                }
            )
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
                        "Une échéance déjà commencée ne peut pas être supprimée. "
                        "Poursuivez son traitement afin de conserver la traçabilité."
                    )
                }
            )
        invalidate_or_block_active_email_deliveries(
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
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        permitted = (
            is_order_responsible(request.user, order)
            if not order.is_supplier_purchase
            else request.user.is_superuser
            or (
                request.user.pk == order.created_by_user_id
                and can_manage_logistics(request.user, order.company_id)
            )
        )
        if not permitted:
            raise PermissionDenied(
                _("Seul le créateur du dossier peut indiquer si l’e-mail a été envoyé.")
            )
        ensure_order_active(order)
        action_serializer = LogisticsPaymentProofEmailStatusSerializer(
            data=request.data
        )
        action_serializer.is_valid(raise_exception=True)
        installment = get_locked_installment(
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
        email_sent = action_serializer.validated_data["email_envoye"]
        installment.preuve_email_statut = "Envoyé" if email_sent else "Non demandé"
        installment.preuve_email_destinataire = ""
        installment.preuve_email_erreur = ""
        installment.preuve_email_demandee_par = request.user
        installment.preuve_email_task_id = ""
        installment.preuve_email_prise_en_charge_le = None
        installment.preuve_email_file_token = ""
        installment.preuve_email_mise_en_file_le = None
        installment.preuve_envoyee_fournisseur_le = (
            timezone.now() if email_sent else None
        )
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
        order.add_event(
            user=request.user,
            action="Suivi manuel e-mail fournisseur",
            new_value="E-mail envoyé" if email_sent else "E-mail non envoyé",
        )
        clear_payment_installment_cache(order)
        serializer = LogisticsOrderDetailSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogisticsProcessNoteCreateView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not (
            can_manage_logistics(request.user, order.company_id)
            or (
                not order.is_supplier_purchase
                and is_order_responsible(request.user, order)
            )
            or can_process_assigned_payment(request.user, order)
        ):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour ajouter une remarque à ce dossier.")
            )
        ensure_order_active(order)
        if order.is_supplier_purchase and order.statut == "Clôture":
            raise ValidationError({"dossier": "Ce dossier est clôturé."})
        serializer = LogisticsProcessNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.save(
            commande=order,
            statut=order.statut,
            user=request.user,
        )
        order.add_event(
            user=request.user,
            action="Remarque processus",
            new_value=order.statut,
            note=note.remarque,
        )
        return Response(
            LogisticsProcessNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )


class LogisticsPaymentReceiptConfirmView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        if not is_order_responsible(request.user, order):
            raise PermissionDenied(
                _(
                    "Seul le Responsable Commande peut confirmer la réception de la preuve par le fournisseur."
                )
            )
        ensure_order_active(order)
        if order.is_supplier_purchase:
            raise ValidationError(
                {"dossier": "Utilisez les actions du dossier d’achat fournisseur."}
            )
        serializer = LogisticsPaymentInstallmentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        installment = get_locked_installment(
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
        clear_payment_installment_cache(order)
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
    protected_delete_message = _(
        "La suppression est bloquée car au moins un dossier est lié à une réception "
        "de stock. Aucun dossier n’a été supprimé."
    )

    model = LogisticsOrder
    document_name = "dossier logistique"

    def get_queryset_with_related(self, ids):
        return LogisticsOrder.objects.filter(pk__in=ids).select_related("company")

    def get_company_id(self, obj):
        return obj.company_id
