from datetime import timedelta
from decimal import Decimal
from typing import Iterable, TypedDict

from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from account.models import Membership
from article.models import Article
from bon_de_livraison.models import BonDeLivraisonLine
from core.constants import ROLE_CAISSIER, ROLE_LOGISTIQUE
from facture_proforma.models import FactureProForma
from logistique.models import LogisticsOrder, LogisticsOrderLine
from notification.models import Notification, NotificationPreference
from notification.services import broadcast_notification
from parameter.models import Emplacement
from .models import (
    InventorySession,
    LowStockAlert,
    StockBalance,
    StockMovement,
    StockReceipt,
    StockReservation,
)

ZERO = Decimal("0.000")
INCOMING_EXCLUDED_STATUSES = LogisticsOrder.STOCK_INCOMING_EXCLUDED_STATUSES
POSTED_DELIVERY_STATUSES = ("Accepté", "Facturé")


class StockBalanceSnapshot(TypedDict):
    physical_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    incoming_quantity: Decimal
    projected_quantity: Decimal
    stock_minimum: Decimal
    stock_state: str


class ArticleStockSnapshot(TypedDict):
    stock_management_enabled: bool
    physical_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    incoming_quantity: Decimal
    projected_quantity: Decimal
    stock_state: str


def is_product(article):
    return (article.type_article or "").strip().lower() == "produit"


def stock_enabled(company):
    return bool(getattr(company, "stock_management_enabled", False))


def ensure_company_stock_ready(company):
    emplacement = Emplacement.objects.get_or_create(
        company=company, nom="Emplacement principal"
    )[0]
    products = Article.objects.filter(company=company).exclude(
        type_article__iexact="Service"
    )
    products.filter(emplacement__isnull=True).update(emplacement=emplacement)
    for article in products.select_related("emplacement"):
        StockBalance.objects.get_or_create(
            company=company,
            article=article,
            emplacement=article.emplacement,
            defaults={"physical_quantity": ZERO, "reserved_quantity": ZERO},
        )
    for proforma in FactureProForma.objects.filter(
        company=company, statut="Accepté"
    ).prefetch_related("lignes__article"):
        sync_proforma_reservations(proforma, "Brouillon", "Accepté")
        delivered_by_article = (
            BonDeLivraisonLine.objects.filter(
                bon_de_livraison__company=company,
                bon_de_livraison__source_facture_client__source_proforma=proforma,
                bon_de_livraison__statut__in=POSTED_DELIVERY_STATUSES,
            )
            .values("article_id")
            .annotate(total=Sum("quantity"))
        )
        for delivered in delivered_by_article:
            article_reservations = StockReservation.objects.filter(
                proforma_line__facture_pro_forma=proforma,
                proforma_line__article_id=delivered["article_id"],
            )
            consumed = (
                article_reservations.aggregate(total=Sum("consumed_quantity"))["total"]
                or ZERO
            )
            quantity_to_reconcile = max(ZERO, (delivered["total"] or ZERO) - consumed)
            if quantity_to_reconcile == ZERO:
                continue
            reservation = (
                article_reservations.filter(status=StockReservation.STATUS_ACTIVE)
                .select_related("balance", "proforma_line__article")
                .order_by("id")
                .first()
            )
            if reservation is None:
                continue
            _consume_reservation(
                proforma,
                reservation.proforma_line.article,
                quantity_to_reconcile,
                reservation.balance,
            )
    for order in (
        LogisticsOrder.objects.filter(
            company=company,
            statut_commande_lancement="Terminée",
        )
        .exclude(statut_global="Annulé")
        .exclude(statut__in=INCOMING_EXCLUDED_STATUSES)
    ):
        activate_incoming(order)


