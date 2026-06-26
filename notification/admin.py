from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from notification.models import Notification, NotificationPreference


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(SimpleHistoryAdmin):
    list_display = (
        "user",
        "notify_overdue_invoice",
        "notify_expiring_quote",
        "notify_uninvoiced_bdl",
        "notify_document_created",
        "date_updated",
    )
    search_fields = ("user__email",)
    readonly_fields = ("date_created", "date_updated")


@admin.register(Notification)
class NotificationAdmin(SimpleHistoryAdmin):
    list_display = ("user", "notification_type", "title", "is_read", "date_created")
    list_filter = ("notification_type", "is_read")
    search_fields = ("user__email", "title")
    ordering = ("-date_created",)
    readonly_fields = ("date_created",)


class HistoricalNotificationPreferenceAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical NotificationPreference records."""

    list_display = (
        "history_id",
        "id",
        "user",
        "notify_overdue_invoice",
        "notify_expiring_quote",
        "notify_uninvoiced_bdl",
        "history_type",
        "history_date",
        "history_user",
    )
    list_filter = ("history_type", "history_date")
    readonly_fields = [
        field.name
        for field in NotificationPreference._meta.get_fields()
        if hasattr(field, "name")
        and getattr(field, "concrete", False)
        and not field.many_to_many
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


class HistoricalNotificationAdmin(admin.ModelAdmin):
    """Read-only admin for viewing historical Notification records."""

    list_display = (
        "history_id",
        "id",
        "user",
        "title",
        "notification_type",
        "is_read",
        "history_type",
        "history_date",
        "history_user",
    )
    list_filter = ("history_type", "history_date", "notification_type", "is_read")
    search_fields = ("title", "message")
    readonly_fields = [
        field.name
        for field in Notification._meta.get_fields()
        if hasattr(field, "name")
        and getattr(field, "concrete", False)
        and not field.many_to_many
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


admin.site.register(
    NotificationPreference.history.model, HistoricalNotificationPreferenceAdmin
)
admin.site.register(Notification.history.model, HistoricalNotificationAdmin)
