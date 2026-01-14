from re import search

from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from core.permissions import can_create, can_delete, can_update
from core.utils import format_number_with_dynamic_digits
from facturation_backend.utils import CustomPagination
from .filters import ClientFilter
from .models import Client
from .serializers import (
    ClientSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
)


class ClientListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        """Parse boolean query param safely."""
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _check_company_access(request, company_id: int) -> None:
        """Raise PermissionDenied if user lacks membership for company."""
        if not Membership.objects.filter(
            user=request.user, company_id=company_id
        ).exists():
            raise PermissionDenied(
                detail=_("Seuls les Caissiers de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        archived = self._get_bool_param(request, "archived")
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)
        base_queryset = Client.objects.filter(company_id=company_id, archived=archived)
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


class ClientDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        """True if the user has a Membership for the given company."""
        return Membership.objects.filter(user=user, company_id=company_id).exists()

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


class GenerateClientCodeView(APIView):
    """Return the next available ``code_client`` (e.g. ``CLT0018``).
    Automatically increases digit count when 9999 is reached."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):

        # Robustly scan all existing codes and extract numeric parts.
        max_num = 0
        for code in Client.objects.filter(code_client__isnull=False).values_list(
            "code_client", flat=True
        ):
            match = search(r"CLT(\d+)", code)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if value > max_num:
                max_num = value

        next_number = max_num + 1
        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
        new_code = f"CLT{formatted_number}"
        return Response({"code_client": new_code}, status=status.HTTP_200_OK)


class ArchiveToggleClientView(APIView):
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

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

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
