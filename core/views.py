import logging

from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status

logger = logging.getLogger(__name__)
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from client.models import Client
from core.permissions import can_create, can_update, can_delete
from facturation_backend.utils import CustomPagination


class CompanyAccessMixin:
    """Shared mixin providing company access checks for all views."""

    @staticmethod
    def _check_company_access(request, company_id: int) -> None:
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                detail=_("Vous n'avez pas accès à cette société.")
            )

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _parse_company_id(company_id_str, error_message=None):
        """Parse and validate company_id from query params."""
        if not company_id_str:
            raise Http404(_(error_message or "company_id est requis."))
        try:
            return int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError({"company_id": _("company_id doit être un entier valide.")})


class BaseDocumentListCreateView(CompanyAccessMixin, APIView):
    """Base view for listing and creating documents (Devi, FactureProforma, FactureClient)."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    filter_class = None
    list_serializer_class = None
    create_serializer_class = None
    detail_serializer_class = None
    document_name = "document"
    # FK fields to select_related on list queries (override in subclasses to extend)
    list_select_related = ("client", "mode_paiement", "created_by_user")
    # Reverse FK fields to prefetch on list queries
    list_prefetch_related = ("lignes",)

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError({"company_id": _("company_id doit être un entier valide.")})
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
                _("Un client doit être spécifié pour %(name)s.") % {"name": self.document_name}
            )
        try:
            client_obj = Client.objects.get(pk=client)
        except Client.DoesNotExist:
            raise Http404(_("Client introuvable."))
        if not Membership.objects.filter(
            user=request.user, company_id=client_obj.company_id
        ).exists():
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer %(name)s pour cette société.") % {"name": self.document_name}
            )

        # Check if user has created permission
        if not can_create(request.user, client_obj.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour créer ce %(name)s.") % {"name": self.document_name}
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


class BaseDocumentDetailEditDeleteView(CompanyAccessMixin, APIView):
    """Base view for retrieving, updating and deleting documents."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    detail_serializer_class = None
    document_name = "document"

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_("Aucun %(name)s ne correspond à la requête.") % {"name": self.document_name})

    def get(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à consulter ce %(name)s.") % {"name": self.document_name}
            )
        serializer = self.detail_serializer_class(object_, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce %(name)s.") % {"name": self.document_name}
            )

        # Check if user has update permission
        if not can_update(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce %(name)s.") % {"name": self.document_name}
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
                _("Vous n'êtes pas autorisé à supprimer ce %(name)s.") % {"name": self.document_name}
            )

        # Check if user has deleted permission
        if not can_delete(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour supprimer ce %(name)s.") % {"name": self.document_name}
            )

        object_.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BaseGenerateNumeroView(CompanyAccessMixin, APIView):
    """Base view for generating document numbers."""

    permission_classes = (permissions.IsAuthenticated,)
    numero_generator = None
    response_key = "numero"

    def get(self, request, *args, **kwargs):
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("company_id manquant dans les paramètres."))
        try:
            company_id = int(company_id_str)
        except (ValueError, TypeError):
            raise ValidationError({"company_id": _("company_id doit être un entier valide.")})

        # Check if user has access to this company
        if not self._has_membership(request.user, company_id):
            raise PermissionDenied(
                _("Vous n'avez pas accès à cette société.")
            )

        # Call the generator function directly, not as a bound method
        new_num = self.__class__.numero_generator(company_id)
        return Response({self.response_key: new_num}, status=status.HTTP_200_OK)


