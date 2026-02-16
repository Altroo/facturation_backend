"""
Shared constants used across multiple apps.
"""

# Role names
ROLE_CAISSIER = "Caissier"
ROLE_COMMERCIAL = "Commercial"
ROLE_COMPTABLE = "Comptable"
ROLE_LECTURE = "Lecture"

ALL_ROLES = [ROLE_CAISSIER, ROLE_COMMERCIAL, ROLE_COMPTABLE, ROLE_LECTURE]
ROLES_WITH_PRINT = [ROLE_CAISSIER, ROLE_COMPTABLE, ROLE_COMMERCIAL]
ROLES_WITH_VIEW = [ROLE_CAISSIER, ROLE_COMPTABLE, ROLE_COMMERCIAL, ROLE_LECTURE]
ROLES_RESTRICTED = [ROLE_COMMERCIAL, ROLE_LECTURE, ROLE_COMPTABLE]

CURRENCY_CHOICES = [
    ("MAD", "MAD – Dirham Marocain"),
    ("EUR", "EUR – Euro"),
    ("USD", "USD – Dollar Américain"),
]

REMISE_TYPE_CHOICES = [
    ("", ""),
    ("Pourcentage", "Pourcentage"),
    ("Fixe", "Fixe"),
]
