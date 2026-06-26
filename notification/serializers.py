from rest_framework import serializers

from notification.models import Notification, NotificationPreference


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "notify_overdue_invoice",
            "notify_expiring_quote",
            "notify_uninvoiced_bdl",
            "notify_document_created",
            "quote_expiry_days",
            "date_created",
            "date_updated",
        ]
        read_only_fields = ["id", "date_created", "date_updated"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "object_id",
            "is_read",
            "date_created",
        ]
        read_only_fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "object_id",
            "date_created",
        ]
