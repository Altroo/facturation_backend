from typing import cast

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q
from django.http import Http404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from company.models import Company
from core.constants import ROLE_CAISSIER, ROLE_LOGISTIQUE
from facturation_backend.utils import CustomPagination
from .models import InventorySession, StockBalance, StockMovement, StockReceipt
from .serializers import (
    InventorySerializer,
    StockAdjustmentSerializer,
    StockBalanceSerializer,
    StockMovementSerializer,
    StockReceiptSerializer,
)
from .services import (
    cancel_receipt,
    get_locked_balance,
    post_movement,
    prepare_balance_snapshots,
    validate_inventory,
    validate_receipt,
)


def apply_list_filters(
    queryset,
    query_params,
    *,
    text_fields=None,
    numeric_fields=None,
    exact_fields=None,
    date_fields=None,
):
    text_fields = text_fields or {}
    numeric_fields = numeric_fields or {}
    exact_fields = exact_fields or {}
    date_fields = date_fields or {}

    for public_name, model_field in text_fields.items():
        for suffix in ("icontains", "istartswith", "iendswith"):
            value = query_params.get(f"{public_name}__{suffix}")
            if value:
                queryset = queryset.filter(**{f"{model_field}__{suffix}": value})
        exact_value = query_params.get(public_name)
        if exact_value:
            queryset = queryset.filter(**{f"{model_field}__iexact": exact_value})

    for public_name, model_field in numeric_fields.items():
        value = query_params.get(public_name)
        if value not in (None, ""):
            queryset = queryset.filter(**{model_field: value})
        for suffix in ("gt", "gte", "lt", "lte"):
            value = query_params.get(f"{public_name}__{suffix}")
            if value not in (None, ""):
                queryset = queryset.filter(**{f"{model_field}__{suffix}": value})
        not_equal = query_params.get(f"{public_name}__ne")
        if not_equal not in (None, ""):
            queryset = queryset.exclude(**{model_field: not_equal})

    for public_name, model_field in exact_fields.items():
        value = query_params.get(public_name)
        if value not in (None, ""):
            queryset = queryset.filter(**{model_field: value})

    for public_name, model_field in date_fields.items():
        after = query_params.get(f"{public_name}_after")
        before = query_params.get(f"{public_name}_before")
        if after:
            queryset = queryset.filter(**{f"{model_field}__date__gte": after})
        if before:
            queryset = queryset.filter(**{f"{model_field}__date__lte": before})

    return queryset


class StockAccessMixin:
    @staticmethod
    def get_company(request):
        raw_id = request.query_params.get("company_id") or request.data.get(
            "company_id"
        )
        if not raw_id:
            raise ValidationError({"company_id": "company_id est requis."})
        try:
            company = Company.objects.get(pk=int(raw_id))
        except (ValueError, TypeError, Company.DoesNotExist):
            raise Http404("Société introuvable.")
        if not (
            request.user.is_superuser
            or Membership.objects.filter(user=request.user, company=company).exists()
        ):
            raise PermissionDenied("Vous n'avez pas accès à cette société.")
        return company

    @staticmethod
    def require_role(request, company, roles):
        if request.user.is_superuser:
            return
        if not Membership.objects.filter(
            user=request.user, company=company, role__name__in=roles
        ).exists():
            raise PermissionDenied(
                "Vous n'avez pas les droits pour cette opération de stock."
            )

    @staticmethod
    def ensure_enabled(company):
        if not company.stock_management_enabled:
            raise ValidationError(
                {"stock": "La gestion de stock n'est pas activée pour cette société."}
            )


