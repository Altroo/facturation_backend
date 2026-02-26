from re import search

from django.db import transaction

from core.utils import format_number_with_dynamic_digits
from .models import Article


def get_next_article_reference(company_id: int) -> str:
    """
    Return the next available reference string like 'ART0001' for the given company.
    Finds the first gap in the sequence starting from 1.
    Automatically increases digit count when 9999 is reached.
    """
    with transaction.atomic():
        # Lock the relevant rows to prevent concurrent access
        existing = (
            Article.objects.filter(
                company_id=company_id,
                reference__isnull=False,
            )
            .select_for_update()
            .values_list("reference", flat=True)
        )

        used_numbers: set[int] = set()
        for ref in existing:
            if not ref:
                continue
            m = search(r"ART(\d+)", ref)
            if m:
                num_str = m.group(1)
            else:
                m_last = search(r"(\d+)(?!.*\d)", ref)
                num_str = m_last.group(1) if m_last else None
            if not num_str:
                continue
            try:
                used_numbers.add(int(num_str))
            except ValueError:
                continue

        # Find the first available number starting from 1
        next_number = 1
        while next_number in used_numbers:
            next_number += 1

        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
        return f"ART{formatted_number}"