class BaseStatusUpdateView(CompanyAccessMixin, APIView):
    """Base view for updating document status."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_("Aucun %(name)s ne correspond à la requête.") % {"name": self.document_name})

    def patch(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier ce %(name)s.") % {"name": self.document_name}
            )

        # Check if user has update permission
        if not can_update(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour modifier ce %(name)s.") % {"name": self.document_name}
            )

        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in self.model.STATUT_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})

        object_.statut = new_status
        object_.save()
        return Response({"statut": object_.statut}, status=status.HTTP_200_OK)


class BaseConversionView(CompanyAccessMixin, APIView):
    """Base view for converting documents."""

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"
    numero_generator = None
    conversion_method = None
    numero_param_name = "numero_facture"  # Default for most conversions

    def get_object(self, pk):
        try:
            return self.model.objects.get(pk=pk)
        except self.model.DoesNotExist:
            raise Http404(_("Aucun %(name)s ne correspond à la requête.") % {"name": self.document_name})

    def post(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)

        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à convertir ce %(name)s.") % {"name": self.document_name}
            )

        # Check if user has created permission for conversions
        if not can_create(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'avez pas les droits pour convertir ce %(name)s.") % {"name": self.document_name}
            )

        # Validate conversion method exists
        if not hasattr(object_, self.conversion_method):
            raise ValidationError(
                _("La méthode de conversion %(method)s n'existe pas.") % {"method": self.conversion_method}
            )

        # Validate source document has lines
        if not object_.get_lines().exists():
            raise ValidationError(
                _("Impossible de convertir un %(name)s sans lignes.") % {"name": self.document_name}
            )

        # Validate source document status
        if object_.statut not in ["Envoyé", "Accepté"]:
            raise ValidationError(
                _("Impossible de convertir un %(name)s avec le statut '%(statut)s'.") % {
                    "name": self.document_name,
                    "statut": object_.statut,
                }
            )

        try:
            numero = self.numero_generator(object_.client.company_id)
            conversion_func = getattr(object_, self.conversion_method)
            converted = conversion_func(
                **{self.numero_param_name: numero},
                created_by_user=request.user,
            )
            return Response({"id": converted.id}, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error("Échec de la conversion pour %s %s: %s", self.document_name, pk, e)
            raise ValidationError(
                _("Échec de la conversion: %(error)s") % {"error": str(e)}
            )


class BaseBulkDeleteView(CompanyAccessMixin, APIView):
    """Base view for bulk-deleting documents by a list of IDs.

    Subclasses must define:
        model              – the Django model class
        document_name      – human-readable name (used in error messages)

    Subclasses must implement:
        get_queryset_with_related(ids)  – returns a queryset pre-fetched for
                                          get_company_id lookups
        get_company_id(obj)             – returns the company_id for one object
    """

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"

    def get_queryset_with_related(self, ids):  # pragma: no cover
        raise NotImplementedError

    def get_company_id(self, obj):  # pragma: no cover
        raise NotImplementedError

    def delete(self, request, *args, **kwargs):
        ids = request.data.get("ids")
        if not ids or not isinstance(ids, list):
            raise ValidationError({"ids": _("Une liste d'identifiants est requise.")})

        ids = [int(i) for i in ids]
        objects = list(self.get_queryset_with_related(ids))
        if len(objects) != len(ids):
            raise Http404(
                _("Certains %(name)s sont introuvables.") % {"name": self.document_name}
            )

        from django.db import transaction
        with transaction.atomic():
            for obj in objects:
                company_id = self.get_company_id(obj)
                if not self._has_membership(request.user, company_id):
                    raise PermissionDenied(
                        _("Vous n'êtes pas autorisé à supprimer ce %(name)s.")
                        % {"name": self.document_name}
                    )
                if not can_delete(request.user, company_id):
                    raise PermissionDenied(
                        _("Vous n'avez pas les droits pour supprimer ce %(name)s.")
                        % {"name": self.document_name}
                    )
            self.model.objects.filter(pk__in=ids).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class BaseBulkArchiveView(CompanyAccessMixin, APIView):
    """Base view for bulk-archiving / unarchiving objects by a list of IDs.

    Subclasses must define:
        model              – the Django model class (must have an ``archived`` field)
        document_name      – human-readable name

    Subclasses must implement:
        get_queryset_with_related(ids)  – returns a queryset pre-fetched for
                                          get_company_id lookups
        get_company_id(obj)             – returns the company_id for one object
    """

    permission_classes = (permissions.IsAuthenticated,)
    model = None
    document_name = "document"

    def get_queryset_with_related(self, ids):  # pragma: no cover
        raise NotImplementedError

    def get_company_id(self, obj):  # pragma: no cover
        raise NotImplementedError

    def patch(self, request, *args, **kwargs):
        ids = request.data.get("ids")
        archived = request.data.get("archived")
        if not ids or not isinstance(ids, list):
            raise ValidationError({"ids": _("Une liste d'identifiants est requise.")})
        if archived is None or not isinstance(archived, bool):
            raise ValidationError({"archived": _("Le champ 'archived' (booléen) est requis.")})

        ids = [int(i) for i in ids]
        objects = list(self.get_queryset_with_related(ids))
        if len(objects) != len(ids):
            raise Http404(
                _("Certains %(name)s sont introuvables.") % {"name": self.document_name}
            )

        from django.db import transaction
        with transaction.atomic():
            for obj in objects:
                company_id = self.get_company_id(obj)
                if not self._has_membership(request.user, company_id):
                    raise PermissionDenied(
                        _("Vous n'êtes pas autorisé à modifier ce %(name)s.")
                        % {"name": self.document_name}
                    )
                if not can_update(request.user, company_id):
                    raise PermissionDenied(
                        _("Vous n'avez pas les droits pour modifier ce %(name)s.")
                        % {"name": self.document_name}
                    )
            self.model.objects.filter(pk__in=ids).update(archived=archived)

        return Response({"updated": len(ids)}, status=status.HTTP_200_OK)
