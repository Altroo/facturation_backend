"""Seven-day stock holds. Supplier logistics remains independent of the hold."""

from datetime import timedelta
from functools import partial
import logging

from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from account.models import Membership
from core.constants import ROLE_CAISSIER, ROLE_COMMERCIAL, ROLE_LOGISTIQUE
from facture_proforma.models import FactureProForma
from notification.models import Notification
from notification.services import broadcast_notification
from .models import StockBalance, StockReservation
from .services import sync_proforma_reservations

logger = logging.getLogger(__name__)


def _active(proforma_id):
    return StockReservation.objects.filter(
        proforma_line__facture_pro_forma_id=proforma_id,
        status=StockReservation.STATUS_ACTIVE,
        reserved_quantity__gt=F("consumed_quantity") + F("released_quantity"),
    )


def _notify(proforma, *, expired, deadline):
    title = f"Proforma {proforma.numero_facture} : " + (
        "réservation expirée" if expired else "réservation bientôt expirée"
    )
    date_label = timezone.localtime(deadline).strftime("%d/%m/%Y à %H:%M")
    message = (
        f"La proforma {proforma.numero_facture} est expirée. Le stock encore réservé a été libéré. Les dossiers logistiques liés restent à vérifier."
        if expired
        else f"La réservation de stock de la proforma {proforma.numero_facture} expire le {date_label}. Relancez le client avant cette échéance."
    )
    recipients = (
        Membership.objects.filter(
            company_id=proforma.company_id,
            user__is_active=True,
            role__name__in=(ROLE_CAISSIER, ROLE_COMMERCIAL, ROLE_LOGISTIQUE),
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in recipients:
        notification = Notification.objects.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type="status_change",
            object_id=proforma.pk,
            target_url=f"/dashboard/facture-pro-forma/{proforma.pk}?company_id={proforma.company_id}",
        )
        transaction.on_commit(
            partial(broadcast_notification, get_channel_layer(), user_id, notification),
            robust=True,
        )


@transaction.atomic
def process_reservation_deadline(proforma_id, *, now=None):
    now = now or timezone.now()
    proforma = (
        FactureProForma.objects.select_for_update(of=("self",))
        .select_related("company")
        .get(pk=proforma_id)
    )
    if proforma.statut != "Accepté" or not proforma.company.stock_management_enabled:
        return "unchanged"
    # Same lock order as document status changes and delivery posting.
    balance_ids = _active(proforma_id).values("balance_id")
    list(
        StockBalance.objects.select_for_update()
        .filter(pk__in=balance_ids)
        .order_by("pk")
    )
    reservations = list(
        _active(proforma_id).select_for_update().order_by("expires_at", "pk")
    )
    deadlines = [r.expires_at for r in reservations if r.expires_at]
    if not deadlines:
        return "unchanged"
    deadline = min(deadlines)
    if deadline <= now:
        sync_proforma_reservations(proforma, "Accepté", "Expiré")
        proforma.statut = "Expiré"
        proforma.save(update_fields=("statut", "date_updated"))
        for order in proforma.commandes_logistiques.all():
            order.add_event(
                action="Expiration de la réservation de stock",
                old_value="Accepté",
                new_value=f"Proforma {proforma.numero_facture} expirée — stock restant libéré. Commande à vérifier.",
            )
        _notify(proforma, expired=True, deadline=deadline)
        return "expired"
    if deadline <= now + timedelta(hours=24) and any(
        r.expiry_reminded_at is None for r in reservations
    ):
        _notify(proforma, expired=False, deadline=deadline)
        _active(proforma_id).update(expiry_reminded_at=now)
        return "reminded"
    return "unchanged"


def scan_reservation_deadlines(*, now=None):
    now = now or timezone.now()
    ids = list(
        StockReservation.objects.filter(
            status=StockReservation.STATUS_ACTIVE,
            expires_at__lte=now + timedelta(hours=24),
            proforma_line__facture_pro_forma__statut="Accepté",
            balance__company__stock_management_enabled=True,
        )
        .order_by()
        .values_list("proforma_line__facture_pro_forma_id", flat=True)
        .distinct()
    )
    counts = {"expired": 0, "reminded": 0, "unchanged": 0, "failed": 0}
    for proforma_id in ids:
        try:
            counts[process_reservation_deadline(proforma_id, now=now)] += 1
        except Exception:
            # One damaged document must not prevent the other holds from expiring.
            logger.exception(
                "Stock reservation expiry failed for proforma %s", proforma_id
            )
            counts["failed"] += 1
    return counts
