from django.contrib import admin

from .models import (
    InventoryLine,
    InventorySession,
    LowStockAlert,
    StockBalance,
    StockMovement,
    StockReceipt,
    StockReceiptLine,
    StockReservation,
)


class StockBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "emplacement",
        "physical_quantity",
        "reserved_quantity",
        "date_updated",
    )
    list_filter = ("company", "emplacement")
    search_fields = ("article__reference", "article__designation")
    list_select_related = ("company", "article", "emplacement")


class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "date_created",
        "balance",
        "movement_type",
        "quantity",
        "balance_after",
        "actor",
    )
    # noinspection PyUnresolvedReferences
    list_filter = ("movement_type", "balance__company")
    # noinspection PyUnresolvedReferences
    search_fields = ("balance__article__reference", "note", "idempotency_key")
    readonly_fields = [field.name for field in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockReceiptLineInline(admin.TabularInline):
    model = StockReceiptLine
    extra = 0


class StockReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reference",
        "company",
        "logistics_order",
        "status",
        "date_created",
    )
    list_filter = ("company", "status")
    inlines = (StockReceiptLineInline,)


class InventoryLineInline(admin.TabularInline):
    model = InventoryLine
    extra = 0


class InventorySessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reference",
        "company",
        "emplacement",
        "status",
        "date_created",
    )
    list_filter = ("company", "status")
    inlines = (InventoryLineInline,)


admin.site.register(StockBalance, StockBalanceAdmin)
admin.site.register(StockMovement, StockMovementAdmin)
admin.site.register(StockReceipt, StockReceiptAdmin)
admin.site.register(InventorySession, InventorySessionAdmin)
admin.site.register(StockReservation)
admin.site.register(LowStockAlert)
