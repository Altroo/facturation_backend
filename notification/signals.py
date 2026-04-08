from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from notification.models import NotificationPreference


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_notification_preference(sender, instance, created, **kwargs):
    """Auto-create a NotificationPreference when a new user is created."""
    if created:
        NotificationPreference.objects.get_or_create(user=instance)
