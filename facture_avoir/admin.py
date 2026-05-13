from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import BaseDocumentAdmin, BaseDocumentLineInline
from .models import FactureAvoir, FactureAvoirLine


class FactureAvoirLineInline(BaseDocumentLineInline):
    model = FactureAvoirLine


class FactureAvoirAdmin(BaseDocumentAdmin):
    inlines = [FactureAvoirLineInline]

    def get_numero_field_name(self):
        return "numero_avoir"

    def get_date_field_name(self):
        return "date_avoir"

    list_display = (
        "numero_avoir",
        "company",
        "client",
        "facture_origine",
        "date_avoir",
        "motif_avoir",
        "statut_badge",
        "display_total_ttc_apres_remise",
        "created_by_user",
    )
    search_fields = (
        "numero_avoir",
        "facture_origine__numero_facture",
        "client__raison_sociale",
        "client__code_client",
        "remarque",
    )
    list_filter = ("statut", "motif_avoir", "company", "date_avoir")
    readonly_fields = (
        "numero_avoir",
        "display_total_ht",
        "display_total_tva",
        "display_total_ttc",
        "display_total_ttc_apres_remise",
        "date_created",
        "date_updated",
    )
    fieldsets = (
        (
            _("Informations principales"),
            {
                "fields": (
                    "numero_avoir",
                    "company",
                    "client",
                    "facture_origine",
                    "date_avoir",
                    "motif_avoir",
                    "statut",
                )
            },
        ),
        (
            _("Détails"),
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
            _("Totaux (à déduire)"),
            {
                "fields": (
                    "display_total_ht",
                    "display_total_tva",
                    "display_total_ttc",
                    "display_total_ttc_apres_remise",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Métadonnées"),
            {
                "fields": ("created_by_user", "date_created", "date_updated"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_delete_permission(self, request, obj=None):
        return False


class FactureAvoirLineAdmin(admin.ModelAdmin):
    list_display = (
        "numero_avoir",
        "article_reference",
        "article_designation",
        "prix_achat",
        "prix_vente",
        "quantity",
        "remise_type",
        "remise",
    )
    search_fields = (
        "facture_avoir__numero_avoir",
        "article__reference",
        "article__designation",
    )
    list_select_related = ("facture_avoir", "facture_avoir__client", "article")
    autocomplete_fields = ("article", "facture_avoir")

    @admin.display(description=_("Numéro avoir"), ordering="facture_avoir__numero_avoir")
    def numero_avoir(self, obj):
        return obj.facture_avoir.numero_avoir

    @admin.display(description=_("Référence"), ordering="article__reference")
    def article_reference(self, obj):
        return obj.article.reference

    @admin.display(description=_("Désignation"), ordering="article__designation")
    def article_designation(self, obj):
        return obj.article.designation


admin.site.register(FactureAvoir, FactureAvoirAdmin)
admin.site.register(FactureAvoirLine, FactureAvoirLineAdmin)
