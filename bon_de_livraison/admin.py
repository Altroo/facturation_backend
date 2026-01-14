from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from core.admin import BaseDocumentAdmin, BaseDocumentLineInline
from .models import BonDeLivraison, BonDeLivraisonLine


class BonDeLivraisonLineInline(BaseDocumentLineInline):
    """Inline admin for BonDeLivraisonLine within BonDeLivraison."""

    model = BonDeLivraisonLine


class BonDeLivraisonAdmin(BaseDocumentAdmin):
    """Admin configuration for the BonDeLivraison model."""

    inlines = [BonDeLivraisonLineInline]

    def get_numero_field_name(self):
        return "numero_bon_livraison"

    def get_date_field_name(self):
        return "date_bon_livraison"

    list_display = (
        "numero_bon_livraison",
        "client",
        "date_bon_livraison",
        "statut_badge",
        "mode_paiement",
        "livre_par",
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
        "numero_bon_livraison",
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
                    "numero_bon_livraison",
                    "client",
                    "date_bon_livraison",
                    "statut",
                )
            },
        ),
        (
            "Détails",
            {
                "fields": (
                    "numero_bon_commande_client",
                    "livre_par",
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


class BonDeLivraisonLineAdmin(SimpleHistoryAdmin):
    """Admin configuration for the BonDeLivraisonLine model."""

    list_display = (
        "bon_de_livraison_numero",
        "article_reference",
        "article_designation",
        "prix_achat",
        "prix_vente",
        "quantity",
        "remise_type",
        "remise",
    )
    list_filter = ("bon_de_livraison__statut", "article")
    search_fields = (
        "bon_de_livraison__numero_bon_livraison",
        "article__reference",
        "article__designation",
    )
    list_select_related = ("bon_de_livraison", "bon_de_livraison__client", "article")
    autocomplete_fields = ("article", "bon_de_livraison")

    fieldsets = (
        (
            "Bon de Livraison",
            {"fields": ("bon_de_livraison",)},
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
        description="Numéro bon de livraison",
        ordering="bon_de_livraison__numero_bon_livraison",
    )
    def bon_de_livraison_numero(self, obj):
        return obj.bon_de_livraison.numero_bon_livraison

    @admin.display(description="Référence", ordering="article__reference")
    def article_reference(self, obj):
        return obj.article.reference

    @admin.display(description="Désignation", ordering="article__designation")
    def article_designation(self, obj):
        return obj.article.designation


# Historical Model Admins (Read-only)
class HistoricalBonDeLivraisonAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical BonDeLivraison records."""
    
    list_display = (
        "history_id",
        "id",
        "numero_bon_livraison",
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
        "numero_bon_livraison",
        "client__raison_sociale",
    )
    
    readonly_fields = [field.name for field in BonDeLivraison._meta.get_fields() if hasattr(field, 'name') and not field.many_to_many and not field.one_to_many] + [
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


class HistoricalBonDeLivraisonLineAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical BonDeLivraisonLine records."""
    
    list_display = (
        "history_id",
        "id",
        "bon_de_livraison",
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
        "bon_de_livraison__numero_bon_livraison",
        "article__reference",
    )
    
    readonly_fields = [field.name for field in BonDeLivraisonLine._meta.get_fields() if hasattr(field, 'name') and not field.many_to_many and not field.one_to_many] + [
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


admin.site.register(BonDeLivraison, BonDeLivraisonAdmin)
admin.site.register(BonDeLivraisonLine, BonDeLivraisonLineAdmin)
admin.site.register(BonDeLivraison.history.model, HistoricalBonDeLivraisonAdmin)
admin.site.register(BonDeLivraisonLine.history.model, HistoricalBonDeLivraisonLineAdmin)
