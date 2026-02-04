from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group
from simple_history.admin import SimpleHistoryAdmin

from account.models import Membership
from .models import Company


class MembershipInlineForm(forms.ModelForm):
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label="Role",
    )

    class Meta:
        model = Membership
        fields = ("user", "role")


class MembershipInline(admin.TabularInline):
    model = Membership
    form = MembershipInlineForm
    extra = 1
    fields = ("user", "role")
    autocomplete_fields = ("user",)
    verbose_name = "Manager"
    verbose_name_plural = "Managers"


class CompanyAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "raison_sociale",
        "email",
        "civilite_responsable",
        "nom_responsable",
        "site_web",
        "ICE",
        "suspended",
        "uses_foreign_currency",
        "date_created",
        "date_updated",
    )
    list_filter = ("civilite_responsable", "nbr_employe", "suspended", "uses_foreign_currency")
    search_fields = (
        "raison_sociale",
        "email",
        "nom_responsable",
        "ICE",
        "registre_de_commerce",
    )
    readonly_fields = ("date_created", "date_updated")
    inlines = [MembershipInline]


# Historical Model Admin (Read-only)
class HistoricalCompanyAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Company records."""

    list_display = (
        "history_id",
        "id",
        "raison_sociale",
        "email",
        "ICE",
        "suspended",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = (
        "history_type",
        "history_date",
        "suspended",
    )

    search_fields = (
        "raison_sociale",
        "email",
        "ICE",
    )

    readonly_fields = [
        field.name
        for field in Company._meta.get_fields()
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


admin.site.register(Company, CompanyAdmin)
admin.site.register(Company.history.model, HistoricalCompanyAdmin)
