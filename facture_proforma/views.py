from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from client.models import Client
from facturation_backend.utils import CustomPagination
from .filters import FactureProFormaFilter
from .models import FactureProForma
from .serializers import (
    FactureProformaSerializer,
    FactureProformaDetailSerializer,
    FactureProformaListSerializer,
)
from .utils import get_next_numero_facture_pro_forma


class FactureProFormaListCreateView(APIView):
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
        company_id_str = request.query_params.get("company_id")
        if not company_id_str:
            raise Http404(_("Aucune clients ne correspond à la requête."))
        company_id = int(company_id_str)
        self._check_company_access(request, company_id)
        base_queryset = FactureProForma.objects.filter(client__company_id=company_id)
        filterset = FactureProFormaFilter(request.GET, queryset=base_queryset)
        ordered_qs = filterset.qs.order_by("-id")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(ordered_qs, request)
            serializer = FactureProformaListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        serializer = FactureProformaListSerializer(
            ordered_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        client = request.data.get("client")
        if not client:
            raise PermissionDenied(
                _("Un client doit être spécifié pour la facture proforma.")
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
                    "Vous n'êtes pas autorisé à créer une facture proforma pour cette société."
                )
            )
        serializer = FactureProformaSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by_user=request.user)

        # return detailed representation (includes nested lignes)
        response_serializer = FactureProformaDetailSerializer(
            instance, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class FactureProFormaDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return FactureProForma.objects.get(pk=pk)
        except FactureProForma.DoesNotExist:
            raise Http404(_("Aucun facture proforma ne correspond à la requête."))

    def get(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à consulter cette facture proforma.")
            )
        serializer = FactureProformaDetailSerializer(
            object_, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cette facture proforma.")
            )
        serializer = FactureProformaDetailSerializer(
            object_, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        # preserve original owner (do not allow payload to change it)
        serializer.save(created_by_user=object_.created_by_user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à supprimer cette facture proforma.")
            )
        object_.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateNumeroFactureView(APIView):
    """Return the next available ``numero_facture`` (e.g. ``0001/25``)."""

    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        new_num = get_next_numero_facture_pro_forma()
        return Response({"numero_facture": new_num}, status=status.HTTP_200_OK)


class FactureProFormaStatusUpdateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return FactureProForma.objects.get(pk=pk)
        except FactureProForma.DoesNotExist:
            raise Http404(_("Aucun facture proforma ne correspond à la requête."))

    def patch(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à modifier cette facture proforma.")
            )
        new_status = request.data.get("statut")
        valid_statuses = [choice[0] for choice in FactureProForma.STATUT_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError({"statut": _("Statut invalide.")})
        object_.statut = new_status
        object_.save()
        return Response({"statut": object_.statut}, status=status.HTTP_200_OK)


class FactureProFormaConvertToFactureClientView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def _has_membership(user, company_id):
        return Membership.objects.filter(user=user, company_id=company_id).exists()

    @staticmethod
    def get_object(pk):
        try:
            return FactureProForma.objects.get(pk=pk)
        except FactureProForma.DoesNotExist:
            raise Http404(_("Aucun facture pro-forma ne correspond à la requête."))

    def post(self, request, pk, *args, **kwargs):
        object_ = self.get_object(pk)
        if not self._has_membership(request.user, object_.client.company_id):
            raise PermissionDenied(
                _("Vous n'êtes pas autorisé à convertir cette facture pro-forma.")
            )
        numero_facture = get_next_numero_facture_pro_forma()
        facture = object_.convert_to_facture_client(
            numero_facture=numero_facture,
            created_by_user=request.user,
        )
        return Response(
            {"facture_client_id": facture.id},
            status=status.HTTP_201_CREATED,
        )
