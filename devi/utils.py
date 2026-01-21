from datetime import datetime

from django.db import transaction

from core.models import DocumentNumberSequence
from core.utils import format_number_with_dynamic_digits


def get_next_numero_devis() -> str:
    """
    Return the next available numero_devis string like '0001/25'.
    Automatically increases digit count when 9999 is reached.
    Uses atomic database sequence to prevent race conditions.
    """
    year_suffix = f"{datetime.now().year % 100:02d}"
    year_full = datetime.now().year

    with transaction.atomic():
        # Get or create sequence for this document type and year
        seq, created = DocumentNumberSequence.objects.select_for_update().get_or_create(
            document_type='devis',
            year=year_full,
            defaults={'last_number': 0}
        )

        # Atomically increment and get next number
        seq.last_number += 1
        next_number = seq.last_number
        seq.save()

    # Format with dynamic digits (0001, 0002, ..., 9999, 10000, etc.)
    formatted_number = format_number_with_dynamic_digits(next_number, min_digits=4)
    return f"{formatted_number}/{year_suffix}"
