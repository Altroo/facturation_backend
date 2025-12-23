from decimal import Decimal, InvalidOperation


def to_decimal_or_none(value):
    """Return Decimal for numeric-like values (int/float/Decimal/str) or None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def is_numeric_or_none(value):
    return to_decimal_or_none(value) is None or isinstance(
        to_decimal_or_none(value), Decimal
    )


def assert_numeric_equal(actual, expected):
    actual_dec = to_decimal_or_none(actual)
    assert actual_dec is not None, f"actual {actual!r} is not numeric"
    assert actual_dec == Decimal(str(expected)), f"{actual_dec} != {expected}"
