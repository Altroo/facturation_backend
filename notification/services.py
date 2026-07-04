import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils.translation import gettext as _

from core.constants import ROLE_CAISSIER
from notification.models import Notification, NotificationPreference

logger = logging.getLogger(__name__)

NOTIFICATION_TARGET_ROUTES = {
    "overdue_invoice": "facture-client",
    "expiring_quote": "devis",
    "uninvoiced_bdl": "bon-de-livraison",
}

DOCUMENT_TARGET_ROUTES = {
    "Devi": "devis",
    "FactureClient": "facture-client",
    "FactureProForma": "facture-pro-forma",
    "BonDeLivraison": "bon-de-livraison",
    "FactureAvoir": "facture-avoir",
    "Reglement": "reglements",
    "LogisticsOrder": "logistique",
}

DOCUMENT_LABEL_TARGET_ROUTES = [
    (
        ("facture pro-forma", "facture proforma", "pro-forma", "proforma"),
        "facture-pro-forma",
    ),
    (("facture d'avoir", "facture avoir", "avoir"), "facture-avoir"),
    (("facture client",), "facture-client"),
    (("bon de livraison",), "bon-de-livraison"),
    (("règlement", "reglement"), "reglements"),
    (("commande logistique", "logistique"), "logistique"),
    (("devis",), "devis"),
]


def _dashboard_url(route: str, object_id, company_id=None) -> str:
    if not route or not object_id:
        return ""
    url = f"/dashboard/{route}/{object_id}"
    if company_id:
        url = f"{url}?company_id={company_id}"
    return url


def _get_document_company_id(document):
    company_id = getattr(document, "company_id", None)
    if company_id:
        return company_id

    company = getattr(document, "company", None)
    company_id = getattr(company, "id", None)
    if company_id:
        return company_id

    client = getattr(document, "client", None)
    company_id = getattr(client, "company_id", None)
    if company_id:
        return company_id

    facture_client = getattr(document, "facture_client", None)
    client = getattr(facture_client, "client", None)
    return getattr(client, "company_id", None)


def _get_model_for_route(route: str):
    if route == "devis":
        from devi.models import Devi

        return Devi
    if route == "facture-client":
        from facture_client.models import FactureClient

        return FactureClient
    if route == "facture-pro-forma":
        from facture_proforma.models import FactureProForma

        return FactureProForma
    if route == "bon-de-livraison":
        from bon_de_livraison.models import BonDeLivraison

        return BonDeLivraison
    if route == "facture-avoir":
        from facture_avoir.models import FactureAvoir

        return FactureAvoir
    if route == "reglements":
        from reglement.models import Reglement

        return Reglement
    if route == "logistique":
        from logistique.models import LogisticsOrder

        return LogisticsOrder
    return None


def _resolve_document_company_id(route: str, object_id):
    model = _get_model_for_route(route)
    if model is None:
        return None
    try:
        document = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return None
    return _get_document_company_id(document)


def _route_from_document_message(message: str) -> str:
    for labels, route in DOCUMENT_LABEL_TARGET_ROUTES:
        if any(label in message for label in labels):
            return route
    return ""


def _route_from_target_url(target_url: str) -> str:
    path = (target_url or "").split("?", 1)[0].strip("/")
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "dashboard":
        return parts[1]
    return ""


def _route_from_notification(notification) -> str:
    object_id = getattr(notification, "object_id", None)
    if not object_id:
        return ""

    notification_type = getattr(notification, "notification_type", "")
    route = NOTIFICATION_TARGET_ROUTES.get(notification_type)
    if route:
        return route

    if notification_type != "document_created":
        return ""

    message = (getattr(notification, "message", "") or "").lower()
    return _route_from_document_message(message)


def resolve_notification_target_url(notification) -> str:
    """Return a navigable dashboard URL for new and legacy notifications."""
    object_id = getattr(notification, "object_id", None)
    target_url = getattr(notification, "target_url", "") or ""

    if not object_id:
        return target_url

    route = _route_from_notification(notification) or _route_from_target_url(target_url)
    if not route:
        return target_url

    if target_url and "company_id=" in target_url:
        return target_url

    company_id = getattr(notification, "company_id", None) or _resolve_document_company_id(
        route, object_id
    )
    return _dashboard_url(route, object_id, company_id) or target_url


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
                    "target_url": resolve_notification_target_url(notification),
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
        "numero_commande",
        "libelle",
    ):
        value = getattr(document, field, None)
        if value:
            return str(value)
    return str(getattr(document, "id", ""))


def _get_document_target_url(document) -> str:
    route = DOCUMENT_TARGET_ROUTES.get(document.__class__.__name__)
    return _dashboard_url(
        route,
        getattr(document, "id", None),
        _get_document_company_id(document),
    )


def notify_document_created(document, *, company_id, document_label, creator=None):
    """Notify company admins that a document has been created."""
    if not company_id:
        return

    from account.models import Membership

    label = _clean_document_label(document_label)
    numero = _get_document_number(document)
    target_url = _get_document_target_url(document)
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
                target_url=target_url,
            )
            _broadcast_notification(channel_layer, membership.user_id, notif)
    except Exception:
        logger.exception(
            "Failed to create document-created notifications for company %s",
            company_id,
        )
