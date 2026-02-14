from django.contrib import admin

from .models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)


class VilleAdmin(admin.ModelAdmin):
    """Admin configuration for the Ville model."""

    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class MarqueAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class CategorieAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class UniteAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class EmplacementAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class ModePaiementAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


class LivreParAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "company")
    search_fields = ("nom",)
    list_filter = ("company",)


# Historical Model Admins (Read-only)
class HistoricalVilleAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Ville records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in Ville._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalMarqueAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Marque records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in Marque._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalCategorieAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Categorie records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in Categorie._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalUniteAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Unite records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in Unite._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalEmplacementAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Emplacement records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in Emplacement._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalModePaiementAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical ModePaiement records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in ModePaiement._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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


class HistoricalLivreParAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical LivrePar records."""

    list_display = (
        "history_id",
        "id",
        "nom",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = ("history_type", "history_date")
    search_fields = ("nom",)

    readonly_fields = [
        field.name
        for field in LivrePar._meta.get_fields()
        if hasattr(field, "name") and not field.many_to_many and not field.one_to_many
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
admin.site.register(Ville, VilleAdmin)
admin.site.register(Marque, MarqueAdmin)
admin.site.register(Categorie, CategorieAdmin)
admin.site.register(Unite, UniteAdmin)
admin.site.register(Emplacement, EmplacementAdmin)
admin.site.register(ModePaiement, ModePaiementAdmin)
admin.site.register(LivrePar, LivreParAdmin)
admin.site.register(Ville.history.model, HistoricalVilleAdmin)
admin.site.register(Marque.history.model, HistoricalMarqueAdmin)
admin.site.register(Categorie.history.model, HistoricalCategorieAdmin)
admin.site.register(Unite.history.model, HistoricalUniteAdmin)
admin.site.register(Emplacement.history.model, HistoricalEmplacementAdmin)
admin.site.register(ModePaiement.history.model, HistoricalModePaiementAdmin)
admin.site.register(LivrePar.history.model, HistoricalLivreParAdmin)
