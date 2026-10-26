from typing import cast
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import (
    Case,
    CharField,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Q,
    Value,
    When,
)
from django.http import Http404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from account.models import Membership
from company.models import Company
from core.constants import ROLE_CAISSIER, ROLE_LOGISTIQUE
from core.filters import CalendarDateFilter
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

    if query_params.get("filter_logic", "and") == "or":
        try:
            groups = json.loads(query_params.get("filter_groups", ""))
        except (TypeError, ValueError):
            raise ValidationError({"filter_groups": "Invalid filter groups."})
        if not isinstance(groups, list) or not groups:
            raise ValidationError({"filter_groups": "Invalid filter groups."})
        allowed = set(exact_fields)
        for name in text_fields:
            allowed.update([name, *[f"{name}__{suffix}" for suffix in ("icontains", "istartswith", "iendswith", "isempty")]])
        for name in numeric_fields:
            allowed.update([name, *[f"{name}__{suffix}" for suffix in ("gt", "gte", "lt", "lte", "ne", "isempty")]])
        for name in date_fields:
            allowed.update((f"{name}_after", f"{name}_before"))
        matches = Q()
        for group in groups:
            if not isinstance(group, dict) or not group or set(group) - allowed or any(not isinstance(value, (str, int, float, bool)) for value in group.values()):
                raise ValidationError({"filter_groups": "Invalid filter group."})
            child = apply_list_filters(
                queryset, group, text_fields=text_fields,
                numeric_fields=numeric_fields, exact_fields=exact_fields,
                date_fields=date_fields,
            )
            # Both date bounds belong to one row; rows are ORed within the
            # already company-scoped and searched queryset.
            matches |= Q(pk__in=child.values("pk"))
        return queryset.filter(matches)

    for public_name, model_field in text_fields.items():
        for suffix in ("icontains", "istartswith", "iendswith"):
            value = query_params.get(f"{public_name}__{suffix}")
            if value:
                queryset = queryset.filter(**{f"{model_field}__{suffix}": value})
        exact_value = query_params.get(public_name)
        if exact_value:
            queryset = queryset.filter(**{f"{model_field}__iexact": exact_value})
        empty = query_params.get(f"{public_name}__isempty")
        if empty is not None:
            empty_q = Q(**{f"{model_field}__isnull": True}) | Q(**{model_field: ""})
            queryset = queryset.filter(empty_q) if str(empty).lower() == "true" else queryset.exclude(empty_q)

    for public_name, model_field in numeric_fields.items():
        for suffix in ("", "gt", "gte", "lt", "lte", "ne"):
            name = f"{public_name}__{suffix}" if suffix else public_name
            value = query_params.get(name)
            if value in (None, ""):
                continue
            try:
                value = Decimal(str(value))
                if not value.is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError({name: "Invalid number."})
            if suffix == "ne":
                queryset = queryset.exclude(**{model_field: value})
            else:
                lookup = f"{model_field}__{suffix}" if suffix else model_field
                queryset = queryset.filter(**{lookup: value})
        empty = query_params.get(f"{public_name}__isempty")
        if empty is not None:
            queryset = queryset.filter(**{f"{model_field}__isnull": str(empty).lower() == "true"})

    for public_name, model_field in exact_fields.items():
        value = query_params.get(public_name)
        if value not in (None, ""):
            queryset = queryset.filter(**{model_field: value})

    for public_name, model_field in date_fields.items():
        for suffix, lookup in (("after", "gte"), ("before", "lte")):
            name = f"{public_name}_{suffix}"
            value = query_params.get(name)
            if not value:
                continue
            try:
                day = date.fromisoformat(str(value))
            except (ValueError, TypeError):
                raise ValidationError({name: "Invalid date."})
            queryset = CalendarDateFilter(field_name=model_field, lookup_expr=lookup).filter(queryset, day)

    return queryset