def get_locked_balance(article, emplacement=None):
    emplacement = emplacement or article.emplacement
    if not emplacement:
        raise ValidationError(
            {
                "emplacement": _(
                    "Renseignez l'emplacement de l'article avant cette opération."
                )
            }
        )
    if emplacement.company_id != article.company_id:
        raise ValidationError(
            {
                "emplacement": _(
                    "L'emplacement doit appartenir à la société de l'article."
                )
            }
        )
    balance = StockBalance.objects.select_for_update().get_or_create(
        company_id=article.company_id,
        article=article,
        emplacement=emplacement,
        defaults={"physical_quantity": ZERO, "reserved_quantity": ZERO},
    )[0]
    return balance


def incoming_quantity(balance):
    total = (
        LogisticsOrderLine.objects.filter(
            commande__company_id=balance.company_id,
            commande__statut_commande_lancement="Terminée",
            expected_emplacement_id=balance.emplacement_id,
            article_id=balance.article_id,
        )
        .exclude(commande__statut_global="Annulé")
        .exclude(commande__statut__in=INCOMING_EXCLUDED_STATUSES)
        .aggregate(total=Sum(F("quantity") - F("received_quantity")))
        .get("total")
    )
    return max(ZERO, total or ZERO)


def balance_snapshot(
    balance: StockBalance, incoming: Decimal | None = None
) -> StockBalanceSnapshot:
    if incoming is None:
        incoming = incoming_quantity(balance)
    available = balance.physical_quantity - balance.reserved_quantity
    projected = available + incoming
    minimum = balance.article.stock_minimum
    if available < ZERO:
        state = "a_approvisionner"
    elif minimum > ZERO and available <= minimum:
        state = "minimum"
    else:
        state = "disponible"
    return {
        "physical_quantity": balance.physical_quantity,
        "reserved_quantity": balance.reserved_quantity,
        "available_quantity": available,
        "incoming_quantity": incoming,
        "projected_quantity": projected,
        "stock_minimum": minimum,
        "stock_state": state,
    }


def prepare_balance_snapshots(
    balances: Iterable[StockBalance],
) -> dict[int, StockBalanceSnapshot]:
    """Build stock snapshots without issuing one incoming query per balance."""
    balances = list(balances)
    if not balances:
        return {}

    company_ids = {balance.company_id for balance in balances}
    article_ids = {balance.article_id for balance in balances}
    emplacement_ids = {balance.emplacement_id for balance in balances}
    incoming_by_key = {
        (
            row["commande__company_id"],
            row["article_id"],
            row["expected_emplacement_id"],
        ): max(ZERO, row["total"] or ZERO)
        for row in LogisticsOrderLine.objects.filter(
            commande__company_id__in=company_ids,
            commande__statut_commande_lancement="Terminée",
            article_id__in=article_ids,
            expected_emplacement_id__in=emplacement_ids,
        )
        .exclude(commande__statut_global="Annulé")
        .exclude(commande__statut__in=INCOMING_EXCLUDED_STATUSES)
        .values("commande__company_id", "article_id", "expected_emplacement_id")
        .annotate(total=Sum(F("quantity") - F("received_quantity")))
    }
    snapshots: dict[int, StockBalanceSnapshot] = {}
    for balance in balances:
        incoming = incoming_by_key.get(
            (balance.company_id, balance.article_id, balance.emplacement_id), ZERO
        )
        snapshots[balance.pk] = balance_snapshot(balance, incoming=incoming)
    return snapshots


