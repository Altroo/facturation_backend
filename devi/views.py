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
from .filters import DeviFilter, DeviLineFilter
from .models import Devi, DeviLine
from .serializers import (
    DeviSerializer,
    DeviDetailSerializer,
    DeviListSerializer,
    DeviLineSerializer,
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


class DeviLineListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _get_bool_param(request, param: str, default: bool = False) -> bool:
        val = request.query_params.get(param, str(default).lower())
        return val.lower() == "true"

    @staticmethod
    def _check_membership(user, company_id: int) -> None:
        if not Membership.objects.filter(user=user, company_id=company_id).exists():
            raise PermissionDenied(
                "Seuls les membres de cette société peuvent accéder à ces lignes."
            )

    def get(self, request, *args, **kwargs):
        pagination = self._get_bool_param(request, "pagination")
        devis_id = request.query_params.get("devis_id")
        if not devis_id:
            raise Http404("Aucun devis n'a été spécifié.")
        try:
            devis = Devi.objects.get(pk=int(devis_id))
        except Devi.DoesNotExist:
            raise Http404("Devis introuvable.")
        self._check_membership(request.user, devis.client.company_id)
        base_queryset = DeviLine.objects.filter(devis=devis)
        filterset = DeviLineFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = DeviLineSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        serializer = DeviLineSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        devis_id = request.data.get("devis")
        if not devis_id:
            raise ValidationError({"devis": "Un devis doit être spécifié."})
        try:
            devis = Devi.objects.get(pk=devis_id)
        except Devi.DoesNotExist:
            raise Http404("Devis introuvable.")
        self._check_membership(request.user, devis.client.company_id)
        serializer = DeviLineSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DeviLineDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get_object(pk):
        try:
            return DeviLine.objects.get(pk=pk)
        except DeviLine.DoesNotExist:
            raise Http404("Ligne de devis introuvable.")

    @staticmethod
    def _has_membership(user, line):
        return Membership.objects.filter(
            user=user, company_id=line.devis.client.company_id
        ).exists()

    def get(self, request, pk, *args, **kwargs):
        line = self.get_object(pk)
        if not self._has_membership(request.user, line):
            raise PermissionDenied(
                "Vous n'êtes pas autorisé à consulter cette ligne de devis."
            )
        serializer = DeviLineSerializer(line, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        line = self.get_object(pk)
        if not self._has_membership(request.user, line):
            raise PermissionDenied(
                "Vous n'êtes pas autorisé à modifier cette ligne de devis."
            )
        serializer = DeviLineSerializer(
            line, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk, *args, **kwargs):
        line = self.get_object(pk)
        if not self._has_membership(request.user, line):
            raise PermissionDenied(
                "Vous n'êtes pas autorisé à modifier cette ligne de devis."
            )
        serializer = DeviLineSerializer(
            line, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        line = self.get_object(pk)
        if not self._has_membership(request.user, line):
            raise PermissionDenied(
                "Vous n'êtes pas autorisé à supprimer ce ligne de devis."
            )
        line.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateNumeroDevisView(APIView):
    """Return the next available ``numero_devis`` (e.g. ``0001/25``)."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        year_suffix = f"{datetime.now().year % 100:02d}"

        # Get all numbers for this year
        qs = Devi.objects.filter(
            numero_devis__isnull=False, numero_devis__endswith=f"/{year_suffix}"
        ).values_list("numero_devis", flat=True)

        used_numbers = []
        for raw in qs:
            m = search(r"^(\d{4})/\d{2}$", raw or "")
            if m:
                try:
                    used_numbers.append(int(m.group(1)))
                except ValueError:
                    continue

        used_numbers = sorted(set(used_numbers))

        # Find first gap
        next_number = None
        for i in range(1, (max(used_numbers) if used_numbers else 0) + 2):
            if i not in used_numbers:
                next_number = i
                break

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
