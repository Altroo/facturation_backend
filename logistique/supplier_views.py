from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce, Lower
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import can_delete
from core.views import CompanyAccessMixin
from facturation_backend.utils import CustomPagination
from parameter.models import Marque
from .filters import LogisticsSupplierFilter
from .models import LogisticsSupplier


class LogisticsSupplierSerializer(serializers.ModelSerializer):
    marques = serializers.PrimaryKeyRelatedField(many=True, queryset=Marque.objects.all(), required=False)
    marques_names = serializers.SlugRelatedField(source="marques", many=True, read_only=True, slug_field="nom")
    total_dossiers = serializers.IntegerField(read_only=True, default=0)
    derniere_activite = serializers.DateTimeField(read_only=True)
    # Existing clients can still display the directory while the frontend deploys.
    fournisseur = serializers.CharField(source="nom", read_only=True)
    fournisseur_email = serializers.CharField(source="email", read_only=True)

    class Meta:
        model = LogisticsSupplier
        fields = [
            "id",
            "company",
            "nom",
            "email",
            "marques",
            "marques_names",
            "total_dossiers",
            "derniere_activite",
            "date_created",
            "date_updated",
            "fournisseur",
            "fournisseur_email",
        ]
        read_only_fields = ["company", "date_created", "date_updated"]
        validators = []

    def validate_marques(self, values):
        if any(brand.company_id != self.context["company_id"] for brand in values):
            raise serializers.ValidationError("Toutes les marques doivent appartenir à cette société.")
        return values

    def validate_nom(self, value):
        existing = LogisticsSupplier.objects.filter(
            company_id=self.context["company_id"], nom__iexact=value
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "Ce fournisseur existe déjà pour cette société."
            )
        return value


class SupplierAccessMixin(CompanyAccessMixin):
    def company_id(self, request):
        company_id = self._parse_company_id(
            request.query_params.get("company_id"),
            error_message="company_id est requis.",
        )
        self._check_company_access(request, company_id)
        return company_id

    @staticmethod
    def queryset(company_id):
        return LogisticsSupplier.objects.filter(company_id=company_id).prefetch_related("marques").annotate(
            total_dossiers=Count("dossiers"),
            derniere_activite=Coalesce(
                Max("dossiers__date_updated"), F("date_updated")
            ),
        )

    @staticmethod
    def check_write(request, company_id):
        from .views import _can_manage_logistics

        if not _can_manage_logistics(request.user, company_id):
            raise PermissionDenied(
                "Vous n’avez pas les droits pour modifier le répertoire fournisseur."
            )
        if "company" in request.data and str(request.data["company"]) != str(
            company_id
        ):
            raise ValidationError(
                {
                    "company": "Un fournisseur ne peut pas être déplacé vers une autre société."
                }
            )

    @staticmethod
    def save(serializer, company_id):
        try:
            with transaction.atomic():
                return serializer.save(company_id=company_id)
        except IntegrityError:
            raise ValidationError(
                {"nom": "Ce fournisseur existe déjà pour cette société."}
            )


class LogisticsSupplierListView(SupplierAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company_id = self.company_id(request)
        filters = LogisticsSupplierFilter(
            request.query_params, queryset=self.queryset(company_id)
        )
        if not filters.is_valid():
            raise ValidationError(filters.errors)
        ordering = request.query_params.get("ordering", "nom")
        descending = ordering.startswith("-")
        field = {"fournisseur": "nom", "fournisseur_email": "email"}.get(
            ordering.removeprefix("-"), ordering.removeprefix("-")
        )
        if field not in {"nom", "email", "total_dossiers", "derniere_activite"}:
            field, descending = "nom", False
        expression = Lower(field) if field in {"nom", "email"} else F(field)
        suppliers = filters.qs.order_by(
            (
                expression.desc(nulls_last=True)
                if descending
                else expression.asc(nulls_last=True)
            ),
            "pk",
        )
        if self._get_bool_param(request, "pagination"):
            paginator = CustomPagination()
            page = paginator.paginate_queryset(suppliers, request)
            return paginator.get_paginated_response(
                LogisticsSupplierSerializer(page, many=True).data
            )
        return Response(LogisticsSupplierSerializer(suppliers, many=True).data)

    def post(self, request):
        company_id = self.company_id(request)
        self.check_write(request, company_id)
        serializer = LogisticsSupplierSerializer(
            data=request.data, context={"company_id": company_id}
        )
        serializer.is_valid(raise_exception=True)
        supplier = self.save(serializer, company_id)
        return Response(
            LogisticsSupplierSerializer(
                self.queryset(company_id).get(pk=supplier.pk)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class LogisticsSupplierDetailView(SupplierAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        company_id = self.company_id(request)
        return Response(
            LogisticsSupplierSerializer(
                get_object_or_404(self.queryset(company_id), pk=pk)
            ).data
        )

    def put(self, request, pk):
        return self.update(request, pk, partial=False)

    def patch(self, request, pk):
        return self.update(request, pk, partial=True)

    def update(self, request, pk, partial):
        company_id = self.company_id(request)
        self.check_write(request, company_id)
        instance = get_object_or_404(LogisticsSupplier, pk=pk, company_id=company_id)
        serializer = LogisticsSupplierSerializer(
            instance,
            data=request.data,
            partial=partial,
            context={"company_id": company_id},
        )
        serializer.is_valid(raise_exception=True)
        self.save(serializer, company_id)
        return Response(
            LogisticsSupplierSerializer(self.queryset(company_id).get(pk=pk)).data
        )

    def delete(self, request, pk):
        company_id = self.company_id(request)
        if not can_delete(request.user, company_id):
            raise PermissionDenied(
                "Vous n’avez pas les droits pour supprimer ce fournisseur."
            )
        instance = get_object_or_404(LogisticsSupplier, pk=pk, company_id=company_id)
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                {
                    "fournisseur": "Ce fournisseur est lié à des dossiers logistiques. Il peut être modifié, mais pas supprimé."
                }
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