def article_stock_snapshot(article: Article) -> ArticleStockSnapshot:
    enabled = stock_enabled(article.company)
    snapshot: ArticleStockSnapshot = {
        "stock_management_enabled": enabled,
        "physical_quantity": ZERO,
        "reserved_quantity": ZERO,
        "available_quantity": ZERO,
        "incoming_quantity": ZERO,
        "projected_quantity": ZERO,
        "stock_state": (
            "not_managed" if not enabled or not is_product(article) else "disponible"
        ),
    }
    if not enabled or not is_product(article) or not article.emplacement_id:
        return snapshot
    balance = (
        StockBalance.objects.filter(
            article=article, emplacement_id=article.emplacement_id
        )
        .select_related("article")
        .first()
    )
    if not balance:
        return snapshot
    stock_values = balance_snapshot(balance)
    snapshot.update(
        physical_quantity=stock_values["physical_quantity"],
        reserved_quantity=stock_values["reserved_quantity"],
        available_quantity=stock_values["available_quantity"],
        incoming_quantity=stock_values["incoming_quantity"],
        projected_quantity=stock_values["projected_quantity"],
        stock_state=stock_values["stock_state"],
    )
    return snapshot


def prepare_article_stock_snapshots(
    articles: Iterable[Article],
) -> dict[int, ArticleStockSnapshot]:
    """Build article stock data using two bounded queries for a whole list."""
    articles = list(articles)
    managed = []
    snapshots: dict[int, ArticleStockSnapshot] = {}
    for article in articles:
        enabled = stock_enabled(article.company)
        snapshots[article.pk] = {
            "stock_management_enabled": enabled,
            "physical_quantity": ZERO,
            "reserved_quantity": ZERO,
            "available_quantity": ZERO,
            "incoming_quantity": ZERO,
            "projected_quantity": ZERO,
            "stock_state": (
                "not_managed"
                if not enabled or not is_product(article)
                else "disponible"
            ),
        }
        if enabled and is_product(article) and article.emplacement_id:
            managed.append(article)

    if not managed:
        return snapshots

    balances = list(
        StockBalance.objects.filter(article_id__in=[item.id for item in managed])
        .select_related("article")
        .order_by("id")
    )
    balance_snapshots = prepare_balance_snapshots(balances)
    balance_by_key = {
        (balance.article_id, balance.emplacement_id): balance for balance in balances
    }
    for article in managed:
        balance = balance_by_key.get((article.id, article.emplacement_id))
        if not balance:
            continue
        stock_values = balance_snapshots[balance.pk]
        snapshots[article.pk].update(
            physical_quantity=stock_values["physical_quantity"],
            reserved_quantity=stock_values["reserved_quantity"],
            available_quantity=stock_values["available_quantity"],
            incoming_quantity=stock_values["incoming_quantity"],
            projected_quantity=stock_values["projected_quantity"],
            stock_state=stock_values["stock_state"],
        )
    return snapshots


def coverage_for_article(article, requested_quantity):
    requested = Decimal(str(requested_quantity or 0))
    if not is_product(article) or not stock_enabled(article.company):
        return {"status": "not_managed", "requested_quantity": requested}
    if not article.emplacement_id:
        return {"status": "a_approvisionner", "requested_quantity": requested}
    balance = StockBalance.objects.filter(
        article=article, emplacement_id=article.emplacement_id
    ).first()
    if not balance:
        available = ZERO
        incoming = ZERO
    else:
        available = balance.available_quantity
        incoming = incoming_quantity(balance)
    if available >= requested:
        status = "disponible"
    elif available + incoming >= requested:
        status = "couvert_par_stock_entrant"
    else:
        status = "a_approvisionner"
    return {
        "status": status,
        "requested_quantity": requested,
        "available_quantity": available,
        "incoming_quantity": incoming,
        "shortage_quantity": max(ZERO, requested - available - incoming),
    }


def _schedule_low_stock_check(balance_id):
    transaction.on_commit(lambda: evaluate_low_stock(balance_id))


