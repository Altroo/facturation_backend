"""
Utility functions for the facturation application.
"""


def format_number_with_dynamic_digits(number: int, min_digits: int = 4) -> str:
    """
    Format a number with dynamic digit count that increases when needed.

    Examples:
        - 1 with min_digits=4 -> "0001"
        - 9999 with min_digits=4 -> "9999"
        - 10000 with min_digits=4 -> "10000" (5 digits)
        - 99999 with min_digits=4 -> "99999" (5 digits)
        - 100000 with min_digits=4 -> "100000" (6 digits)

    Args:
        number: The number to format
        min_digits: Minimum number of digits (default 4)

    Returns:
        Formatted string with zero padding as needed
    """
    if number < 10**min_digits:
        # Number fits in min_digits, use standard zero-padding
        return f"{number:0{min_digits}d}"
    else:
        # Number exceeded min_digits, calculate required digits
        required_digits = len(str(number))
        return f"{number:0{required_digits}d}"
