from datetime import date, timedelta

from chat_ai_assistant.contracts import ChatAIError
from django.utils import timezone


def parse_dates(args):
    try:
        start = date.fromisoformat(args["date_from"]) if args.get("date_from") else None
        end = date.fromisoformat(args["date_to"]) if args.get("date_to") else None
        if start and end and (start > end or (end - start).days > 3660):
            raise ValueError()
        return start, end
    except ValueError as exc:
        raise ChatAIError("INVALID_ARGUMENTS") from exc


def period_dates(args):
    today = timezone.localdate()
    start, end = parse_dates(args)
    period = args["period"]
    if period == "custom":
        if not start or not end:
            raise ChatAIError("INVALID_ARGUMENTS")
        return start, end
    if start or end:
        raise ChatAIError("INVALID_ARGUMENTS")
    if period == "current_month":
        return today.replace(day=1), today
    if period == "previous_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if period == "current_year":
        return today.replace(month=1, day=1), today
    return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