def post_movement(
    *,
    balance,
    quantity,
    movement_type,
    actor=None,
    source_type="",
    source_id=None,
    source_line_id=None,
    reservation=None,
    reversal_of=None,
    note="",
    idempotency_key=None,
):
    quantity = Decimal(str(quantity))
    if quantity == ZERO:
        return None
    if idempotency_key:
        existing = StockMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
    balance = StockBalance.objects.select_for_update().get(pk=balance.pk)
    new_quantity = balance.physical_quantity + quantity
    if new_quantity < ZERO:
        raise ValidationError(
            {
                "stock": _(
                    "Stock physique insuffisant pour %(article)s à %(emplacement)s. "
                    "Disponible physiquement: %(available)s, demandé: %(requested)s."
                )
                % {
                    "article": balance.article.reference,
                    "emplacement": balance.emplacement.nom,
                    "available": balance.physical_quantity,
                    "requested": abs(quantity),
                }
            }
        )
    balance.physical_quantity = new_quantity
    balance.save(update_fields=("physical_quantity", "date_updated"))
    movement = StockMovement.objects.create(
        balance=balance,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=new_quantity,
        source_type=source_type,
        source_id=source_id,
        source_line_id=source_line_id,
        reservation=reservation,
        reversal_of=reversal_of,
        actor=actor,
        note=note,
        idempotency_key=idempotency_key,
    )
    _schedule_low_stock_check(balance.pk)
    return movement


def sync_proforma_reservations(proforma, old_status, new_status):
    if not stock_enabled(proforma.company) or old_status == new_status:
        return
    lines = list(
        proforma.lignes.select_related("article", "article__emplacement").order_by("id")
    )
    if new_status == "Accepté":
        missing = [
            line.article.reference
            for line in lines
            if is_product(line.article) and not line.article.emplacement_id
        ]
        if missing:
            raise ValidationError(
                {
                    "stock": _("Emplacement manquant pour: %(articles)s")
                    % {"articles": ", ".join(missing)}
                }
            )
        for line in lines:
            if not is_product(line.article):
                continue
            balance = get_locked_balance(line.article)
            requested = Decimal(str(line.quantity))
            reservation = StockReservation.objects.select_for_update().get_or_create(
                proforma_line=line,
                defaults={"balance": balance, "reserved_quantity": ZERO},
            )[0]
            active_quantity = (
                reservation.reserved_quantity
                - reservation.consumed_quantity
                - reservation.released_quantity
            )
            desired_active = max(ZERO, requested - reservation.consumed_quantity)
            delta = desired_active - active_quantity
            if delta:
                balance.reserved_quantity += delta
                if balance.reserved_quantity < ZERO:
                    balance.reserved_quantity = ZERO
                balance.save(update_fields=("reserved_quantity", "date_updated"))
            reservation.balance = balance
            if delta > ZERO:
                restored_quantity = min(delta, reservation.released_quantity)
                reservation.released_quantity -= restored_quantity
                reservation.reserved_quantity += delta - restored_quantity
            elif delta < ZERO:
                reservation.released_quantity += abs(delta)
            if desired_active > ZERO:
                reservation.status = StockReservation.STATUS_ACTIVE
            elif reservation.consumed_quantity > ZERO:
                reservation.status = StockReservation.STATUS_CONSUMED
            else:
                reservation.status = StockReservation.STATUS_RELEASED
            reservation.save()
            _schedule_low_stock_check(balance.pk)
        return

    if old_status == "Accepté" and new_status != "Accepté":
        reservations = (
            StockReservation.objects.select_for_update()
            .filter(
                proforma_line__facture_pro_forma=proforma,
                status=StockReservation.STATUS_ACTIVE,
            )
            .select_related("balance")
        )
        for reservation in reservations:
            remaining = max(
                ZERO,
                reservation.reserved_quantity
                - reservation.consumed_quantity
                - reservation.released_quantity,
            )
            if remaining:
                balance = StockBalance.objects.select_for_update().get(
                    pk=reservation.balance_id
                )
                balance.reserved_quantity = max(
                    ZERO, balance.reserved_quantity - remaining
                )
                balance.save(update_fields=("reserved_quantity", "date_updated"))
                reservation.released_quantity += remaining
                _schedule_low_stock_check(balance.pk)
            reservation.status = StockReservation.STATUS_RELEASED
            reservation.save()


