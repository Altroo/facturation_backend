from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Article


class ArticleAdmin(SimpleHistoryAdmin):
    """Admin configuration for the Article model."""

    list_display = (
        "id",
        "reference",
        "designation",
        "company",
        "marque",
        "categorie",
        "unite",
        "prix_vente",
        "archived",
        "date_created",
        "date_updated",
    )
    search_fields = ("reference", "designation", "company__raison_sociale")
    list_filter = ("archived", "type_article", "company", "marque", "categorie")
    ordering = ("-date_created",)
    readonly_fields = ("date_created", "date_updated")


# Historical Model Admin (Read-only)
class HistoricalArticleAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Article records."""

    list_display = (
        "history_id",
        "id",
        "reference",
        "designation",
        "prix_vente",
        "archived",
        "history_type",
        "history_date",
        "history_user",
    )

    list_filter = (
        "history_type",
        "history_date",
        "archived",
        "type_article",
    )

    search_fields = (
        "reference",
        "designation",
    )

    readonly_fields = [
        field.name
        for field in Article._meta.get_fields()
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


admin.site.register(Article, ArticleAdmin)
admin.site.register(Article.history.model, HistoricalArticleAdmin)
