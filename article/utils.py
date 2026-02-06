from re import search

from django.db import transaction

from core.utils import format_number_with_dynamic_digits
from .models import Article


def get_next_article_reference(company_id: int) -> str:
    """
    Return the next available reference string like 'ART0001' for the given company.
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

        max_num = 0
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
                value = int(num_str)
            except ValueError:
                continue
            if value > max_num:
                max_num = value

        next_number = max_num + 1
        formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
        return f"ART{formatted_number}"
