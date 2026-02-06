from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from client.models import Client
from core.permissions import can_create, can_update, can_delete
from facturation_backend.utils import CustomPagination


class BaseDocumentListCreateView(APIView):
    """Base view for listing and creating documents (Devi, FactureProforma, FactureClient)."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    filter_class = None
    list_serializer_class = None
    create_serializer_class = None
    detail_serializer_class = None
    document_name = "document"

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
                detail=_("Seuls les Caissiers de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)
        base_queryset = self.model.objects.filter(client__company_id=company_id)
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
        client = request.data.get("client")
        if not client:
            raise PermissionDenied(
                _(f"Un client doit être spécifié pour {self.document_name}.")
            )
        try:
            client_obj = Client.objects.get(pk=client)
        except Client.DoesNotExist:
            raise Http404(_("Client introuvable."))
        if not Membership.objects.filter(
            user=request.user, company_id=client_obj.company_id
        ).exists():
            raise PermissionDenied(
                _(
                    f"Vous n'êtes pas autorisé à créer {self.document_name} pour cette société."
                )
            )

        # Check if user has created permission
        if not can_create(request.user, client_obj.company_id):
            raise PermissionDenied(
                _(f"Vous n'avez pas les droits pour créer ce {self.document_name}.")
            )

        serializer = self.create_serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by_user=request.user)
        response_serializer = self.detail_serializer_class(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class BaseDocumentDetailEditDeleteView(APIView):
    """Base view for retrieving, updating and deleting documents."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    detail_serializer_class = None
    document_name = "document"

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_(f"Aucun {self.document_name} ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'êtes pas autorisé à consulter ce {self.document_name}.")
            )
        serializer = self.detail_serializer_class(object_, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'êtes pas autorisé à modifier ce {self.document_name}.")
            )

        # Check if user has update permission
        if not can_update(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'avez pas les droits pour modifier ce {self.document_name}.")
            )

        serializer = self.detail_serializer_class(
            object_, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by_user=object_.created_by_user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'êtes pas autorisé à supprimer ce {self.document_name}.")
            )

        # Check if user has deleted permission
        if not can_delete(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'avez pas les droits pour supprimer ce {self.document_name}.")
            )

        object_.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BaseGenerateNumeroView(APIView):
    """Base view for generating document numbers."""

    permission_classes = (permissions.IsAuthenticated,)
    numero_generator = None
    response_key = "numero"

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def get(self, request, *args, **kwargs):
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("company_id manquant dans les paramètres."))
        company_id = int(company_id_str)

        # Check if user has access to this company
        if not self._has_membership(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas accès à cette société.")
            )

        new_num = self.numero_generator(company_id)
        return Response({self.response_key: new_num}, status=status.HTTP_200_OK)


class BaseStatusUpdateView(APIView):
    """Base view for updating document status."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_(f"Aucun {self.document_name} ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'êtes pas autorisé à modifier ce {self.document_name}.")
            )

        # Check if user has update permission
        if not can_update(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'avez pas les droits pour modifier ce {self.document_name}.")
            )

        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in self.model.STATUT_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})
        object_.statut = new_status
        object_.save()
        return Response({"statut": object_.statut}, status=status.HTTP_200_OK)


class BaseConversionView(APIView):
    """Base view for converting documents."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"
    numero_generator = None
    conversion_method = None
    numero_param_name = "numero_facture"  # Default for most conversions

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_(f"Aucun {self.document_name} ne correspond à la requête."))

    def post(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)

        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'êtes pas autorisé à convertir ce {self.document_name}.")
            )

        # Check if user has created permission for conversions
        if not can_create(request.user, object_.client.company_id):
            raise PermissionDenied(
                _(f"Vous n'avez pas les droits pour convertir ce {self.document_name}.")
            )

        # Validate conversion method exists
        if not hasattr(object_, self.conversion_method):
            raise ValidationError(
                _(f"La méthode de conversion {self.conversion_method} n'existe pas.")
            )

        # Validate source document has lines
        if not object_.get_lines().exists():
            raise ValidationError(
                _(f"Impossible de convertir un {self.document_name} sans lignes.")
            )

        # Validate source document status
        if object_.statut not in ["Envoyé", "Accepté"]:
            raise ValidationError(
                _(
                    f"Impossible de convertir un {self.document_name} avec le statut '{object_.statut}'."
                )
            )

        try:
            numero = self.numero_generator()
            conversion_func = getattr(object_, self.conversion_method)
            converted = conversion_func(
                **{self.numero_param_name: numero},
                created_by_user=request.user,
            )
            return Response({"id": converted.id}, status=status.HTTP_201_CREATED)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Échec de la conversion pour {self.document_name} {pk}: {e}")
            raise ValidationError(_(f"Échec de la conversion: {str(e)}"))
