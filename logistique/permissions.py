"""Role and assignment checks for logistics operations."""

from core.constants import ROLE_COMPTABLE, ROLE_LOGISTIQUE
from core.permissions import can_create, can_update, get_user_role


def has_payment_validation_permission(user, company_id):
    if getattr(user, "is_superuser", False):
        return True
    return get_user_role(user, company_id) == ROLE_COMPTABLE


def is_order_responsible(user, order):
    return bool(
        getattr(user, "is_superuser", False)
        or (order.responsable_id and order.responsable_id == user.id)
    )


def can_process_assigned_payment(user, order):
    return bool(
        getattr(user, "is_superuser", False)
        or (
            has_payment_validation_permission(user, order.company_id)
            and order.paiement_assigne_a_id == user.id
        )
    )


def can_manage_logistics(user, company_id):
    return (
        can_update(user, company_id)
        or get_user_role(user, company_id) == ROLE_LOGISTIQUE
    )


def can_create_logistics(user, company_id):
    return (
        can_create(user, company_id)
        or get_user_role(user, company_id) == ROLE_LOGISTIQUE
    )
