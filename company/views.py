from account.models import Role
from django.db.models import Count
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from facturation_backend.utils import CustomPagination
from .filters import CompanyFilter
from .models import Company
from .serializers import (
    CompanySerializer,
    CompanyDetailSerializer,
    CompanyListSerializer,
    CompanyBasicListSerializer,
)


def _is_admin_for_company(user, company):
    """Check if user has admin (isAdmin=True) membership for the company."""
    return Membership.objects.filter(
        user=user, company=company, role__is_admin=True
    ).exists()


class CompanyListCreateView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def get(request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        # Only show companies where user has isAdmin membership
        queryset = Company.objects.filter(
            memberships__user=request.user,
            memberships__role__is_admin=True,
            suspended=False,
        )
        if pagination:
            paginator = CustomPagination()
            filterset = CompanyFilter(request.GET, queryset=queryset)
            queryset = filterset.qs.order_by("-id")
            page = paginator.paginate_queryset(queryset, request)
            serializer = CompanyListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        else:
            serializer = CompanyListSerializer(
                queryset, many=True, context={"request": request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

    @staticmethod
    def post(request, *args, **kwargs):
        # Check if user is trying to create a company with a non-Caissier role
        # We need to verify if they already have memberships and what role
        existing_memberships = Membership.objects.filter(user=request.user)
        if existing_memberships.exists():
            # Check if any membership is Commercial or other restricted role
            for membership in existing_memberships:
                if membership.role.name in ["Commercial", "Lecture", "Comptable"]:
                    raise PermissionDenied(
                        detail="Vous n'avez pas les droits pour créer une société."
                    )

        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            admin_group = Role.objects.get(name="Caissier")
        except Role.DoesNotExist:
            raise PermissionDenied(
                detail="Le groupe 'Caissier' n'existe pas. Un super‑utilisateur doit le créer et assigner les rôles."
            )

        company = serializer.save()
        Membership.objects.create(
            company=company,
            user=request.user,
            role=admin_group,
        )

        managed_by = request.data.get("managed_by")
        if managed_by:
            CompanyDetailSerializer.update_memberships(company, managed_by)

        response_serializer = CompanyDetailSerializer(
            company, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CompanyDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get_object(self, pk):
        user = self.request.user
        try:
            company = Company.objects.get(pk=pk)
        except Company.DoesNotExist:
            raise Http404(_("Aucune entreprise ne correspond à la requête."))

        # Check if user has isAdmin membership for this company
        if not _is_admin_for_company(user, company):
            raise PermissionDenied(
                detail=_("Seuls les administrateurs peuvent accéder à cette société.")
            )

        return company

    def get(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        serializer = CompanyDetailSerializer(company, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        from core.permissions import can_update

        company = self.get_object(pk)

        # Check if user has update permission
        if not can_update(request.user, company.id):
            raise PermissionDenied(
                detail=_("Vous n'avez pas les droits pour modifier cette société.")
            )

        serializer = CompanyDetailSerializer(
            company, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        from core.permissions import can_delete

        company = self.get_object(pk)

        # Check if user has deleted permission
        if not can_delete(request.user, company.id):
            raise PermissionDenied(
                detail=_("Vous n'avez pas les droits pour supprimer cette société.")
            )

        # Suspend the company instead of deleting
        company.suspended = True
        company.save(update_fields=["suspended"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompaniesByUserView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        queryset = (
            Company.objects.filter(memberships__user=request.user, suspended=False)
            .annotate(_client_count=Count("clients"))
            .order_by("-_client_count")
        )
        serializer = CompanyBasicListSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
