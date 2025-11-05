from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from .filters import CompanyFilter
from .models import Company
from .serializers import CompanySerializer


def _is_admin(user):
    """Check if user has Admin role in any company."""
    return Membership.objects.filter(user=user, role="Admin").exists()


class CompanyListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        paginator = PageNumberPagination()
        paginator.page_size = 10

        if _is_admin(request.user):
            # Admin sees companies they manage
            queryset = Company.objects.filter(managed_by=request.user)
        else:
            company_ids = Membership.objects.filter(user=request.user).values_list(
                "company_id", flat=True
            )
            queryset = Company.objects.filter(id__in=company_ids)

        # Apply global search filter
        filterset = CompanyFilter(request.GET, queryset=queryset)
        queryset = filterset.qs.order_by("-id")

        page = paginator.paginate_queryset(queryset, request)
        serializer = CompanySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @staticmethod
    def post(request, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied(
                detail="Seuls les Admins peuvent créer des sociétés."
            )

        # Prevent client from setting `managed_by`
        data = request.data.copy()
        data.pop("managed_by", None)

        serializer = CompanySerializer(data=data)
        if serializer.is_valid():
            company = serializer.save()
            # Add the requesting user as a manager
            company.managed_by.add(request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CompanyDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_object(self, pk):
        user = self.request.user
        if _is_admin(user):
            # Admin can only access companies they manage
            company = get_object_or_404(Company, pk=pk, managed_by=user)
        else:
            # Finance/Lecture can only access companies they're assigned to
            company = get_object_or_404(Company, pk=pk, memberships__user=user)
        return company

    def get(self, request, pk, *args, **kwargs):
        company = self.get_object(pk)
        serializer = CompanySerializer(company)
        return Response(serializer.data)

    def put(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied(
                detail="Seuls les Admins peuvent mettre à jour les sociétés."
            )

        company = self.get_object(pk)
        serializer = CompanySerializer(company, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied(
                detail="Seuls les Admins peuvent supprimer les sociétés."
            )

        company = self.get_object(pk)
        company.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