class StockBalanceListView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company = self.get_company(request)
        queryset = StockBalance.objects.filter(company=company).select_related(
            "article", "emplacement", "company"
        )
        article_id = request.query_params.get("article_id")
        emplacement_id = request.query_params.get("emplacement_id")
        low_only = request.query_params.get("low_only", "false").lower() == "true"
        search = (request.query_params.get("search") or "").strip()
        if article_id:
            queryset = queryset.filter(article_id=article_id)
        if emplacement_id:
            queryset = queryset.filter(emplacement_id=emplacement_id)
        emplacement_ids = request.query_params.get("emplacement_ids")
        if emplacement_ids:
            queryset = queryset.filter(
                emplacement_id__in=emplacement_ids.split(",")
            )
        if search:
            queryset = queryset.filter(
                Q(article__reference__icontains=search)
                | Q(article__designation__icontains=search)
                | Q(emplacement__nom__icontains=search)
            )
        queryset = apply_list_filters(
            queryset,
            request.query_params,
            text_fields={
                "article_reference": "article__reference",
                "article_designation": "article__designation",
                "emplacement_name": "emplacement__nom",
            },
            numeric_fields={
                "physical_quantity": "physical_quantity",
                "reserved_quantity": "reserved_quantity",
                "stock_minimum": "article__stock_minimum",
            },
        )
        stock_states = {
            value
            for value in (request.query_params.get("stock_states") or "").split(",")
            if value
        }
        if low_only or stock_states:
            queryset = queryset.annotate(
                available_for_filter=ExpressionWrapper(
                    F("physical_quantity") - F("reserved_quantity"),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                )
            )
        if low_only:
            queryset = queryset.filter(
                article__stock_minimum__gt=0,
                available_for_filter__lte=F("article__stock_minimum"),
            )
        if stock_states:
            state_filter = Q()
            if "a_approvisionner" in stock_states:
                state_filter |= Q(available_for_filter__lt=0)
            if "minimum" in stock_states:
                state_filter |= Q(
                    article__stock_minimum__gt=0,
                    available_for_filter__gte=0,
                    available_for_filter__lte=F("article__stock_minimum"),
                )
            if "disponible" in stock_states:
                state_filter |= Q(
                    article__stock_minimum=0,
                    available_for_filter__gte=0,
                ) | Q(available_for_filter__gt=F("article__stock_minimum"))
            queryset = queryset.filter(state_filter)
        ordered_queryset = queryset.order_by("article__reference", "emplacement__nom")
        if request.query_params.get("pagination", "true").lower() == "true":
            paginator = CustomPagination()
            page = cast(
                list[StockBalance],
                paginator.paginate_queryset(ordered_queryset, request),
            )
            stock_snapshots = prepare_balance_snapshots(page)
            return paginator.get_paginated_response(
                StockBalanceSerializer(
                    page, many=True, context={"stock_snapshots": stock_snapshots}
                ).data
            )
        rows = list(ordered_queryset)
        stock_snapshots = prepare_balance_snapshots(rows)
        return Response(
            StockBalanceSerializer(
                rows, many=True, context={"stock_snapshots": stock_snapshots}
            ).data
        )


class StockBalanceDetailView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        company = self.get_company(request)
        balance = (
            StockBalance.objects.filter(company=company, pk=pk)
            .select_related("article", "emplacement", "company")
            .first()
        )
        if not balance:
            raise Http404("Stock introuvable.")
        stock_snapshots = prepare_balance_snapshots([balance])
        return Response(
            StockBalanceSerializer(
                balance, context={"stock_snapshots": stock_snapshots}
            ).data
        )


