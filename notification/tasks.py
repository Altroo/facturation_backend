"""Celery tasks for facturation notification checks."""

import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.utils import timezone
from django.utils.translation import gettext as _

from notification.models import Notification, NotificationPreference
from notification.services import _dashboard_url, resolve_notification_target_url

logger = logging.getLogger(__name__)

# Quote considered "expiring" if issued more than QUOTE_EXPIRY_DAYS ago and still Envoyé
QUOTE_EXPIRY_DAYS = 30

# BDL considered "stale" if accepted more than BDL_STALE_DAYS ago without being invoiced
BDL_STALE_DAYS = 7


@shared_task(name="notification.check_facturation_notifications")
def check_facturation_notifications():
    """
    Periodic task that checks for critical facturation events and creates
    notifications for all users. Runs every hour via Celery Beat.

    Events checked:
    - Overdue invoices (date_facture + client.delai_de_paiement < today)
    - Expiring quotes (Envoyé status, older than QUOTE_EXPIRY_DAYS)
    - Uninvoiced delivery notes (Accepté status, older than BDL_STALE_DAYS)
    """
    from facture_client.models import FactureClient
    from devi.models import Devi
    from bon_de_livraison.models import BonDeLivraison

    now = timezone.now()
    today = now.date()
    channel_layer = get_channel_layer()

    preferences = NotificationPreference.objects.select_related("user").all()

    for pref in preferences:
        user = pref.user

        # ── Overdue invoices ──────────────────────────────────────────────
        if pref.notify_overdue_invoice:
            overdue_factures = FactureClient.objects.select_related(
                "client", "company"
            ).filter(
                company__in=_get_user_companies(user),
                statut__in=["Envoyé", "Accepté"],
            )
            for facture in overdue_factures:
                delay_days = getattr(facture.client, "delai_de_paiement", 30) or 30
                due_date = facture.date_facture + timedelta(days=delay_days)
                if today > due_date:
                    exists = Notification.objects.filter(
                        user=user,
                        notification_type="overdue_invoice",
                        object_id=facture.id,
                    ).exists()
                    if not exists:
                        notif = Notification.objects.create(
                            user=user,
                            title=_("Facture en retard — %(numero)s")
                            % {"numero": facture.numero_facture},
                            message=_(
                                "La facture %(numero)s de %(client)s est en retard de paiement "
                                "(échéance : %(due)s)."
                            )
                            % {
                                "numero": facture.numero_facture,
                                "client": str(facture.client),
                                "due": due_date,
                            },
                            notification_type="overdue_invoice",
                            object_id=facture.id,
                            target_url=_dashboard_url(
                                "facture-client", facture.id, facture.company_id
                            ),
                        )
                        _broadcast(channel_layer, user.id, notif)

        # ── Expiring quotes ───────────────────────────────────────────────
        if pref.notify_expiring_quote:
            expiry_threshold = today - timedelta(days=pref.quote_expiry_days)
            expiring_devis = Devi.objects.select_related("client", "company").filter(
                company__in=_get_user_companies(user),
                statut="Envoyé",
                date_devis__lte=expiry_threshold,
            )
            for devis in expiring_devis:
                exists = Notification.objects.filter(
                    user=user,
                    notification_type="expiring_quote",
                    object_id=devis.id,
                ).exists()
                if not exists:
                    notif = Notification.objects.create(
                        user=user,
                        title=_("Devis expirant — %(numero)s")
                        % {"numero": devis.numero_devis},
                        message=_(
                            "Le devis %(numero)s pour %(client)s est en attente depuis "
                            "%(days)s jours sans réponse."
                        )
                        % {
                            "numero": devis.numero_devis,
                            "client": str(devis.client),
                            "days": (today - devis.date_devis).days,
                        },
                        notification_type="expiring_quote",
                        object_id=devis.id,
                        target_url=_dashboard_url("devis", devis.id, devis.company_id),
                    )
                    _broadcast(channel_layer, user.id, notif)

        # ── Uninvoiced delivery notes ─────────────────────────────────────
        if pref.notify_uninvoiced_bdl:
            stale_threshold = today - timedelta(days=BDL_STALE_DAYS)
            stale_bdl = BonDeLivraison.objects.select_related(
                "client", "company"
            ).filter(
                company__in=_get_user_companies(user),
                statut="Accepté",
                date_bon_livraison__lte=stale_threshold,
            )
            for bdl in stale_bdl:
                exists = Notification.objects.filter(
                    user=user,
                    notification_type="uninvoiced_bdl",
                    object_id=bdl.id,
                ).exists()
                if not exists:
                    notif = Notification.objects.create(
                        user=user,
                        title=_("BL non facturé — %(numero)s")
                        % {"numero": bdl.numero_bon_livraison},
                        message=_(
                            "Le bon de livraison %(numero)s pour %(client)s n'a pas encore "
                            "été facturé (livré le %(date)s)."
                        )
                        % {
                            "numero": bdl.numero_bon_livraison,
                            "client": str(bdl.client),
                            "date": bdl.date_bon_livraison,
                        },
                        notification_type="uninvoiced_bdl",
                        object_id=bdl.id,
                        target_url=_dashboard_url(
                            "bon-de-livraison", bdl.id, bdl.company_id
                        ),
                    )
                    _broadcast(channel_layer, user.id, notif)


def _get_user_companies(user):
    """Return companies accessible to the user."""
    from company.models import Company
    from account.models import Membership

    if user.is_staff:
        return Company.objects.all()
    company_ids = Membership.objects.filter(user=user).values_list(
        "company_id", flat=True
    )
    return Company.objects.filter(id__in=company_ids)


def _broadcast(channel_layer, user_id, notification):
    """Send a notification event to the user's personal WS group."""
    try:
        async_to_sync(channel_layer.group_send)(
            str(user_id),
            {
                "type": "receive_group_message",
                "message": {
                    "type": "NOTIFICATION",
                    "id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "notification_type": notification.notification_type,
                    "object_id": notification.object_id,
                    "target_url": resolve_notification_target_url(notification),
                    "is_read": notification.is_read,
                    "date_created": notification.date_created.isoformat(),
                },
            },
        )
    except Exception:
        logger.exception(
            "Failed to broadcast notification %s to user %s", notification.id, user_id
        )
