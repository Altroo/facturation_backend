from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

MAINTENANCE_GROUP = "maintenance"


class WsMaintenanceState(models.Model):
    maintenance = models.BooleanField(default=False, verbose_name="Maintenance")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Maintenance"
        verbose_name_plural = "Maintenance"


@receiver(post_save, sender=WsMaintenanceState)
def broadcast_maintenance_state(sender, instance, **kwargs):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    event = {
        "type": "receive_group_message",
        "message": {
            "type": "MAINTENANCE",
            "maintenance": bool(instance.maintenance),
        },
    }
    async_to_sync(channel_layer.group_send)(MAINTENANCE_GROUP, event)
