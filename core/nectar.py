"""Helpers for Nectar-specific document behavior."""

from company.models import Company

NECTAR_RAISON_SOCIALE = "IMMOBILIERE NECTAR"


def normalize_company_name(value: str | None) -> str:
    return (value or "").strip().upper()


def is_nectar_raison_sociale(value: str | None) -> bool:
    return normalize_company_name(value) == NECTAR_RAISON_SOCIALE


def is_nectar_company(company) -> bool:
    return is_nectar_raison_sociale(getattr(company, "raison_sociale", None))


def is_nectar_company_id(company_id: int | None) -> bool:
    if not company_id:
        return False
    raison_sociale = (
        Company.objects.filter(pk=company_id)
        .values_list("raison_sociale", flat=True)
        .first()
    )
    return is_nectar_raison_sociale(raison_sociale)
