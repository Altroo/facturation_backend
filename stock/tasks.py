from celery import shared_task
from .services import scan_low_stock


@shared_task
def check_low_stock():
    scan_low_stock()


@shared_task
def check_reservation_deadlines():
    from .expiry import scan_reservation_deadlines

    return scan_reservation_deadlines()
