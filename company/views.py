from django.contrib.auth.models import Group
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
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
)


def _is_admin(user):
    """User has an Admin membership for any company."""
    return Membership.objects.filter(user=user, role__name="Admin").exists()


def _is_admin_for_company(user, company):
    """User has an Admin membership for the given company."""
    return Membership.objects.filter(
        user=user, company=company, role__name="Admin"
    ).exists()


class CompanyListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        paginator = CompanyPagination()
        paginator.page_size = 10

        # Only companies where the user is an Admin member
        queryset = Company.objects.filter(
            memberships__user=request.user,
            memberships__role__name="Admin",
        )

        filterset = CompanyFilter(request.GET, queryset=queryset)
        queryset = filterset.qs.order_by("-id")

        page = paginator.paginate_queryset(queryset, request)
        serializer = CompanyListSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @staticmethod
    def post(request, *args, **kwargs):
        # User must be an admin somewhere to create a new company
        if not _is_admin(request.user):
            raise PermissionDenied(
                detail="Seuls les Admins peuvent créer des sociétés."
            )

        data = request.data.copy()
        data.pop("managed_by", None)  # safety, field no longer exists

        serializer = CompanySerializer(data=data)
        if not serializer.is_valid():
            raise ValidationError(serializer.errors)

        # Ensure the Admin group exists
        try:
            admin_group = Group.objects.get(name="Admin")
        except Group.DoesNotExist:
            raise PermissionDenied(
                detail="Le groupe 'Admin' n'existe pas. Un super‑utilisateur doit le créer et assigner les rôles."
            )

        company = serializer.save()
        # Record the creator as an Admin member of the new company
        Membership.objects.create(
            company=company,
            user=request.user,
            role=admin_group,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    permission_classes = (IsAuthenticated,)

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
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)

    def delete(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        company.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
