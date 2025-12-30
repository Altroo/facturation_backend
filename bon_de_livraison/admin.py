from django.contrib import admin

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


class BonDeLivraisonLineAdmin(admin.ModelAdmin):
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


admin.site.register(BonDeLivraison, BonDeLivraisonAdmin)
admin.site.register(BonDeLivraisonLine, BonDeLivraisonLineAdmin)