class StockMovementListView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company = self.get_company(request)
        queryset = StockMovement.objects.filter(
            balance__company=company
        ).select_related("balance__article", "balance__emplacement", "actor")
        if request.query_params.get("article_id"):
            queryset = queryset.filter(
                balance__article_id=request.query_params["article_id"]
            )
        if request.query_params.get("movement_type"):
            queryset = queryset.filter(
                movement_type=request.query_params["movement_type"]
            )
        movement_types = request.query_params.get("movement_types")
        if movement_types:
            queryset = queryset.filter(movement_type__in=movement_types.split(","))
        emplacement_ids = request.query_params.get("emplacement_ids")
        if emplacement_ids:
            queryset = queryset.filter(
                balance__emplacement_id__in=emplacement_ids.split(",")
            )
        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(balance__article__reference__icontains=search)
                | Q(balance__article__designation__icontains=search)
                | Q(balance__emplacement__nom__icontains=search)
                | Q(note__icontains=search)
                | Q(source_type__icontains=search)
                | Q(actor__first_name__icontains=search)
                | Q(actor__last_name__icontains=search)
                | Q(actor__email__icontains=search)
            )
        queryset = apply_list_filters(
            queryset,
            request.query_params,
            text_fields={
                "article_reference": "balance__article__reference",
                "article_designation": "balance__article__designation",
                "emplacement_name": "balance__emplacement__nom",
                "note": "note",
                "source_type": "source_type",
                "actor_name": "actor__email",
            },
            numeric_fields={"quantity": "quantity", "balance_after": "balance_after"},
            exact_fields={"movement_type": "movement_type"},
            date_fields={"date_created": "date_created"},
        )
        statuses = request.query_params.get("statuses")
        if statuses:
            queryset = queryset.filter(status__in=statuses.split(","))
        logistics_order_ids = request.query_params.get("logistics_order_ids")
        if logistics_order_ids:
            queryset = queryset.filter(
                logistics_order_id__in=logistics_order_ids.split(",")
            )
        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            StockMovementSerializer(page, many=True).data
        )


class StockMovementDetailView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        company = self.get_company(request)
        movement = (
            StockMovement.objects.filter(balance__company=company, pk=pk)
            .select_related("balance__article", "balance__emplacement", "actor")
            .first()
        )
        if not movement:
            raise Http404("Mouvement introuvable.")
        return Response(StockMovementSerializer(movement).data)


class StockAdjustmentCreateView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request):
        company = self.get_company(request)
        self.ensure_enabled(company)
        self.require_role(request, company, (ROLE_CAISSIER,))
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["article"].company_id != company.id:
            raise ValidationError(
                {"article": "L'article appartient à une autre société."}
            )
        balance = get_locked_balance(data["article"], data["emplacement"])
        movement = post_movement(
            balance=balance,
            quantity=data["quantity"],
            movement_type=data["movement_type"],
            actor=request.user,
            note=data["reason"],
        )
        return Response(
            StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED
        )


class StockReceiptListCreateView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company = self.get_company(request)
        queryset = (
            StockReceipt.objects.filter(company=company)
            .select_related("logistics_order", "created_by", "validated_by")
            .prefetch_related("lines__article", "lines__emplacement")
        )
        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(logistics_order__numero_commande__icontains=search)
                | Q(note__icontains=search)
                | Q(lines__article__reference__icontains=search)
                | Q(lines__article__designation__icontains=search)
                | Q(created_by__first_name__icontains=search)
                | Q(created_by__last_name__icontains=search)
                | Q(created_by__email__icontains=search)
            ).distinct()
        queryset = apply_list_filters(
            queryset,
            request.query_params,
            text_fields={
                "reference": "reference",
                "logistics_order_number": "logistics_order__numero_commande",
                "note": "note",
                "created_by_name": "created_by__email",
            },
            exact_fields={"status": "status"},
            date_fields={"date_created": "date_created"},
        )
        statuses = request.query_params.get("statuses")
        if statuses:
            queryset = queryset.filter(status__in=statuses.split(","))
        emplacement_ids = request.query_params.get("emplacement_ids")
        if emplacement_ids:
            queryset = queryset.filter(
                emplacement_id__in=emplacement_ids.split(",")
            )
        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            StockReceiptSerializer(page, many=True).data
        )

    @transaction.atomic
    def post(self, request):
        company = self.get_company(request)
        self.ensure_enabled(company)
        self.require_role(request, company, (ROLE_LOGISTIQUE,))
        serializer = StockReceiptSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["logistics_order"].company_id != company.id:
            raise ValidationError(
                {"logistics_order": "Le dossier appartient à une autre société."}
            )
        receipt = serializer.save()
        return Response(
            StockReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED
        )


