from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    LogisticsOrder,
    LogisticsOrderEvent,
    LogisticsOrderLine,
    LogisticsOrderProforma,
)


class LogisticsOrderLineInline(admin.TabularInline):
    model = LogisticsOrderLine
    extra = 0
    readonly_fields = (
        "proforma",
        "client",
        "article",
        "article_reference",
        "designation",
        "quantity",
        "prix_achat",
        "total_achat",
    )


class LogisticsOrderProformaInline(admin.TabularInline):
    model = LogisticsOrderProforma
    extra = 0
    readonly_fields = ("proforma", "date_created")


class LogisticsOrderEventInline(admin.TabularInline):
    model = LogisticsOrderEvent
    extra = 0
    readonly_fields = (
        "user",
        "action",
        "old_value",
        "new_value",
        "note",
        "date_created",
    )


@admin.register(LogisticsOrder)
class LogisticsOrderAdmin(SimpleHistoryAdmin):
    list_display = (
        "numero_commande",
        "company",
        "marque",
        "statut",
        "statut_paiement",
        "cout_total",
        "date_created",
    )
    list_filter = ("company", "statut", "statut_paiement", "marque")
    search_fields = ("numero_commande", "marque__nom")
    inlines = [
        LogisticsOrderProformaInline,
        LogisticsOrderLineInline,
        LogisticsOrderEventInline,
    ]


# Historical Model Admin (Read-only)
class HistoricalLogisticsOrderAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical LogisticsOrder records."""

    list_display = (
        "history_id",
        "id",
        "numero_commande",
        "company",
        "marque",
        "statut",
        "statut_paiement",
        "history_type",
        "history_date",
        "history_user",
    )
    list_filter = (
        "history_type",
        "history_date",
        "company",
        "statut",
        "statut_paiement",
    )
    search_fields = ("numero_commande", "marque__nom")
    readonly_fields = [
        field.name
        for field in LogisticsOrder._meta.get_fields()
        if hasattr(field, "name")
        and not field.many_to_many
        and not field.one_to_many
        and not field.one_to_one
        and not field.related_model
    ] + [
        "history_id",
        "history_date",
        "history_change_reason",
        "history_type",
        "history_user",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LogisticsOrderEvent)
class LogisticsOrderEventAdmin(admin.ModelAdmin):
    list_display = ("commande", "action", "user", "date_created")
    search_fields = ("commande__numero_commande", "action", "note")


admin.site.register(LogisticsOrder.history.model, HistoricalLogisticsOrderAdmin)