def activate_incoming(order):
    if not stock_enabled(order.company):
        return
    if order.statut_global == "Annulé" or order.statut in INCOMING_EXCLUDED_STATUSES:
        return
    lines = order.lignes.select_related("article", "article__emplacement").order_by(
        "id"
    )
    missing = [
        line.article.reference
        for line in lines
        if is_product(line.article) and not line.article.emplacement_id
    ]
    if missing:
        raise ValidationError(
            {
                "stock": _("Emplacement manquant pour: %(articles)s")
                % {"articles": ", ".join(missing)}
            }
        )
    for line in lines:
        if is_product(line.article) and not line.expected_emplacement_id:
            line.expected_emplacement_id = line.article.emplacement_id
            line.save(update_fields=("expected_emplacement",))


def _consume_reservation(proforma, article, quantity, balance):
    remaining = quantity
    consumed = []
    if not proforma:
        return consumed, remaining
    reservations = (
        StockReservation.objects.select_for_update()
        .filter(
            proforma_line__facture_pro_forma=proforma,
            proforma_line__article=article,
            balance=balance,
            status=StockReservation.STATUS_ACTIVE,
        )
        .order_by("id")
    )
    for reservation in reservations:
        active = max(
            ZERO,
            reservation.reserved_quantity
            - reservation.consumed_quantity
            - reservation.released_quantity,
        )
        amount = min(active, remaining)
        if amount:
            reservation.consumed_quantity += amount
            if (
                reservation.consumed_quantity + reservation.released_quantity
                >= reservation.reserved_quantity
            ):
                reservation.status = StockReservation.STATUS_CONSUMED
            reservation.save()
            balance.reserved_quantity = max(ZERO, balance.reserved_quantity - amount)
            balance.save(update_fields=("reserved_quantity", "date_updated"))
            consumed.append((reservation, amount))
            remaining -= amount
        if remaining <= ZERO:
            break
    return consumed, remaining


