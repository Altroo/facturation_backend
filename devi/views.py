from datetime import datetime
from re import search

from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from client.models import Client
from facturation_backend.utils import CustomPagination
from .filters import DeviFilter
from .models import Devi
from .serializers import (
    DeviSerializer,
    DeviDetailSerializer,
    DeviListSerializer,
)


class DeviListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

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
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        client_id_str = request.query_params.get("client_id")
        if not client_id_str:
            raise Http404(_("Aucun client n'a été spécifié."))
        try:
            client = Client.objects.get(pk=int(client_id_str))
        except Client.DoesNotExist:
            raise Http404(_("Client introuvable."))
        company_id = client.company_id
        self._check_company_access(request, company_id)
        base_queryset = Devi.objects.filter(client=client)
        filterset = DeviFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = DeviListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        serializer = DeviListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        client = request.data.get("client")
        if not client:
            raise PermissionDenied(_("Un client doit être spécifié pour le devis."))
        try:
            client_obj = Client.objects.get(pk=client)
        except Client.DoesNotExist:
            raise Http404(_("Client introuvable."))
        if not Membership.objects.filter(
            user=request.user, company_id=client_obj.company_id
        ).exists():
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à créer un devis pour cette société.")
            )
        serializer = DeviSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by_user=request.user)

        # return detailed representation (includes nested lignes)
        response_serializer = DeviDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DeviDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Devi.objects.get(pk=pk)
        except Devi.DoesNotExist:
            raise Http404(_("Aucun devis ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        devi = self.get_object(pk)
        if not self._has_membership(request.user, devi.client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à consulter ce devis."))
        serializer = DeviDetailSerializer(devi, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        devi = self.get_object(pk)
        if not self._has_membership(request.user, devi.client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à modifier ce devis."))
        serializer = DeviDetailSerializer(
            devi, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        # preserve original owner (do not allow payload to change it)
        serializer.save(created_by_user=devi.created_by_user)
        # serializer.data contains detailed 'lignes' via DeviDetailSerializer.to_representation
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        devi = self.get_object(pk)
        if not self._has_membership(request.user, devi.client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à supprimer ce devis."))
        devi.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateNumeroDevisView(APIView):
    """Return the next available ``numero_devis`` (e.g. ``0001/25``)."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        # use two-digit year suffix, zero-padded
        year_suffix = f"{datetime.now().year % 100:02d}"

        # only scan entries for the current year to reset numbering each year
        qs = Devi.objects.filter(
            numero_devis__isnull=False, numero_devis__endswith=f"/{year_suffix}"
        )

        max_num = 0
        for raw in qs.values_list("numero_devis", flat=True):
            if not raw:
                continue
            m = search(r"^(\d{4})/\d{2}$", raw)
            if not m:
                # skip malformed entries
                continue
            try:
                value = int(m.group(1))
            except ValueError:
                continue
            if value > max_num:
                max_num = value

        next_number = max_num + 1
        new_num = f"{next_number:04d}/{year_suffix}"
        return Response({"numero_devis": new_num}, status=status.HTTP_200_OK)


class DeviStatusUpdateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return Devi.objects.get(pk=pk)
        except Devi.DoesNotExist:
            raise Http404(_("Aucun devis ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        devi = self.get_object(pk)
        if not self._has_membership(request.user, devi.client.company_id):
            raise PermissionDenied(_("Vous n'êtes pas autorisé à modifier ce devis."))
        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in Devi.STATUT_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})
        devi.statut = new_status
        devi.save()
        return Response({"statut": devi.statut}, status=status.HTTP_200_OK)
