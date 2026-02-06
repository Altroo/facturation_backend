from re import search

from django.db import transaction

from core.utils import format_number_with_dynamic_digits
from .models import Client


def get_next_client_code(company_id: int) -> str:
    """
    Return the next available code_client string like 'CLT0001' for the given company.
    Automatically increases digit count when 9999 is reached.
    """
    with transaction.atomic():
        # Lock the relevant rows to prevent concurrent access
        existing = (
            Client.objects.filter(
                company_id=company_id,
                code_client__isnull=False,
            )
            .select_for_update()
            .values_list("code_client", flat=True)
        )

        max_num = 0
        for code in existing:
            if not code:
                continue
            match = search(r"CLT(\d+)", code)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if value > max_num:
                max_num = value

        next_number = max_num + 1
        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
        return f"CLT{formatted_number}"
