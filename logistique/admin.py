from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    LogisticsOrder,
    LogisticsOrderEvent,
    LogisticsOrderLine,
    LogisticsOrderProforma,
    LogisticsPaymentInstallment,
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
    readonly_fields = (
        "user",
        "action",
        "old_value",
        "new_value",
        "note",
        "date_created",
    )


class LogisticsPaymentInstallmentInline(admin.TabularInline):
    model = LogisticsPaymentInstallment
    extra = 0
    can_delete = False
    readonly_fields = (
        "date_echeance",
        "montant_prevu",
        "devise",
        "statut_traitement",
        "date_paiement",
        "montant_paye",
        "banque",
        "reference_bancaire",
        "methode_paiement",
        "commentaire",
        "justificatif_file",
        "execution_enregistree_le",
        "execution_enregistree_par",
        "paiement_valide_le",
        "paiement_valide_par",
        "preuve_email_statut",
        "preuve_email_destinataire",
        "preuve_email_erreur",
        "preuve_email_tentatives",
        "preuve_email_task_id",
        "preuve_email_prise_en_charge_le",
        "preuve_email_file_token",
        "preuve_email_mise_en_file_le",
        "preuve_email_demandee_par",
        "preuve_envoyee_fournisseur_le",
        "reception_confirmee_le",
        "reception_confirmee_par",
        "date_created",
        "date_updated",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LogisticsOrder)
class LogisticsOrderAdmin(SimpleHistoryAdmin):
    readonly_fields = (
        "fournisseur",
        "fournisseur_email",
        "statut_global",
        "statut_commande_lancement",
        "proforma_demandee_le",
        "proforma_demandee_par",
        "statut_proforma_conformite",
        "proforma_controlee_le",
        "proforma_controlee_par",
        "proforma_validee_le",
        "proforma_validee_par",
        "date_validation_titre_importation",
        "statut_titre_importation",
        "statut_paiement",
        "statut_banque_paiement",
        "statut_traitement_paiement",
        "paiement_assigne_a",
        "demande_paiement_envoyee_le",
        "demande_paiement_envoyee_par",
        "demande_paiement_email_statut",
        "demande_paiement_email_destinataires",
        "demande_paiement_email_erreur",
        "demande_paiement_email_tentatives",
        "demande_paiement_email_task_id",
        "demande_paiement_email_prise_en_charge_le",
        "demande_paiement_email_file_token",
        "demande_paiement_email_mis_en_file_le",
        "paiement_valide_le",
        "paiement_valide_par",
        "date_paiement",
        "montant_paiement",
        "devise_paiement",
        "banque_paiement",
        "reference_paiement",
        "commentaire_paiement",
        "date_upload_swift",
        "swift_file",
        "swift_envoye_fournisseur_le",
        "paiement_confirme_reception_le",
        "paiement_confirme_reception_par",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.statut_paiement != "Non demandé":
            fields.extend(
                [
                    "numero_domiciliation",
                    "banque",
                    "montant_titre_importation",
                    "devise_titre_importation",
                    "date_titre_importation",
                    "titre_importation_file",
                    "methode_paiement",
                ]
            )
        return tuple(dict.fromkeys(fields))
    list_display = (
        "numero_commande",
        "company",
        "fournisseur",
        "statut_global",
        "statut_commande_lancement",
        "statut_proforma_conformite",
        "statut",
        "statut_paiement",
        "statut_banque_paiement",
        "statut_traitement_paiement",
        "cout_total",
        "date_created",
    )
    list_filter = (
        "company",
        "statut_global",
        "statut_commande_lancement",
        "statut_proforma_conformite",
        "statut_paiement",
        "statut_banque_paiement",
        "statut_traitement_paiement",
        "fournisseur",
    )
    search_fields = ("numero_commande", "fournisseur")
    inlines = [
        LogisticsOrderProformaInline,
        LogisticsOrderLineInline,
        LogisticsPaymentInstallmentInline,
        LogisticsOrderEventInline,
    ]


# Historical Model Admin (Read-only)
class HistoricalLogisticsOrderAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical LogisticsOrder records."""

    list_display = (
        "history_id",
        "id",
        "numero_commande",
        "company",
        "fournisseur",
        "statut",
        "statut_paiement",
        "history_type",
        "history_date",
        "history_user",
    )
    list_filter = (
        "history_type",
        "history_date",
        "company",
        "statut",
        "statut_paiement",
    )
    search_fields = ("numero_commande", "fournisseur")
    readonly_fields = [
        field.name
        for field in LogisticsOrder._meta.get_fields()
        if hasattr(field, "name")
        and not field.many_to_many
        and not field.one_to_many
        and not field.one_to_one
        and not field.related_model
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


@admin.register(LogisticsOrderEvent)
class LogisticsOrderEventAdmin(admin.ModelAdmin):
    list_display = ("commande", "action", "user", "date_created")
    search_fields = ("commande__numero_commande", "action", "note")


admin.site.register(LogisticsOrder.history.model, HistoricalLogisticsOrderAdmin)