def sync_delivery_stock(delivery, old_status, new_status, actor):
    if not stock_enabled(delivery.company) or old_status == new_status:
        return
    posted_statuses = set(POSTED_DELIVERY_STATUSES)
    if new_status in posted_statuses and old_status not in posted_statuses:
        previous_postings = list(
            StockMovement.objects.select_for_update().filter(
                source_type="BonDeLivraison",
                source_id=delivery.pk,
                movement_type=StockMovement.TYPE_DELIVERY,
            )
        )
        reversed_posting_ids = set(
            StockMovement.objects.filter(
                reversal_of_id__in=[movement.pk for movement in previous_postings]
            ).values_list("reversal_of_id", flat=True)
        )
        if any(
            movement.pk not in reversed_posting_ids for movement in previous_postings
        ):
            return
        posting_cycle = len(previous_postings) + 1
        lines = list(
            delivery.lignes.select_related("article", "article__emplacement").order_by(
                "id"
            )
        )
        requirements = {}
        for line in lines:
            if not is_product(line.article):
                continue
            balance = get_locked_balance(line.article)
            requirements[balance.pk] = requirements.get(balance.pk, ZERO) + Decimal(
                str(line.quantity)
            )
        shortages = []
        for balance_id, required in requirements.items():
            balance = (
                StockBalance.objects.select_for_update()
                .select_related("article", "emplacement")
                .get(pk=balance_id)
            )
            if balance.physical_quantity < required:
                shortages.append(
                    f"{balance.article.reference} ({balance.physical_quantity}/{required})"
                )
        if shortages:
            raise ValidationError(
                {
                    "stock": _("Stock physique insuffisant: %(items)s")
                    % {"items": ", ".join(shortages)}
                }
            )

        source_proforma = getattr(
            delivery.source_facture_client, "source_proforma", None
        )
        for line in lines:
            if not is_product(line.article):
                continue
            balance = get_locked_balance(line.article)
            qty = Decimal(str(line.quantity))
            consumed, unreserved = _consume_reservation(
                source_proforma, line.article, qty, balance
            )
            chunk = 0
            for reservation, amount in consumed:
                post_movement(
                    balance=balance,
                    quantity=-amount,
                    movement_type=StockMovement.TYPE_DELIVERY,
                    actor=actor,
                    source_type="BonDeLivraison",
                    source_id=delivery.pk,
                    source_line_id=line.pk,
                    reservation=reservation,
                    note=_("Sortie sur bon de livraison %(number)s")
                    % {"number": delivery.numero_bon_livraison},
                    idempotency_key=(
                        f"bdl:{delivery.pk}:cycle:{posting_cycle}:"
                        f"line:{line.pk}:out:{chunk}"
                    ),
                )
                chunk += 1
            if unreserved:
                post_movement(
                    balance=balance,
                    quantity=-unreserved,
                    movement_type=StockMovement.TYPE_DELIVERY,
                    actor=actor,
                    source_type="BonDeLivraison",
                    source_id=delivery.pk,
                    source_line_id=line.pk,
                    note=_("Sortie sur bon de livraison %(number)s")
                    % {"number": delivery.numero_bon_livraison},
                    idempotency_key=(
                        f"bdl:{delivery.pk}:cycle:{posting_cycle}:"
                        f"line:{line.pk}:out:{chunk}"
                    ),
                )
        return

    if old_status in posted_statuses and new_status not in posted_statuses:
        movements = (
            StockMovement.objects.filter(
                source_type="BonDeLivraison",
                source_id=delivery.pk,
                movement_type=StockMovement.TYPE_DELIVERY,
            )
            .select_related("balance", "reservation")
            .order_by("id")
        )
        for movement in movements:
            if hasattr(movement, "reversal"):
                continue
            post_movement(
                balance=movement.balance,
                quantity=-movement.quantity,
                movement_type=StockMovement.TYPE_REVERSAL,
                actor=actor,
                source_type="BonDeLivraison",
                source_id=delivery.pk,
                source_line_id=movement.source_line_id,
                reservation=movement.reservation,
                reversal_of=movement,
                note=_("Annulation de la sortie du bon de livraison"),
                idempotency_key=f"reverse:{movement.pk}",
            )
            if movement.reservation_id:
                reservation = (
                    StockReservation.objects.select_for_update()
                    .select_related("proforma_line__facture_pro_forma")
                    .get(pk=movement.reservation_id)
                )
                amount = abs(movement.quantity)
                reservation.consumed_quantity = max(
                    ZERO, reservation.consumed_quantity - amount
                )
                proforma_status = reservation.proforma_line.facture_pro_forma.statut
                if proforma_status == "Accepté":
                    reservation.status = StockReservation.STATUS_ACTIVE
                    balance = StockBalance.objects.select_for_update().get(
                        pk=reservation.balance_id
                    )
                    balance.reserved_quantity += amount
                    balance.save(update_fields=("reserved_quantity", "date_updated"))
                    _schedule_low_stock_check(balance.pk)
                else:
                    reservation.released_quantity += amount
                    reservation.status = StockReservation.STATUS_RELEASED
                reservation.save()


