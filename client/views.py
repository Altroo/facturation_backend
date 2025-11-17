from re import search

from django.db.models import Max
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import ClientFilter
from .models import Client
from .pagination import ClientPagination
from .serializers import ClientSerializer, ClientDetailSerializer, ClientListSerializer


class ClientListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        queryset = Client.objects.all()
        if pagination:
            paginator = ClientPagination()
            filterset = ClientFilter(request.GET, queryset=queryset)
            queryset = filterset.qs.order_by("-id")
            page = paginator.paginate_queryset(queryset, request)
            serializer = ClientListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ClientListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        serializer = ClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ClientDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get_object(pk):
        try:
            return Client.objects.get(pk=pk)
        except Client.DoesNotExist:
            raise Http404(_("Aucun client ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        serializer = ClientDetailSerializer(client)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        serializer = ClientDetailSerializer(client, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    def patch(self, request, pk, *args, **kwargs):
        client = self.get_object(pk)

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
