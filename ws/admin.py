from django.contrib import admin

from ws.models import ChangelogEntry, WsMaintenanceState


class WsMaintenanceStateAdmin(admin.ModelAdmin):
    list_display = ("maintenance", "version", "updated_at")


admin.site.register(WsMaintenanceState, WsMaintenanceStateAdmin)


@admin.register(ChangelogEntry)
class ChangelogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "version",
        "title_fr",
        "title_en",
        "is_published",
        "updated_at",
    )
    list_filter = ("is_published",)
    search_fields = ("version", "title_fr", "title_en", "changes_fr", "changes_en")
    date_hierarchy = "date"
    readonly_fields = ("updated_at",)
    fieldsets = (
        (None, {"fields": ("date", "version", "is_published")}),
        ("Français", {"fields": ("title_fr", "changes_fr")}),
        ("English", {"fields": ("title_en", "changes_en")}),
        (None, {"fields": ("updated_at",)}),
    )
