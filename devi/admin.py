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
    # remove from admin form
    exclude = ("created_by_user",)
    list_select_related = ("client", "created_by_user")
    autocomplete_fields = ("client", "mode_paiement")

    def save_model(self, request, obj, form, change):
        # when creating, set the creator automatically
        if not change or not getattr(obj, "created_by_user", None):
            obj.created_by_user = request.user
        super().save_model(request, obj, form, change)


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