def validate_receipt(receipt, actor):
    if receipt.status != StockReceipt.STATUS_DRAFT:
        raise ValidationError(
            {"status": _("Seule une réception brouillon peut être validée.")}
        )
    order = receipt.logistics_order
    if (
        order.statut_commande_lancement != "Terminée"
        or order.statut_global == "Annulé"
        or order.statut in INCOMING_EXCLUDED_STATUSES
    ):
        raise ValidationError(
            {
                "logistics_order": _(
                    "Le dossier logistique n'est pas actif en stock entrant."
                )
            }
        )
    lines = list(
        receipt.lines.select_related(
            "logistics_line", "article", "emplacement"
        ).order_by("id")
    )
    if not lines:
        raise ValidationError({"lines": _("Ajoutez au moins une ligne de réception.")})
    for line in lines:
        logistics_line = line.logistics_line
        if (
            logistics_line.commande_id != order.pk
            or logistics_line.article_id != line.article_id
        ):
            raise ValidationError(
                {"lines": _("Une ligne ne correspond pas au dossier logistique.")}
            )
        logistics_line = (
            type(logistics_line).objects.select_for_update().get(pk=logistics_line.pk)
        )
        remaining = logistics_line.quantity - logistics_line.received_quantity
        if line.quantity <= ZERO or line.quantity > remaining:
            raise ValidationError(
                {
                    "quantity": _(
                        "La quantité reçue pour %(article)s doit être comprise entre 0 et %(remaining)s."
                    )
                    % {"article": line.article.reference, "remaining": remaining}
                }
            )
        balance = get_locked_balance(line.article, line.emplacement)
        post_movement(
            balance=balance,
            quantity=line.quantity,
            movement_type=StockMovement.TYPE_RECEIPT,
            actor=actor,
            source_type="StockReceipt",
            source_id=receipt.pk,
            source_line_id=line.pk,
            note=_("Réception du dossier %(number)s")
            % {"number": order.numero_commande},
            idempotency_key=f"receipt:{receipt.pk}:line:{line.pk}",
        )
        logistics_line.received_quantity += line.quantity
        logistics_line.save(update_fields=("received_quantity",))
    receipt.status = StockReceipt.STATUS_VALIDATED
    receipt.validated_by = actor
    receipt.date_validated = timezone.now()
    receipt.save(update_fields=("status", "validated_by", "date_validated"))
    if not order.lignes.filter(received_quantity__lt=F("quantity")).exists():
        order.statut = "Réception locale"
        order.date_reelle = timezone.localdate()
        order.save(update_fields=("statut", "date_reelle", "date_updated"))


def cancel_receipt(receipt, actor):
    if receipt.status != StockReceipt.STATUS_VALIDATED:
        raise ValidationError(
            {"status": _("Seule une réception validée peut être annulée.")}
        )
    movements = list(
        StockMovement.objects.filter(
            source_type="StockReceipt",
            source_id=receipt.pk,
            movement_type=StockMovement.TYPE_RECEIPT,
        )
        .select_related("balance")
        .order_by("-id")
    )
    for movement in movements:
        if hasattr(movement, "reversal"):
            continue
        post_movement(
            balance=movement.balance,
            quantity=-movement.quantity,
            movement_type=StockMovement.TYPE_REVERSAL,
            actor=actor,
            source_type="StockReceipt",
            source_id=receipt.pk,
            source_line_id=movement.source_line_id,
            reversal_of=movement,
            note=_("Annulation de réception"),
            idempotency_key=f"reverse:{movement.pk}",
        )
        receipt_line = receipt.lines.get(pk=movement.source_line_id)
        logistics_line = (
            type(receipt_line.logistics_line)
            .objects.select_for_update()
            .get(pk=receipt_line.logistics_line_id)
        )
        logistics_line.received_quantity = max(
            ZERO, logistics_line.received_quantity - receipt_line.quantity
        )
        logistics_line.save(update_fields=("received_quantity",))
    receipt.status = StockReceipt.STATUS_CANCELLED
    receipt.save(update_fields=("status",))
    order = receipt.logistics_order
    if order.statut == "Réception locale":
        order.statut = "Dédouanement"
        order.date_reelle = None
        order.save(update_fields=("statut", "date_reelle", "date_updated"))


