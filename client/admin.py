from django.contrib import admin

from .models import Client


class ClientAdmin(admin.ModelAdmin):
    """Admin configuration for the Client model."""

    list_display = (
        "id",
        "code_client",
        "client_type",
        "raison_sociale",
        "nom",
        "prenom",
        "email",
        "ville",
        "company",
        "archived",
        "date_created",
        "date_updated",
    )
    list_filter = ("client_type", "ville", "company", "archived")
    search_fields = (
        "code_client",
        "raison_sociale",
        "nom",
        "prenom",
        "email",
        "ICE",
        "registre_de_commerce",
    )
    readonly_fields = ("date_created", "date_updated")


# Client
admin.site.register(Client, ClientAdmin)
