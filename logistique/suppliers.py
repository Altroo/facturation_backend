"""Link directory entries without rewriting the identity recorded on past dossiers."""

from .models import LogisticsSupplier


def ensure_supplier(company_id, name, email=""):
    name = (name or "").strip()
    if not name:
        return None
    supplier, _ = LogisticsSupplier.objects.get_or_create(
        company_id=company_id,
        nom__iexact=name,
        defaults={"nom": name, "email": (email or "").strip()},
    )
    return supplier
