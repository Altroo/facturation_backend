from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class StockBalance(models.Model):
    company = models.ForeignKey(
        "company.Company", on_delete=models.PROTECT, related_name="stock_balances"
    )
    article = models.ForeignKey(
        "article.Article", on_delete=models.PROTECT, related_name="stock_balances"
    )
    emplacement = models.ForeignKey(
        "parameter.Emplacement", on_delete=models.PROTECT, related_name="stock_balances"
    )
    physical_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    reserved_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("article__reference", "emplacement__nom")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "article", "emplacement"),
                name="unique_stock_balance",
            ),
            models.CheckConstraint(
                condition=models.Q(physical_quantity__gte=0),
                name="stock_physical_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__gte=0),
                name="stock_reserved_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("company", "article"), name="stock_bal_company_article"
            ),
        ]

    @property
    def available_quantity(self):
        return self.physical_quantity - self.reserved_quantity

    def __str__(self):
        return f"{self.article} — {self.emplacement}: {self.physical_quantity}"


class StockReservation(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_RELEASED = "released"
    STATUS_CONSUMED = "consumed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, _("Active")),
        (STATUS_RELEASED, _("Libérée")),
        (STATUS_CONSUMED, _("Consommée")),
    ]

    proforma_line = models.OneToOneField(
        "facture_proforma.FactureProFormaLine",
        on_delete=models.PROTECT,
        related_name="+",
    )
    balance = models.ForeignKey(
        StockBalance, on_delete=models.PROTECT, related_name="reservations"
    )
    reserved_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    consumed_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    released_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date_created",)


class StockMovement(models.Model):
    TYPE_OPENING = "opening"
    TYPE_ADJUSTMENT = "adjustment"
    TYPE_RECEIPT = "receipt"
    TYPE_DELIVERY = "delivery"
    TYPE_INVENTORY = "inventory"
    TYPE_REVERSAL = "reversal"
    TYPE_CHOICES = [
        (TYPE_OPENING, _("Stock initial")),
        (TYPE_ADJUSTMENT, _("Ajustement")),
        (TYPE_RECEIPT, _("Réception")),
        (TYPE_DELIVERY, _("Livraison")),
        (TYPE_INVENTORY, _("Inventaire")),
        (TYPE_REVERSAL, _("Annulation")),
    ]

    balance = models.ForeignKey(
        StockBalance, on_delete=models.PROTECT, related_name="movements"
    )
    movement_type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    source_type = models.CharField(max_length=40, blank=True, default="")
    source_id = models.PositiveIntegerField(null=True, blank=True)
    source_line_id = models.PositiveIntegerField(null=True, blank=True)
    reservation = models.ForeignKey(
        StockReservation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements",
    )
    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversal",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    note = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(
        max_length=120, unique=True, null=True, blank=True
    )
    date_created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-date_created", "-id")
        indexes = [
            models.Index(
                fields=("balance", "date_created"), name="stock_move_balance_date"
            ),
            models.Index(fields=("source_type", "source_id"), name="stock_move_source"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_("Un mouvement de stock validé est immuable."))
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            _("Un mouvement de stock validé ne peut pas être supprimé.")
        )


class StockReceipt(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_VALIDATED = "validated"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Brouillon")),
        (STATUS_VALIDATED, _("Validée")),
        (STATUS_CANCELLED, _("Annulée")),
    ]

    company = models.ForeignKey(
        "company.Company", on_delete=models.PROTECT, related_name="stock_receipts"
    )
    logistics_order = models.ForeignKey(
        "logistique.LogisticsOrder",
        on_delete=models.PROTECT,
        related_name="stock_receipts",
    )
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    reference = models.CharField(max_length=80, blank=True, default="")
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_receipts_created",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_receipts_validated",
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_validated = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-date_created",)


class StockReceiptLine(models.Model):
    receipt = models.ForeignKey(
        StockReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    logistics_line = models.ForeignKey(
        "logistique.LogisticsOrderLine",
        on_delete=models.PROTECT,
        related_name="receipt_lines",
    )
    article = models.ForeignKey("article.Article", on_delete=models.PROTECT)
    emplacement = models.ForeignKey("parameter.Emplacement", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("receipt", "logistics_line"),
                name="unique_receipt_logistics_line",
            )
        ]


class InventorySession(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_VALIDATED = "validated"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Brouillon")),
        (STATUS_VALIDATED, _("Validé")),
        (STATUS_CANCELLED, _("Annulé")),
    ]

    company = models.ForeignKey(
        "company.Company", on_delete=models.PROTECT, related_name="stock_inventories"
    )
    emplacement = models.ForeignKey(
        "parameter.Emplacement",
        on_delete=models.PROTECT,
        related_name="stock_inventories",
    )
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    reference = models.CharField(max_length=80, blank=True, default="")
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventories_created",
    )
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventories_validated",
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_validated = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-date_created",)


class InventoryLine(models.Model):
    inventory = models.ForeignKey(
        InventorySession, on_delete=models.CASCADE, related_name="lines"
    )
    article = models.ForeignKey("article.Article", on_delete=models.PROTECT)
    expected_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    counted_quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("inventory", "article"), name="unique_inventory_article"
            )
        ]


class LowStockAlert(models.Model):
    balance = models.OneToOneField(
        StockBalance, on_delete=models.CASCADE, related_name="low_stock_alert"
    )
    active = models.BooleanField(default=True)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    recovered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-first_detected_at",)
