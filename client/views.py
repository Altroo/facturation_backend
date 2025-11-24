from re import search

from django.db.models import Max
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from .filters import ClientFilter
from .models import Client
from .pagination import ClientPagination
from .serializers import (
    ClientSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
)


class ClientListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _user_company_ids(user):
        """Return a queryset of company IDs the user is member of."""
        return Membership.objects.filter(user=user).values_list("company_id", flat=True)

    def get(self, request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        archived = request.query_params.get("archived", "false").lower() == "true"
        member_company_ids = list(self._user_company_ids(request.user))
        # Require company_id from query params
        company_id = request.query_params.get("company_id")
        if not company_id:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        # Ensure user has access to that company
        if int(company_id) not in member_company_ids:
            raise PermissionDenied(
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )
        # Only clients of that company
        base_queryset = Client.objects.filter(company_id=company_id, archived=archived)
        # Apply filters (archived, search, etc.)
        filterset = ClientFilter(request.GET, queryset=base_queryset)
        filtered_queryset = filterset.qs
        if pagination:
            paginator = ClientPagination()
            ordered_qs = filtered_queryset.order_by("-id")
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = ClientListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ClientListSerializer(filtered_queryset.order_by("-id"), many=True)
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
        serializer = ClientDetailSerializer(client, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à supprimer ce client."))
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        if not self._has_membership(request.user, client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à modifier ce client."))
        # reuse the same logic as ArchiveToggleClientView for partial updates
        serializer = ClientDetailSerializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class GenerateClientCodeView(APIView):
    """Return the next available ``code_client`` (e.g. ``CLT0018``)."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        # Find the highest numeric part of existing codes
        max_code = (
            Client.objects.annotate(num=Max("code_client")).aggregate(
                max_num=Max("code_client")
            )
        )["max_num"]

        # Extract the numeric suffix; default to 0 if none exist
        match = search(r"CLT(\d+)", max_code or "")
        next_number = int(match.group(1)) + 1 if match else 1

        # Build the new code with leading zeros (4 digits)
        new_code = f"CLT{next_number:04d}"
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
