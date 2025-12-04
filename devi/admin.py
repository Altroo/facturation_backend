from django.contrib import admin
from django.utils.html import format_html

from .models import Devi, DeviLine


class DeviLineInline(admin.TabularInline):
    """Inline admin for DeviLine within Devi."""

    model = DeviLine
    extra = 1
    autocomplete_fields = ("article",)
    fields = (
        "article",
        "prix_achat",
        "prix_vente",
        "quantity",
        "pourcentage_remise",
    )

    def get_readonly_fields(self, request, obj=None):
        # If devi is in certain statuses, make lines readonly
        if obj and obj.statut in ("Accepté", "Refusé", "Annulé"):
            return self.fields
        return ()


class DeviAdmin(admin.ModelAdmin):
    """Admin configuration for the Devi model."""

    list_display = (
        "numero_devis",
        "client",
        "date_devis",
        "statut_badge",
        "mode_paiement",
        "display_lignes_count",
        "date_created",
        "created_by_user",
    )
    list_filter = (
        "statut",
        "date_devis",
        "date_created",
        "mode_paiement",
    )
    search_fields = (
        "numero_devis",
        "client__raison_sociale",
        "client__code_client",
        "numero_demande_prix_client",
        "remarque",
    )
    inlines = [DeviLineInline]
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
                )
            },
        ),
        (
            "Métadonnées",
            {
                # include computed field in fieldsets only if it's readonly
                "fields": (
                    "created_by_user",
                    "date_created",
                    "date_updated",
                ),
                "classes": ("collapse",),
            },
        ),
    )
    list_select_related = ("client", "created_by_user", "mode_paiement")
    autocomplete_fields = ("client", "mode_paiement")
    date_hierarchy = "date_devis"

    # Make computed and system fields readonly at class-level so Django can resolve them in fieldsets
    readonly_fields = (
        "date_created",
        "date_updated",
        "created_by_user",
        "display_lignes_count",
    )

    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly based on status."""
        readonly = list(self.readonly_fields)

        # If devi is accepted/refused/cancelled, make key fields readonly
        if obj and obj.statut in ("Accepté", "Refusé", "Annulé"):
            readonly.extend(["numero_devis", "client", "date_devis"])

        return readonly

    def save_model(self, request, obj, form, change):
        """Set the creator automatically when creating."""
        if not change or not getattr(obj, "created_by_user", None):
            obj.created_by_user = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Statut", ordering="statut")
    def statut_badge(self, obj):
        colors = {
            "Brouillon": "#6c757d",
            "Envoyé": "#0dcaf0",
            "Accepté": "#198754",
            "Refusé": "#dc3545",
            "Annulé": "#6c757d",
            "Expiré": "#ffc107",
        }
        color = colors.get(obj.statut, "#6c757d")
        # false warning, already in kwargs
        return format_html(
            '<span style="background-color: {color}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{status}</span>',
            color=color,
            status=obj.statut,
        )

    @admin.display(description="Nombre de lignes")
    def display_lignes_count(self, obj):
        """Display the number of lines."""
        if obj and obj.pk:
            return obj.lignes.count()
        return 0


class DeviLineAdmin(admin.ModelAdmin):
    """Admin configuration for the DeviLine model."""

    list_display = (
        "devis_numero",
        "article_reference",
        "article_designation",
        "prix_achat",
        "prix_vente",
        "quantity",
        "pourcentage_remise",
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
            "Prix",
            {
                "fields": (
                    "prix_achat",
                    "prix_vente",
                    "pourcentage_remise",
                )
            },
        ),
    )

    @admin.display(description="Numéro devis", ordering="devis__numero_devis")
    def devis_numero(self, obj):
        """Display devis numero."""
        return obj.devis.numero_devis

    @admin.display(description="Référence", ordering="article__reference")
    def article_reference(self, obj):
        """Display article reference."""
        return obj.article.reference

    @admin.display(description="Désignation", ordering="article__designation")
    def article_designation(self, obj):
        """Display article designation."""
        return obj.article.designation


admin.site.register(Devi, DeviAdmin)
admin.site.register(DeviLine, DeviLineAdmin)
