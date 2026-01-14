from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Client


class ClientAdmin(SimpleHistoryAdmin):
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


# Historical Model Admin (Read-only)
class HistoricalClientAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Client records."""
    
    list_display = (
        "history_id",
        "id",
        "code_client",
        "raison_sociale",
        "email",
        "archived",
        "history_type",
        "history_date",
        "history_user",
    )
    
    list_filter = (
        "history_type",
        "history_date",
        "archived",
        "client_type",
    )
    
    search_fields = (
        "code_client",
        "raison_sociale",
        "nom",
        "prenom",
        "email",
    )
    
    readonly_fields = [field.name for field in Client._meta.get_fields() if hasattr(field, 'name') and not field.many_to_many and not field.one_to_many] + [
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


admin.site.register(Client.history.model, HistoricalClientAdmin)
