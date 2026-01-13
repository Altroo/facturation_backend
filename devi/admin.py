from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from core.admin import BaseDocumentAdmin, BaseDocumentLineInline
from .models import Devi, DeviLine


class DeviLineInline(BaseDocumentLineInline):
    """Inline admin for DeviLine within Devi."""

    model = DeviLine


class DeviAdmin(BaseDocumentAdmin):
    """Admin configuration for the Devi model."""

    inlines = [DeviLineInline]

    def get_numero_field_name(self):
        return "numero_devis"

    def get_date_field_name(self):
        return "date_devis"

    list_display = (
        "numero_devis",
        "client",
        "date_devis",
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
        "numero_devis",
        "client__raison_sociale",
        "client__code_client",
        "numero_demande_prix_client",
        "remarque",
    )
    fieldsets = (
        (
            "Informations principales",
            {
                "fields": (
                    "numero_devis",
                    "client",
                    "date_devis",
                    "statut",
                )
            },
        ),
        (
            "Détails",
            {
                "fields": (
                    "numero_demande_prix_client",
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


class DeviLineAdmin(SimpleHistoryAdmin):
    """Admin configuration for the DeviLine model."""

    list_display = (
        "devis_numero",
        "article_reference",
        "article_designation",
        "prix_achat",
        "prix_vente",
        "quantity",
        "remise_type",
        "remise",
    )
    list_filter = ("devis__statut", "article")
    search_fields = (
        "devis__numero_devis",
        "article__reference",
        "article__designation",
    )
    list_select_related = ("devis", "devis__client", "article")
    autocomplete_fields = ("article", "devis")

    fieldsets = (
        (
            "Devis",
            {"fields": ("devis",)},
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

    @admin.display(description="Numéro devis", ordering="devis__numero_devis")
    def devis_numero(self, obj):
        return obj.devis.numero_devis

    @admin.display(description="Référence", ordering="article__reference")
    def article_reference(self, obj):
        return obj.article.reference

    @admin.display(description="Désignation", ordering="article__designation")
    def article_designation(self, obj):
        return obj.article.designation


admin.site.register(Devi, DeviAdmin)
admin.site.register(DeviLine, DeviLineAdmin)
