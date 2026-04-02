"""
Shared constants used across multiple apps.
"""

from django.utils.translation import gettext_lazy as _

# Role names
ROLE_CAISSIER = _("Caissier")
ROLE_COMMERCIAL = _("Commercial")
ROLE_COMPTABLE = _("Comptable")
ROLE_LECTURE = _("Lecture")

ALL_ROLES = [ROLE_CAISSIER, ROLE_COMMERCIAL, ROLE_COMPTABLE, ROLE_LECTURE]
ROLES_WITH_PRINT = [ROLE_CAISSIER, ROLE_COMPTABLE, ROLE_COMMERCIAL]
ROLES_WITH_VIEW = [ROLE_CAISSIER, ROLE_COMPTABLE, ROLE_COMMERCIAL, ROLE_LECTURE]
ROLES_RESTRICTED = [ROLE_COMMERCIAL, ROLE_LECTURE, ROLE_COMPTABLE]

CURRENCY_CHOICES = [
    ("MAD", _("MAD – Dirham Marocain")),
    ("EUR", _("EUR – Euro")),
    ("USD", _("USD – Dollar Américain")),
]

REMISE_TYPE_CHOICES = [
    ("", ""),
    ("Pourcentage", _("Pourcentage")),
    ("Fixe", _("Fixe")),
]
