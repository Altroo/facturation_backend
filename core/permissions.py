"""
Permission utilities for group-based access control.

Group definitions:
- Caissier: Full access (create, read, update, delete, print)
- Comptable: Read and print only
- Commercial: Create documents (factures, devis, pro forma, bon_livraison), no users/companies, no prix_vente update
- Lecture: View only (no print, no create, no delete, no edit)
"""

from typing import TYPE_CHECKING

from core.constants import (
    ROLE_CAISSIER,
    ROLE_COMMERCIAL,
    ROLE_COMPTABLE,
    ROLE_LECTURE,
    ROLES_WITH_PRINT,
    ROLES_WITH_VIEW,
)

if TYPE_CHECKING:
    from account.models import CustomUser


def get_user_role(user: "CustomUser", company_id: int) -> str:
    """Get the user's role for a specific company. Cached on the user object per request."""
    from account.models import Membership

    # Cache roles on the user object to avoid repeated queries in the same request
    cache: dict[int, str] = getattr(user, "role_cache", {})
    if not cache:
        setattr(user, "role_cache", cache)

    if company_id not in cache:
        try:
            membership = Membership.objects.select_related("role").get(
                user=user, company_id=company_id
            )
            cache[company_id] = membership.role.name if membership.role else ""
        except Membership.DoesNotExist:
            cache[company_id] = ""

    return cache[company_id]


def is_caissier(user: "CustomUser", company_id: int) -> bool:
    """Check if user is Caissier for the company (full access)."""
    return get_user_role(user, company_id) == ROLE_CAISSIER


def is_comptable(user: "CustomUser", company_id: int) -> bool:
    """Check if user is Comptable for the company (read & print only)."""
    return get_user_role(user, company_id) == ROLE_COMPTABLE


def is_commercial(user: "CustomUser", company_id: int) -> bool:
    """Check if user is Commercial for the company."""
    return get_user_role(user, company_id) == ROLE_COMMERCIAL


def is_lecture(user: "CustomUser", company_id: int) -> bool:
    """Check if user is Lecture for the company (view only)."""
    return get_user_role(user, company_id) == ROLE_LECTURE


def can_create(user: "CustomUser", company_id: int, model_name: str = "") -> bool:
    """
    Check if user can create resources.

    Args:
        user: The user to check
        company_id: The company ID
        model_name: Optional model name for specific checks (e.g., 'user', 'company')
    """
    role = get_user_role(user, company_id)

    # Caissier can create everything
    if role == ROLE_CAISSIER:
        return True

    # Commercial can create documents but not users/companies
    if role == ROLE_COMMERCIAL:
        if model_name.lower() in ["user", "company"]:
            return False
        return True

    # Comptable and Lecture cannot create
    return False


def can_update(user: "CustomUser", company_id: int, field_name: str = "") -> bool:
    """
    Check if user can update resources.

    Args:
        user: The user to check
        company_id: The company ID
        field_name: Optional field name for specific checks (e.g., 'prix_vente')
    """
    role = get_user_role(user, company_id)

    # Caissier can update everything
    if role == ROLE_CAISSIER:
        return True

    # Commercial can update but not prix_vente
    if role == ROLE_COMMERCIAL:
        if field_name == "prix_vente":
            return False
        return True

    # Comptable and Lecture cannot update
    return False


def can_delete(user: "CustomUser", company_id: int) -> bool:
    """Check if user can delete resources."""
    role = get_user_role(user, company_id)

    # Only Caissier can delete
    return role == ROLE_CAISSIER


def can_view(user: "CustomUser", company_id: int) -> bool:
    """Check if user can view resources (all roles can view)."""
    role = get_user_role(user, company_id)
    return role in ROLES_WITH_VIEW


def can_print(user: "CustomUser", company_id: int) -> bool:
    """Check if user can print documents."""
    role = get_user_role(user, company_id)

    # Caissier, Comptable, and Commercial can print
    # Lecture cannot print
    return role in ROLES_WITH_PRINT
