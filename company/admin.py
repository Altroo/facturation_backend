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
        "date_created",
        "date_updated",
    )
    list_filter = ("civilite_responsable", "nbr_employe", "suspended")
    search_fields = (
        "raison_sociale",
        "email",
        "nom_responsable",
        "ICE",
        "registre_de_commerce",
    )
    readonly_fields = ("date_created", "date_updated")
    inlines = [MembershipInline]


admin.site.register(Company, CompanyAdmin)
