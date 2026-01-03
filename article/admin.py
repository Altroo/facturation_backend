from django.contrib import admin

from .models import Article


class ArticleAdmin(admin.ModelAdmin):
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


admin.site.register(Article, ArticleAdmin)