def validate_inventory(inventory, actor):
    if inventory.status != InventorySession.STATUS_DRAFT:
        raise ValidationError(
            {"status": _("Seul un inventaire brouillon peut être validé.")}
        )
    lines = list(inventory.lines.select_related("article").order_by("id"))
    if not lines:
        raise ValidationError({"lines": _("Ajoutez au moins une ligne d'inventaire.")})
    for line in lines:
        balance = get_locked_balance(line.article, inventory.emplacement)
        expected = balance.physical_quantity
        delta = line.counted_quantity - expected
        post_movement(
            balance=balance,
            quantity=delta,
            movement_type=StockMovement.TYPE_INVENTORY,
            actor=actor,
            source_type="InventorySession",
            source_id=inventory.pk,
            source_line_id=line.pk,
            note=inventory.note or _("Écart d'inventaire"),
            idempotency_key=f"inventory:{inventory.pk}:line:{line.pk}",
        )
        line.expected_quantity = expected
        line.save(update_fields=("expected_quantity",))
    inventory.status = InventorySession.STATUS_VALIDATED
    inventory.validated_by = actor
    inventory.date_validated = timezone.now()
    inventory.save(update_fields=("status", "validated_by", "date_validated"))


def evaluate_low_stock(balance_id, force=False):
    try:
        balance = StockBalance.objects.select_related(
            "article", "emplacement", "company"
        ).get(pk=balance_id)
    except StockBalance.DoesNotExist:
        return
    available = balance.available_quantity
    is_low = (
        balance.article.stock_minimum > ZERO
        and available <= balance.article.stock_minimum
    )
    alert = LowStockAlert.objects.filter(balance=balance).first()
    if not is_low:
        if alert and alert.active:
            alert.active = False
            alert.recovered_at = timezone.now()
            alert.save(update_fields=("active", "recovered_at"))
        return
    alert = LowStockAlert.objects.get_or_create(balance=balance)[0]
    was_active = alert.active
    if not was_active:
        alert.active = True
        alert.first_detected_at = timezone.now()
        alert.recovered_at = None
    memberships = Membership.objects.filter(
        company_id=balance.company_id,
        user__is_active=True,
        role__name__in=(ROLE_CAISSIER, ROLE_LOGISTIQUE),
    ).select_related("user")
    notified = False
    incoming = incoming_quantity(balance)
    for membership in memberships:
        pref = NotificationPreference.objects.get_or_create(user=membership.user)[0]
        repeat_after = timedelta(hours=max(1, pref.low_stock_repeat_hours))
        if not pref.notify_low_stock:
            continue
        if not force and was_active:
            last_notification = (
                Notification.objects.filter(
                    user=membership.user,
                    notification_type="low_stock",
                    object_id=balance.article_id,
                )
                .only("date_created")
                .first()
            )
            if (
                last_notification
                and timezone.now() - last_notification.date_created < repeat_after
            ):
                continue
        notification = Notification.objects.create(
            user=membership.user,
            title=_("Stock minimum — %(article)s")
            % {"article": balance.article.reference},
            message=_(
                "%(article)s à %(location)s : physique %(physical)s, réservé %(reserved)s, "
                "entrant %(incoming)s, projeté %(projected)s, minimum %(minimum)s."
            )
            % {
                "article": balance.article.designation,
                "location": balance.emplacement.nom,
                "physical": balance.physical_quantity,
                "reserved": balance.reserved_quantity,
                "incoming": incoming,
                "projected": available + incoming,
                "minimum": balance.article.stock_minimum,
            },
            notification_type="low_stock",
            object_id=balance.article_id,
            target_url=f"/dashboard/stock?company_id={balance.company_id}&article_id={balance.article_id}",
        )
        broadcast_notification(get_channel_layer(), membership.user_id, notification)
        notified = True
    if notified:
        alert.last_notified_at = timezone.now()
    alert.save()


def scan_low_stock():
    for balance_id in (
        StockBalance.objects.filter(
            company__stock_management_enabled=True,
            article__stock_minimum__gt=0,
        )
        .values_list("id", flat=True)
        .iterator()
    ):
        evaluate_low_stock(balance_id)
