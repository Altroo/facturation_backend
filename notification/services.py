import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils.translation import gettext as _

from core.constants import ROLE_CAISSIER
from notification.models import Notification, NotificationPreference

logger = logging.getLogger(__name__)


def _broadcast_notification(channel_layer, user_id, notification):
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
                    "is_read": notification.is_read,
                    "date_created": notification.date_created.isoformat(),
                },
            },
        )
    except Exception:
        logger.exception(
            "Failed to broadcast notification %s to user %s",
            notification.id,
            user_id,
        )


def _clean_document_label(document_label: str) -> str:
    label = (document_label or _("document")).strip()
    for prefix in ("la ", "le ", "l'"):
        if label.lower().startswith(prefix):
            return label[len(prefix) :]
    return label


def _get_document_number(document) -> str:
    for field in (
        "numero_devis",
        "numero_facture",
        "numero_bon_livraison",
        "numero_avoir",
        "libelle",
    ):
        value = getattr(document, field, None)
        if value:
            return str(value)
    return str(getattr(document, "id", ""))


def notify_document_created(document, *, company_id, document_label, creator=None):
    """Notify company admins that a document has been created."""
    if not company_id:
        return

    from account.models import Membership

    label = _clean_document_label(document_label)
    numero = _get_document_number(document)
    client = getattr(document, "client", None)
    if client is None:
        facture_client = getattr(document, "facture_client", None)
        client = getattr(facture_client, "client", None)
    client_name = str(client) if client else _("ce client")
    creator_name = (
        creator.get_full_name()
        if creator is not None and hasattr(creator, "get_full_name")
        else ""
    )
    creator_name = creator_name or getattr(creator, "email", "") or _("Un utilisateur")

    try:
        memberships = (
            Membership.objects.select_related("user", "role")
            .filter(company_id=company_id, role__name=ROLE_CAISSIER)
            .distinct()
        )
        channel_layer = get_channel_layer()

        for membership in memberships:
            pref, _created = NotificationPreference.objects.get_or_create(
                user=membership.user
            )
            if not pref.notify_document_created:
                continue

            notif = Notification.objects.create(
                user=membership.user,
                title=_("Nouveau document — %(numero)s") % {"numero": numero},
                message=_(
                    "%(creator)s a créé %(document)s %(numero)s pour %(client)s."
                )
                % {
                    "creator": creator_name,
                    "document": label,
                    "numero": numero,
                    "client": client_name,
                },
                notification_type="document_created",
                object_id=getattr(document, "id", None),
            )
            _broadcast_notification(channel_layer, membership.user_id, notif)
    except Exception:
        logger.exception(
            "Failed to create document-created notifications for company %s",
            company_id,
        )
