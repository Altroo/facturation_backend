from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from core.admin import BaseDocumentAdmin, BaseDocumentLineInline
from .models import FactureProForma, FactureProFormaLine


class FactureProFormaLineInline(BaseDocumentLineInline):
    """Inline admin for FactureProFormaLine within FactureProForma."""

    model = FactureProFormaLine


class FactureProFormaAdmin(BaseDocumentAdmin):
    """Admin configuration for the FactureProForma model."""

    inlines = [FactureProFormaLineInline]

    def get_numero_field_name(self):
        return "numero_facture"

    def get_date_field_name(self):
        return "date_facture"

    list_display = (
        "numero_facture",
        "client",
        "date_facture",
        "statut_badge",
        "mode_paiement",
        "display_remise",
        "display_lignes_count",
        "display_total_ht",
        "display_total_tva",
        "display_total_ttc",
        "display_total_ttc_apres_remise",
        "date_created",
        "created_by_user",
    )
    search_fields = (
        "numero_facture",
        "client__raison_sociale",
        "client__code_client",
        "numero_bon_commande_client",
        "remarque",
    )
    fieldsets = (
        (
            "Informations principales",
            {
                "fields": (
                    "numero_facture",
                    "client",
                    "date_facture",
                    "statut",
                )
            },
        ),
        (
            "Détails",
            {
                "fields": (
                    "numero_bon_commande_client",
                    "mode_paiement",
                    "remarque",
                    "remise_type",
                    "remise",
                )
            },
        ),
        (
            "Totaux (calculés)",
            {
                "fields": (
                    "display_total_ht",  # type: ignore[attr-defined]
                    "display_total_tva",  # type: ignore[attr-defined]
                    "display_total_ttc",  # type: ignore[attr-defined]
                    "display_total_ttc_apres_remise",  # type: ignore[attr-defined]
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_by_user",
                    "date_created",
                    "date_updated",
                ),
                "classes": ("collapse",),
            },
        ),
    )


class FactureProFormaLineAdmin(SimpleHistoryAdmin):
    """Admin configuration for the FactureProFormaLine model."""

    list_display = (
        "numero_facture",
        "article_reference",
        "article_designation",
        "prix_achat",
        "prix_vente",
        "quantity",
        "remise_type",
        "remise",
    )
    list_filter = ("facture_pro_forma__statut", "article")
    search_fields = (
        "facture_pro_forma__numero_facture",
        "article__reference",
        "article__designation",
    )
    list_select_related = ("facture_pro_forma", "facture_pro_forma__client", "article")
    autocomplete_fields = ("article", "facture_pro_forma")

    fieldsets = (
        (
            "FactureProForma",
            {"fields": ("facture_pro_forma",)},
        ),
        (
            "Article",
            {"fields": ("article", "quantity")},
        ),
        (
            "Prix & Remise",
            {
                "fields": (
                    "prix_achat",
                    "prix_vente",
                    "remise_type",
                    "remise",
                )
            },
        ),
    )

    @admin.display(
        description="Numéro facture", ordering="facture_pro_forma__numero_facture"
    )
    def numero_facture(self, obj):
        return obj.facture_pro_forma.numero_facture

    @admin.display(description="Référence", ordering="article__reference")
    def article_reference(self, obj):
        return obj.article.reference

    @admin.display(description="Désignation", ordering="article__designation")
    def article_designation(self, obj):
        return obj.article.designation


# Historical Model Admins (Read-only)
class HistoricalFactureProFormaAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical FactureProForma records."""

    list_display = (
        "history_id",
        "id",
        "numero_facture",
        "client",
        "statut",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = (
        "history_type",
        "history_date",
        "statut",
    )

    search_fields = (
        "numero_facture",
        "client__raison_sociale",
    )

    readonly_fields = [
        field.name
        for field in FactureProForma._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalFactureProFormaLineAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical FactureProFormaLine records."""

    list_display = (
        "history_id",
        "id",
        "facture_pro_forma",
        "article",
        "quantity",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = (
        "history_type",
        "history_date",
    )

    search_fields = (
        "facture_pro_forma__numero_facture",
        "article__reference",
    )

    readonly_fields = [
        field.name
        for field in FactureProFormaLine._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


admin.site.register(FactureProForma, FactureProFormaAdmin)
admin.site.register(FactureProFormaLine, FactureProFormaLineAdmin)
admin.site.register(FactureProForma.history.model, HistoricalFactureProFormaAdmin)
admin.site.register(
    FactureProFormaLine.history.model, HistoricalFactureProFormaLineAdmin
)
