from django.contrib.auth.models import Group
from django.db.models import Count
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from .filters import CompanyFilter
from .models import Company
from .pagination import CompanyPagination
from .serializers import (
    CompanySerializer,
    CompanyDetailSerializer,
    CompanyListSerializer,
    CompanyBasicListSerializer,
)


def _is_admin_for_company(user, company):
    """User has an Admin membership for the given company."""
    return Membership.objects.filter(
        user=user, company=company, role__name="Admin"
    ).exists()


class CompanyListCreateView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def get(request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        queryset = Company.objects.filter(
            memberships__user=request.user,
            memberships__role__name="Admin",
        )
        if pagination:
            paginator = CompanyPagination()
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
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            admin_group = Group.objects.get(name="Admin")
        except Group.DoesNotExist:
            raise PermissionDenied(
                detail="Le groupe 'Admin' n'existe pas. Un super‑utilisateur doit le créer et assigner les rôles."
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

        if not _is_admin_for_company(user, company):
            raise PermissionDenied(
                detail=_("Seuls les Admins de cette société peuvent y accéder.")
            )

        return company

    def get(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        serializer = CompanyDetailSerializer(company, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        serializer = CompanyDetailSerializer(
            company, data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        company.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompaniesByUserView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        queryset = (
            Company.objects.filter(memberships__user=request.user)
            .annotate(_client_count=Count("clients"))
            .order_by("-_client_count")
        )
        serializer = CompanyBasicListSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
