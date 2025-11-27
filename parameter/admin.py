from django.contrib import admin

from .models import Ville, Marque, Categorie, Unite, Emplacement


class VilleAdmin(admin.ModelAdmin):
    """Admin configuration for the Ville model."""

    list_display = ("id", "nom")
    search_fields = ("nom",)


class MarqueAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


class CategorieAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


class UniteAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


class EmplacementAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


# Register models
admin.site.register(Ville, VilleAdmin)
admin.site.register(Marque, MarqueAdmin)
admin.site.register(Categorie, CategorieAdmin)
admin.site.register(Unite, UniteAdmin)
admin.site.register(Emplacement, EmplacementAdmin)
