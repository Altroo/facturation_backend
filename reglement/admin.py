from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import Reglement

# Facture statuses that allow règlement creation
ALLOWED_FACTURE_STATUSES = ["Envoyé", "Accepté"]


class ReglementAdminForm(forms.ModelForm):
    """Form with validation for Reglement admin."""

    class Meta:
        model = Reglement
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        facture_client = cleaned_data.get("facture_client")
        montant = cleaned_data.get("montant")
        statut = cleaned_data.get("statut")

        if facture_client:
            # Validate facture status
            if facture_client.statut not in ALLOWED_FACTURE_STATUSES:
                raise forms.ValidationError(
                    {
                        "facture_client": _("Impossible d'ajouter un règlement pour une facture "
                        "avec le statut '%(statut)s'. "
                        "Statuts autorisés: %(statuts_autorises)s.") % {
                            "statut": facture_client.statut,
                            "statuts_autorises": ", ".join(ALLOWED_FACTURE_STATUSES),
                        }
                    }
                )

            if montant:
                # For updates, exclude current instance from calculation
                exclude_id = (
                    self.instance.pk if self.instance and self.instance.pk else None
                )

                # Only validate if status is "Valide" (canceled payments don't count)
                if statut == "Valide":
                    reste_a_payer = Reglement.get_reste_a_payer(
                        facture_client, exclude_id
                    )

                    if montant > reste_a_payer:
                        raise forms.ValidationError(
                            {
                                "montant": _("Le montant (%(montant)s MAD) dépasse le reste à payer "
                                "(%(reste_a_payer)s MAD) pour cette facture.") % {
                                    "montant": montant,
                                    "reste_a_payer": reste_a_payer,
                                }
                            }
                        )

        if montant is not None and montant <= 0:
            raise forms.ValidationError(
                {"montant": _("Le montant doit être supérieur à 0.")}
            )

        return cleaned_data


class ReglementAdmin(SimpleHistoryAdmin):
    """Admin configuration for the Reglement model."""

    form = ReglementAdminForm

    list_display = (
        "id",
        "facture_client",
        "client_name",
        "mode_reglement",
        "libelle",
        "montant",
        "date_reglement",
        "date_echeance",
        "statut_badge",
        "date_created",
    )

    list_filter = (
        "statut",
        "mode_reglement",
        "date_reglement",
        "date_echeance",
    )

    search_fields = (
        "libelle",
        "facture_client__numero_facture",
        "facture_client__client__raison_sociale",
    )

    readonly_fields = (
        "date_created",
        "date_updated",
    )

    fieldsets = (
        (
            _("Informations principales"),
            {
                "fields": (
                    "facture_client",
                    "mode_reglement",
                    "libelle",
                    "montant",
                )
            },
        ),
        (
            _("Dates"),
            {
                "fields": (
                    "date_reglement",
                    "date_echeance",
                )
            },
        ),
        (
            _("Statut"),
            {"fields": ("statut",)},
        ),
        (
            _("Métadonnées"),
            {
                "fields": (
                    "date_created",
                    "date_updated",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def client_name(self, obj):
        """Display client name from facture."""
        return obj.facture_client.client.raison_sociale

    client_name.short_description = _("Client")
    client_name.admin_order_field = "facture_client__client__raison_sociale"

    def statut_badge(self, obj):
        """Display status with colored badge."""
        colors = {
            "Valide": "#28a745",
            "Annulé": "#dc3545",
        }
        color = colors.get(obj.statut, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.statut,
        )

    statut_badge.short_description = _("Statut")
    statut_badge.admin_order_field = "statut"


# Historical Model Admin (Read-only)
class HistoricalReglementAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Reglement records."""

    list_display = (
        "history_id",
        "id",
        "facture_client",
        "montant",
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
        "id",
        "libelle",
        "facture_client__numero_facture",
    )

    readonly_fields = [
        field.name
        for field in Reglement._meta.get_fields()
        if not field.many_to_many and not field.one_to_many
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


# Register models
admin.site.register(Reglement, ReglementAdmin)
admin.site.register(Reglement.history.model, HistoricalReglementAdmin)
