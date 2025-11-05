from django.contrib import admin

from .models import Company


class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "raison_sociale",
        "email",
        "civilite_responsable",
        "nom_responsable",
        "site_web",
        "ICE",
        "date_created",
    )
    list_filter = ("civilite_responsable", "nbr_employe")
    search_fields = (
        "raison_sociale",
        "email",
        "nom_responsable",
        "ICE",
        "registre_de_commerce",
    )
    readonly_fields = ("date_created",)


admin.site.register(Company, CompanyAdmin)
