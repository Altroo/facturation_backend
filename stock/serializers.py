from decimal import Decimal
from functools import cached_property

from rest_framework import serializers

from article.models import Article
from parameter.models import Emplacement
from .models import (
    InventoryLine,
    InventorySession,
    StockBalance,
    StockMovement,
    StockReceipt,
    StockReceiptLine,
)
from .services import StockBalanceSnapshot, balance_snapshot, is_product


class StockBalanceSerializer(serializers.ModelSerializer):
    article_reference = serializers.CharField(
        source="article.reference", read_only=True
    )
    article_designation = serializers.CharField(
        source="article.designation", read_only=True
    )
    emplacement_name = serializers.CharField(source="emplacement.nom", read_only=True)
    available_quantity = serializers.SerializerMethodField()
    incoming_quantity = serializers.SerializerMethodField()
    projected_quantity = serializers.SerializerMethodField()
    stock_minimum = serializers.DecimalField(
        source="article.stock_minimum", max_digits=12, decimal_places=3, read_only=True
    )
    stock_state = serializers.SerializerMethodField()

    class Meta:
        model = StockBalance
        fields = (
            "id",
            "company",
            "article",
            "article_reference",
            "article_designation",
            "emplacement",
            "emplacement_name",
            "physical_quantity",
            "reserved_quantity",
            "available_quantity",
            "incoming_quantity",
            "projected_quantity",
            "stock_minimum",
            "stock_state",
            "date_updated",
        )
        read_only_fields = fields

    @cached_property
    def stock_snapshots(self) -> dict[int, StockBalanceSnapshot]:
        configured = self.context.get("stock_snapshots")
        if isinstance(configured, dict):
            return configured.copy()
        return {}

    def _snapshot(self, obj: StockBalance) -> StockBalanceSnapshot:
        snapshot = self.stock_snapshots.get(obj.pk)
        if snapshot is None:
            snapshot = balance_snapshot(obj)
            self.stock_snapshots[obj.pk] = snapshot
        return snapshot

    def get_available_quantity(self, obj):
        return self._snapshot(obj)["available_quantity"]

    def get_incoming_quantity(self, obj):
        return self._snapshot(obj)["incoming_quantity"]

    def get_projected_quantity(self, obj):
        return self._snapshot(obj)["projected_quantity"]

    def get_stock_state(self, obj):
        return self._snapshot(obj)["stock_state"]


class StockMovementSerializer(serializers.ModelSerializer):
    article_reference = serializers.CharField(
        source="balance.article.reference", read_only=True
    )
    article_designation = serializers.CharField(
        source="balance.article.designation", read_only=True
    )
    emplacement_name = serializers.CharField(
        source="balance.emplacement.nom", read_only=True
    )
    actor_name = serializers.SerializerMethodField()
    movement_type_display = serializers.CharField(
        source="get_movement_type_display", read_only=True
    )

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "balance",
            "article_reference",
            "article_designation",
            "emplacement_name",
            "movement_type",
            "movement_type_display",
            "quantity",
            "balance_after",
            "source_type",
            "source_id",
            "source_line_id",
            "note",
            "actor",
            "actor_name",
            "date_created",
        )
        read_only_fields = fields

    @staticmethod
    def get_actor_name(obj):
        if not obj.actor:
            return None
        return (
            f"{obj.actor.first_name} {obj.actor.last_name}".strip() or obj.actor.email
        )


