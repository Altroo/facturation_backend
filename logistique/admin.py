from django.contrib import admin

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
    readonly_fields = ("user", "action", "old_value", "new_value", "note", "date_created")


@admin.register(LogisticsOrder)
class LogisticsOrderAdmin(admin.ModelAdmin):
    list_display = (
        "numero_commande",
        "company",
        "fournisseur",
        "marque",
        "statut",
        "statut_paiement",
        "cout_total",
        "date_created",
    )
    list_filter = ("company", "statut", "statut_paiement", "marque")
    search_fields = ("numero_commande", "fournisseur", "marque__nom")
    inlines = [LogisticsOrderProformaInline, LogisticsOrderLineInline, LogisticsOrderEventInline]


@admin.register(LogisticsOrderEvent)
class LogisticsOrderEventAdmin(admin.ModelAdmin):
    list_display = ("commande", "action", "user", "date_created")
    search_fields = ("commande__numero_commande", "action", "note")