class StockReceiptDetailView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        company = self.get_company(request)
        receipt = (
            StockReceipt.objects.filter(company=company, pk=pk)
            .select_related("logistics_order", "created_by", "validated_by")
            .prefetch_related("lines__article", "lines__emplacement")
            .first()
        )
        if not receipt:
            raise Http404("Réception introuvable.")
        return Response(StockReceiptSerializer(receipt).data)


class StockReceiptActionView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk, action):
        receipt = (
            StockReceipt.objects.select_for_update()
            .select_related("company", "logistics_order")
            .filter(pk=pk)
            .first()
        )
        if not receipt:
            raise Http404("Réception introuvable.")
        company = self.get_company(request)
        if receipt.company_id != company.id:
            raise PermissionDenied("Cette réception appartient à une autre société.")
        self.ensure_enabled(company)
        self.require_role(request, company, (ROLE_LOGISTIQUE,))
        if action == "validate":
            validate_receipt(receipt, request.user)
        elif action == "cancel":
            cancel_receipt(receipt, request.user)
        else:
            raise Http404("Action inconnue.")
        receipt.refresh_from_db()
        return Response(StockReceiptSerializer(receipt).data)


class InventoryListCreateView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company = self.get_company(request)
        queryset = (
            InventorySession.objects.filter(company=company)
            .select_related("emplacement", "created_by", "validated_by")
            .prefetch_related("lines__article")
        )
        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(emplacement__nom__icontains=search)
                | Q(note__icontains=search)
                | Q(lines__article__reference__icontains=search)
                | Q(lines__article__designation__icontains=search)
                | Q(created_by__first_name__icontains=search)
                | Q(created_by__last_name__icontains=search)
                | Q(created_by__email__icontains=search)
            ).distinct()
        queryset = apply_list_filters(
            queryset,
            request.query_params,
            text_fields={
                "reference": "reference",
                "emplacement_name": "emplacement__nom",
                "note": "note",
                "created_by_name": "created_by__email",
            },
            exact_fields={"status": "status"},
            date_fields={"date_created": "date_created"},
        )
        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            InventorySerializer(page, many=True).data
        )

    @transaction.atomic
    def post(self, request):
        company = self.get_company(request)
        self.ensure_enabled(company)
        self.require_role(request, company, (ROLE_CAISSIER,))
        serializer = InventorySerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["emplacement"].company_id != company.id:
            raise ValidationError(
                {"emplacement": "L'emplacement appartient à une autre société."}
            )
        inventory = serializer.save()
        return Response(
            InventorySerializer(inventory).data, status=status.HTTP_201_CREATED
        )


class InventoryDetailView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk):
        company = self.get_company(request)
        inventory = (
            InventorySession.objects.filter(company=company, pk=pk)
            .select_related("emplacement", "created_by", "validated_by")
            .prefetch_related("lines__article")
            .first()
        )
        if not inventory:
            raise Http404("Inventaire introuvable.")
        return Response(InventorySerializer(inventory).data)


class InventoryValidateView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, pk):
        inventory = (
            InventorySession.objects.select_for_update()
            .select_related("company")
            .filter(pk=pk)
            .first()
        )
        if not inventory:
            raise Http404("Inventaire introuvable.")
        company = self.get_company(request)
        if inventory.company_id != company.id:
            raise PermissionDenied("Cet inventaire appartient à une autre société.")
        self.ensure_enabled(company)
        self.require_role(request, company, (ROLE_CAISSIER,))
        validate_inventory(inventory, request.user)
        inventory.refresh_from_db()
        return Response(InventorySerializer(inventory).data)
