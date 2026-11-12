"""Publish committed logistics changes to active company members."""

import logging
from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from account.models import Membership
from .models import LogisticsOrder, LogisticsPaymentInstallment

logger = logging.getLogger(__name__)


def broadcast_logistics_change(order_id, company_id):
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        recipients = (
            Membership.objects.filter(company_id=company_id, user__is_active=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        for user_id in recipients:
            async_to_sync(layer.group_send)(
                str(user_id),
                {
                    "type": "receive_group_message",
                    "message": {
                        "type": "LOGISTICS_UPDATED",
                        "id": order_id,
                        "company_id": company_id,
                    },
                },
            )
    except Exception:
        logger.exception(
            "Unable to broadcast logistics update for dossier %s", order_id
        )


@receiver(post_save, sender=LogisticsOrder, dispatch_uid="logistics_order_live_update")
def order_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(
            partial(broadcast_logistics_change, instance.pk, instance.company_id)
        )


@receiver(
    post_save,
    sender=LogisticsPaymentInstallment,
    dispatch_uid="logistics_payment_live_update",
)
def installment_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(
            partial(
                broadcast_logistics_change,
                instance.commande_id,
                instance.commande.company_id,
            )
        )
