from django.db import transaction
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import CompanyAccessMixin

from .corrections import authorize_step, handle_change_request
from .import_title import extract_import_title
from .permissions import can_manage_logistics
from .purchase import (
    action_step,
)
from .purchase_services import adopt_supplier_workflow, apply_purchase_action
from .selectors import get_order
from .serializers import (
    LogisticsOrderDetailSerializer,
    validate_logistics_document,
)
from .services import ensure_order_active


class PurchaseWorkflowView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    @transaction.atomic
    def post(self, request, pk):
        order = get_order(pk, for_update=True)
        self._check_company_access(request, order.company_id)
        deciding = request.data.get("action") in {
            "approuver_modification",
            "refuser_modification",
        }
        if not can_manage_logistics(request.user, order.company_id) and not (
            deciding and order.responsable_id == request.user.pk
        ):
            raise PermissionDenied(
                "Vous n’avez pas les droits pour modifier ce dossier."
            )
        ensure_order_active(order)
        action = request.data.get("action")
        if action in {
            "demander_modification",
            "approuver_modification",
            "refuser_modification",
        }:
            handle_change_request(order, request, apply_action=apply_purchase_action)
            order = get_order(pk)
            return Response(
                LogisticsOrderDetailSerializer(order, context={"request": request}).data
            )
        if not order.is_supplier_purchase:
            if request.data.get("action") != "adopter_parcours_fournisseur":
                raise ValidationError(
                    {
                        "dossier": "Complétez d’abord les informations du dossier pour utiliser le parcours d’achat fournisseur."
                    }
                )
            adopt_supplier_workflow(order, user=request.user, data=request.data)
            order.sync_global_status(preserve_manual=False)
            order = get_order(pk)
            return Response(
                LogisticsOrderDetailSerializer(order, context={"request": request}).data
            )
        if (
            order.statut == "Clôture"
            and request.data.get("action") != "relancer_notification"
        ):
            raise ValidationError({"dossier": "Ce dossier est clôturé."})
        if set(request.data) == {"action"} and action in {
            "dossier",
            "titre",
            "progression",
        }:
            return Response(
                LogisticsOrderDetailSerializer(order, context={"request": request}).data
            )
        step = action_step(order, request.data)
        approval = authorize_step(order, request, step) if step else None
        order = apply_purchase_action(order, request, approval)
        return Response(
            LogisticsOrderDetailSerializer(order, context={"request": request}).data
        )


class ImportTitleExtractView(CompanyAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, pk):
        order = get_order(pk)
        self._check_company_access(request, order.company_id)
        if not can_manage_logistics(request.user, order.company_id):
            raise PermissionDenied(
                "Vous n’avez pas les droits pour lire ce titre d’importation."
            )
        file = request.FILES.get("file")
        if not file:
            raise ValidationError({"file": "Joignez le titre d’importation."})
        validate_logistics_document(file)
        return Response(extract_import_title(file))