class StockAdjustmentSerializer(serializers.Serializer):
    article = serializers.PrimaryKeyRelatedField(queryset=Article.objects.all())
    emplacement = serializers.PrimaryKeyRelatedField(queryset=Emplacement.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    movement_type = serializers.ChoiceField(
        choices=(StockMovement.TYPE_OPENING, StockMovement.TYPE_ADJUSTMENT),
        default=StockMovement.TYPE_ADJUSTMENT,
    )
    reason = serializers.CharField(max_length=1000, allow_blank=False)

    def validate(self, attrs):
        if attrs["quantity"] == Decimal("0"):
            raise serializers.ValidationError(
                {"quantity": "La quantité ne peut pas être nulle."}
            )
        if attrs["article"].company_id != attrs["emplacement"].company_id:
            raise serializers.ValidationError(
                {"emplacement": "L'emplacement appartient à une autre société."}
            )
        if not is_product(attrs["article"]):
            raise serializers.ValidationError(
                {"article": "Un service ne peut pas être géré en stock."}
            )
        return attrs


class StockReceiptLineSerializer(serializers.ModelSerializer):
    article_reference = serializers.CharField(
        source="article.reference", read_only=True
    )
    article_designation = serializers.CharField(
        source="article.designation", read_only=True
    )
    emplacement_name = serializers.CharField(source="emplacement.nom", read_only=True)

    class Meta:
        model = StockReceiptLine
        fields = (
            "id",
            "logistics_line",
            "article",
            "article_reference",
            "article_designation",
            "emplacement",
            "emplacement_name",
            "quantity",
        )
        read_only_fields = (
            "id",
            "article_reference",
            "article_designation",
            "emplacement_name",
        )


class StockReceiptSerializer(serializers.ModelSerializer):
    lines = StockReceiptLineSerializer(many=True)
    logistics_order_number = serializers.CharField(
        source="logistics_order.numero_commande", read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockReceipt
        fields = (
            "id",
            "company",
            "logistics_order",
            "logistics_order_number",
            "status",
            "reference",
            "note",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "date_created",
            "date_validated",
            "lines",
        )
        read_only_fields = (
            "id",
            "company",
            "status",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "date_created",
            "date_validated",
        )

    @staticmethod
    def _user_name(user):
        return (
            (f"{user.first_name} {user.last_name}".strip() or user.email)
            if user
            else None
        )

    def get_created_by_name(self, obj):
        return self._user_name(obj.created_by)

    def get_validated_by_name(self, obj):
        return self._user_name(obj.validated_by)

    def validate(self, attrs):
        order = attrs["logistics_order"]
        if not order.company.stock_management_enabled:
            raise serializers.ValidationError(
                {"company": "La gestion de stock n'est pas activée."}
            )
        logistics_line_ids = set()
        for line in attrs.get("lines", []):
            logistics_line = line["logistics_line"]
            if logistics_line.pk in logistics_line_ids:
                raise serializers.ValidationError(
                    {
                        "lines": "Une ligne logistique ne peut être reçue qu'une fois par réception."
                    }
                )
            logistics_line_ids.add(logistics_line.pk)
            if logistics_line.commande_id != order.id:
                raise serializers.ValidationError(
                    {"lines": "Une ligne ne correspond pas au dossier sélectionné."}
                )
            if line["article"].id != logistics_line.article_id:
                raise serializers.ValidationError(
                    {"lines": "L'article ne correspond pas à la ligne logistique."}
                )
            if line["emplacement"].company_id != order.company_id:
                raise serializers.ValidationError(
                    {"lines": "L'emplacement appartient à une autre société."}
                )
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        order = validated_data["logistics_order"]
        receipt = StockReceipt.objects.create(
            company=order.company,
            created_by=self.context["request"].user,
            **validated_data,
        )
        for line in lines:
            StockReceiptLine.objects.create(receipt=receipt, **line)
        return receipt


class InventoryLineSerializer(serializers.ModelSerializer):
    article_reference = serializers.CharField(
        source="article.reference", read_only=True
    )
    article_designation = serializers.CharField(
        source="article.designation", read_only=True
    )
    difference = serializers.SerializerMethodField()

    class Meta:
        model = InventoryLine
        fields = (
            "id",
            "article",
            "article_reference",
            "article_designation",
            "expected_quantity",
            "counted_quantity",
            "difference",
        )
        read_only_fields = (
            "id",
            "article_reference",
            "article_designation",
            "expected_quantity",
            "difference",
        )

    @staticmethod
    def get_difference(obj):
        return obj.counted_quantity - obj.expected_quantity


class InventorySerializer(serializers.ModelSerializer):
    lines = InventoryLineSerializer(many=True)
    emplacement_name = serializers.CharField(source="emplacement.nom", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = InventorySession
        fields = (
            "id",
            "company",
            "emplacement",
            "emplacement_name",
            "status",
            "reference",
            "note",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "date_created",
            "date_validated",
            "lines",
        )
        read_only_fields = (
            "id",
            "company",
            "status",
            "created_by",
            "created_by_name",
            "validated_by",
            "validated_by_name",
            "date_created",
            "date_validated",
            "emplacement_name",
        )

    @staticmethod
    def _user_name(user):
        return (
            (f"{user.first_name} {user.last_name}".strip() or user.email)
            if user
            else None
        )

    def get_created_by_name(self, obj):
        return self._user_name(obj.created_by)

    def get_validated_by_name(self, obj):
        return self._user_name(obj.validated_by)

    def validate(self, attrs):
        emplacement = attrs["emplacement"]
        article_ids = set()
        for line in attrs.get("lines", []):
            article = line["article"]
            if article.pk in article_ids:
                raise serializers.ValidationError(
                    {
                        "lines": "Un article ne peut apparaître qu'une fois par inventaire."
                    }
                )
            article_ids.add(article.pk)
            if article.company_id != emplacement.company_id:
                raise serializers.ValidationError(
                    {"lines": "Un article appartient à une autre société."}
                )
            if not is_product(article):
                raise serializers.ValidationError(
                    {"lines": "Un service ne peut pas être inventorié."}
                )
            if line["counted_quantity"] < 0:
                raise serializers.ValidationError(
                    {"lines": "La quantité comptée ne peut pas être négative."}
                )
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        emplacement = validated_data["emplacement"]
        inventory = InventorySession.objects.create(
            company=emplacement.company,
            created_by=self.context["request"].user,
            **validated_data,
        )
        for line in lines:
            balance = StockBalance.objects.filter(
                article=line["article"], emplacement=emplacement
            ).first()
            InventoryLine.objects.create(
                inventory=inventory,
                expected_quantity=(
                    balance.physical_quantity if balance else Decimal("0")
                ),
                **line,
            )
        return inventory
