from django.contrib import admin

from core.admin import BaseDocumentAdmin, BaseDocumentLineInline
from .models import FactureClient, FactureClientLine


class FactureClientLineInline(BaseDocumentLineInline):
    """Inline admin for FactureClientLine within FactureClient."""

    model = FactureClientLine


class FactureClientAdmin(BaseDocumentAdmin):
    """Admin configuration for the FactureClient model."""

    inlines = [FactureClientLineInline]

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


class FactureClientLineAdmin(admin.ModelAdmin):
    """Admin configuration for the FactureClientLine model."""

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
    list_filter = ("facture_client__statut", "article")
    search_fields = (
        "facture_client__numero_facture",
        "article__reference",
        "article__designation",
    )
    list_select_related = ("facture_client", "facture_client__client", "article")
    autocomplete_fields = ("article", "facture_client")

    fieldsets = (
        (
            "FactureClient",
            {"fields": ("facture_client",)},
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
        description="Numéro facture", ordering="facture_client__numero_facture"
    )
    def numero_facture(self, obj):
        return obj.facture_client.numero_facture

    @admin.display(description="Référence", ordering="article__reference")
    def article_reference(self, obj):
        return obj.article.reference

    @admin.display(description="Désignation", ordering="article__designation")
    def article_designation(self, obj):
        return obj.article.designation


admin.site.register(FactureClient, FactureClientAdmin)
admin.site.register(FactureClientLine, FactureClientLineAdmin)
