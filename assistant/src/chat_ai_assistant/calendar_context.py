"""Calendar anchors computed from the adapter's trusted application-local date."""
from datetime import date, timedelta


def with_calendar_context(context):
    result = dict(context)
    # Never retain caller-provided computed boundaries; derive them from today.
    result.pop('calendar', None)
    value = context.get('today')
    if not isinstance(value, str) or len(value) != 10:
        return result
    try:
        today = date.fromisoformat(value)
        first = today.replace(day=1)
        previous_last = first - timedelta(days=1)
        anchors = {
            'yesterday': today - timedelta(days=1),
            'current_month_first_day': first,
            'previous_month_first_day': previous_last.replace(day=1),
            'previous_month_last_day': previous_last,
            'current_year_first_day': today.replace(month=1, day=1),
            'previous_year_first_day': date(today.year - 1, 1, 1),
            'previous_year_last_day': date(today.year - 1, 12, 31),
        }
    except (ValueError, OverflowError):
        return result
    result['calendar'] = {key: day.isoformat() for key, day in anchors.items()}
    return result
