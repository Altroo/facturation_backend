from django.contrib import admin

from ws.models import ChangelogEntry, MobileChangelogEntry, WsMaintenanceState


class WsMaintenanceStateAdmin(admin.ModelAdmin):
    list_display = ("maintenance", "version", "version_mobile", "updated_at")


admin.site.register(WsMaintenanceState, WsMaintenanceStateAdmin)


@admin.register(ChangelogEntry)
class ChangelogEntryAdmin(admin.ModelAdmin):
    platforms = (ChangelogEntry.Platform.WEB, ChangelogEntry.Platform.BOTH)
    list_display = (
        "date",
        "version",
        "platform",
        "title_fr",
        "title_en",
        "is_published",
        "updated_at",
    )
    list_filter = ("platform", "is_published")
    search_fields = ("version", "title_fr", "title_en", "changes_fr", "changes_en")
    date_hierarchy = "date"
    readonly_fields = ("updated_at",)
    fieldsets = (
        (None, {"fields": ("date", "version", "platform", "is_published")}),
        ("Français", {"fields": ("title_fr", "changes_fr")}),
        ("English", {"fields": ("title_en", "changes_en")}),
        (None, {"fields": ("updated_at",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(platform__in=self.platforms)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "platform":
            kwargs["choices"] = [(platform, platform.label) for platform in self.platforms]
            kwargs["initial"] = self.platforms[0]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(MobileChangelogEntry)
class MobileChangelogEntryAdmin(ChangelogEntryAdmin):
    platforms = (ChangelogEntry.Platform.MOBILE,)
    list_display = ("date", "version", "title_fr", "title_en", "is_published", "updated_at")
    list_filter = ("is_published",)

    def save_model(self, request, obj, form, change):
        obj.platform = ChangelogEntry.Platform.MOBILE
        super().save_model(request, obj, form, change)
