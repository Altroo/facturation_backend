from django.contrib import admin

from .models import Devi, DeviLine


class DeviLineInline(admin.TabularInline):
    """Inline admin for DeviLine within Devi."""

    model = DeviLine
    extra = 1
    autocomplete_fields = ("article",)


class DeviAdmin(admin.ModelAdmin):
    """Admin configuration for the Devi model."""

    list_display = (
        "numero_devis",
        "client",
        "date_devis",
        "statut",
        "date_created",
        "created_by_user",
    )
    list_filter = ("statut", "date_devis", "client")
    search_fields = (
        "numero_devis",
        "client__raison_sociale",
        "numero_demande_prix_client",
    )
    inlines = [DeviLineInline]
    readonly_fields = ("date_created", "date_updated")
    list_select_related = ("client", "created_by_user")
    autocomplete_fields = ("client", "created_by_user", "mode_paiement")


class DeviLineAdmin(admin.ModelAdmin):
    """Admin configuration for the DeviLine model."""

    list_display = (
        "devis",
        "article",
        "prix_vente",
        "quantity",
        "pourcentage_remise",
    )
    list_filter = ("devis", "article")
    search_fields = ("devis__numero_devis", "article__reference")
    list_select_related = ("devis", "article")
    autocomplete_fields = ("article", "devis")


admin.site.register(Devi, DeviAdmin)
admin.site.register(DeviLine, DeviLineAdmin)
