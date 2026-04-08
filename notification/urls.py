from django.urls import path

from notification.views import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationPreferenceView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path(
        "preferences/",
        NotificationPreferenceView.as_view(),
        name="notification-preferences",
    ),
    path("", NotificationListView.as_view(), name="notification-list"),
    path(
        "mark-read/", NotificationMarkReadView.as_view(), name="notification-mark-read"
    ),
    path(
        "unread-count/",
        NotificationUnreadCountView.as_view(),
        name="notification-unread-count",
    ),
]