def apply_list_ordering(queryset, query_params, fields, default):
    ordering = []
    for term in (query_params.get("ordering") or "").split(","):
        term = term.strip()
        descending = term.startswith("-")
        field = fields.get(term[1:] if descending else term)
        if field:
            ordering.append(("-" if descending else "") + field)
    # A stable tie-breaker prevents missing/duplicated cards on successive pages.
    if ordering:
        return queryset.order_by(*ordering, "pk")
    return queryset.order_by(*default)


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

    @staticmethod
    def ensure_inventory_enabled(company):
        StockAccessMixin.ensure_enabled(company)
        if not company.inventory_management_enabled:
            raise ValidationError(
                {"inventory": "L'inventaire n'est pas activé pour cette société."}
            )


class StockBalanceListView(StockAccessMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        company = self.get_company(request)
        queryset = (
            StockBalance.objects.filter(company=company)
            .select_related("article", "emplacement", "company")
            .annotate(available_for_filter=ExpressionWrapper(
                F("physical_quantity") - F("reserved_quantity"),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            ))
            .annotate(stock_state_for_filter=Case(
                When(available_for_filter__lt=0, then=Value("a_approvisionner")),
                When(article__stock_minimum__gt=0, available_for_filter__lte=F("article__stock_minimum"), then=Value("minimum")),
                default=Value("disponible"), output_field=CharField(),
            ))
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
            queryset = queryset.filter(emplacement_id__in=emplacement_ids.split(","))
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
            exact_fields={"stock_state": "stock_state_for_filter"},
            date_fields={"date_updated": "date_updated"},
        )
        stock_states = {
            value
            for value in (request.query_params.get("stock_states") or "").split(",")
            if value
        }
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
        ordered_queryset = apply_list_ordering(queryset.annotate(
            positive_stock=Case(
                When(physical_quantity__gt=0, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ), request.query_params, {
            "id": "pk", "article_reference": "article__reference",
            "article_designation": "article__designation", "emplacement_name": "emplacement__nom",
            "physical_quantity": "physical_quantity", "reserved_quantity": "reserved_quantity",
            "available_quantity": "available_for_filter", "stock_minimum": "article__stock_minimum",
            "stock_state": "stock_state_for_filter", "date_updated": "date_updated",
        }, ("positive_stock", "article__reference", "emplacement__nom", "pk"))
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
        queryset = apply_list_ordering(queryset, request.query_params, {
            "id": "pk", "article_reference": "balance__article__reference",
            "article_designation": "balance__article__designation", "emplacement_name": "balance__emplacement__nom",
            "movement_type": "movement_type", "quantity": "quantity", "balance_after": "balance_after",
            "note": "note", "source_type": "source_type", "actor_name": "actor__email", "date_created": "date_created",
        }, ("-date_created", "-pk"))
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
            queryset = queryset.filter(lines__emplacement_id__in=emplacement_ids.split(",")).distinct()
        logistics_order_ids = request.query_params.get("logistics_order_ids")
        if logistics_order_ids:
            queryset = queryset.filter(logistics_order_id__in=logistics_order_ids.split(","))
        queryset = apply_list_ordering(queryset, request.query_params, {
            "id": "pk", "reference": "reference", "logistics_order_number": "logistics_order__numero_commande",
            "status": "status", "note": "note", "created_by_name": "created_by__email",
            "date_created": "date_created", "date_validated": "date_validated",
        }, ("-date_created", "-pk"))
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
        statuses = request.query_params.get("statuses")
        if statuses:
            queryset = queryset.filter(status__in=statuses.split(","))
        emplacement_ids = request.query_params.get("emplacement_ids")
        if emplacement_ids:
            queryset = queryset.filter(emplacement_id__in=emplacement_ids.split(","))
        queryset = apply_list_ordering(queryset, request.query_params, {
            "id": "pk", "reference": "reference", "emplacement_name": "emplacement__nom",
            "status": "status", "note": "note", "created_by_name": "created_by__email",
            "date_created": "date_created", "date_validated": "date_validated",
        }, ("-date_created", "-pk"))
        paginator = CustomPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(
            InventorySerializer(page, many=True).data
        )

    @transaction.atomic
    def post(self, request):
        company = self.get_company(request)
        self.ensure_inventory_enabled(company)
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
        self.ensure_inventory_enabled(company)
        self.require_role(request, company, (ROLE_CAISSIER,))
        validate_inventory(inventory, request.user)
        inventory.refresh_from_db()
        return Response(InventorySerializer(inventory).data)
