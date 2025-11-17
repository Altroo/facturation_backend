from django.contrib import admin

from .models import Ville


class VilleAdmin(admin.ModelAdmin):
    """Admin configuration for the Ville model."""

    list_display = ("id", "nom")
    search_fields = ("nom",)


# Ville
admin.site.register(Ville, VilleAdmin)
