from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site
from django.contrib.admin.sites import NotRegistered


class BaseDocumentLineInline(admin.TabularInline):
    """Abstract inline admin for document lines."""

    extra = 1
    autocomplete_fields = ("article",)
    fields = (
        "article",
        "prix_achat",
        "prix_vente",
        "quantity",
        "remise_type",
        "remise",
    )

    def get_readonly_fields(self, request, obj=None):
        """Make lines readonly if document is in certain statuses."""
        if obj and obj.statut in ("Accepté", "Refusé", "Annulé"):  # type: ignore[attr-defined]
            return self.fields
        return ()


# python
class BaseDocumentAdmin(SimpleHistoryAdmin):
    """Abstract admin for document models (Devi, FactureClient, FactureProForma)."""

    list_filter = (
        "statut",  # type: ignore[attr-defined]
        "date_created",  # type: ignore[attr-defined]
        "mode_paiement",  # type: ignore[attr-defined]
    )
    list_select_related = ("client", "created_by_user", "mode_paiement")
    autocomplete_fields = ("client", "mode_paiement")
    date_hierarchy = "date_created"

    readonly_fields = (
        "date_created",  # type: ignore[attr-defined]
        "date_updated",  # type: ignore[attr-defined]
        "created_by_user",  # type: ignore[attr-defined]
        "display_lignes_count",
        "display_total_ht",
        "display_total_tva",
        "display_total_ttc",
        "display_total_ttc_apres_remise",
    )

    def get_readonly_fields(self, request, obj=None):
        """Make certain fields readonly based on status."""
        readonly = list(self.readonly_fields)
        if obj and obj.statut in ("Accepté", "Refusé", "Annulé"):  # type: ignore[attr-defined]
            readonly.extend(
                [self.get_numero_field_name(), "client", self.get_date_field_name()]
            )
        return readonly

    def save_model(self, request, obj, form, change):
        """Set the creator automatically when creating."""
        if not change or not getattr(obj, "created_by_user", None):
            obj.created_by_user = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """Recalc totals once after saving related inline objects."""
        super().save_related(request, form, formsets, change)
        document = form.instance
        if document and document.pk:
            with transaction.atomic():
                document.recalc_totals()
                document.save(
                    update_fields=[
                        "total_ht",
                        "total_tva",
                        "total_ttc",
                        "total_ttc_apres_remise",
                    ]
                )

    def get_numero_field_name(self):
        """Return the numero field name. Override in subclasses."""
        raise NotImplementedError("Subclasses must define get_numero_field_name()")

    def get_date_field_name(self):
        """Return the date field name. Override in subclasses."""
        raise NotImplementedError("Subclasses must define get_date_field_name()")

    @admin.display(description="Statut", ordering="statut")
    def statut_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            "Brouillon": "#6c757d",
            "Envoyé": "#0dcaf0",
            "Accepté": "#198754",
            "Refusé": "#dc3545",
            "Annulé": "#6c757d",
            "Expiré": "#ffc107",
        }
        color = colors.get(obj.statut, "#6c757d")
        return format_html(
            '<span style="background-color: {color}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-weight: bold;">{status}</span>',
            color=color,
            status=obj.statut,
        )

    @admin.display(description="Remise", ordering="remise")
    def display_remise(self, obj):
        """Show remise as percent or formatted amount."""
        if not obj:
            return "-"
        if getattr(obj, "remise_type", None) == "Pourcentage":
            try:
                return f"{int(obj.remise)} %"
            except (TypeError, ValueError):
                return "-"
        # remise is already a Decimal with 2 decimals, don't divide by 100
        return f"{obj.remise:.2f} MAD"

    @admin.display(description="Nombre de lignes")
    def display_lignes_count(self, obj):
        """Display the number of lines."""
        if obj and obj.pk:
            return obj.lignes.count()
        return 0

    @admin.display(description="Total HT", ordering="total_ht")
    def display_total_ht(self, obj):
        if obj is None:
            return "-"
        return f"{obj.total_ht:.2f} MAD"

    @admin.display(description="Total TVA", ordering="total_tva")
    def display_total_tva(self, obj):
        if obj is None:
            return "-"
        return f"{obj.total_tva:.2f} MAD"

    @admin.display(description="Total TTC", ordering="total_ttc")
    def display_total_ttc(self, obj):
        if obj is None:
            return "-"
        return f"{obj.total_ttc:.2f} MAD"

    @admin.display(
        description="Total TTC après remise", ordering="total_ttc_apres_remise"
    )
    def display_total_ttc_apres_remise(self, obj):
        if obj is None:
            return "-"
        return f"{obj.total_ttc_apres_remise:.2f} MAD"

    class Meta:
        abstract = True


for model in (Group, Site):
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass
