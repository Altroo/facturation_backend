from types import SimpleNamespace

from notification.serializers import NotificationSerializer
from notification.services import (
    _get_document_target_url,
    resolve_notification_target_url,
)


def _notification(**overrides):
    data = {
        "id": 1,
        "title": "Nouveau document",
        "message": "",
        "notification_type": "document_created",
        "object_id": 41,
        "target_url": "",
        "company_id": 3,
        "is_read": False,
        "date_created": "2026-06-26T00:00:00Z",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_notification_target_url_preserves_stored_url():
    notification = _notification(
        object_id=12,
        target_url="/dashboard/devis/12?company_id=9",
        company_id=9,
    )

    assert resolve_notification_target_url(notification) == (
        "/dashboard/devis/12?company_id=9"
    )


def test_notification_target_url_infers_legacy_document_created_url():
    notification = _notification(
        message="support@example.com a créé facture pro-forma P001/26 pour Client."
    )

    assert (
        resolve_notification_target_url(notification)
        == "/dashboard/facture-pro-forma/41?company_id=3"
    )


def test_notification_target_url_infers_periodic_notification_url():
    notification = _notification(
        notification_type="overdue_invoice",
        object_id=82,
    )

    assert (
        resolve_notification_target_url(notification)
        == "/dashboard/facture-client/82?company_id=3"
    )


def test_notification_serializer_returns_resolved_target_url():
    notification = _notification(
        message="contact@example.com a créé bon de livraison 0001/26 pour Client.",
        object_id=5,
    )

    assert NotificationSerializer(notification).data["target_url"] == (
        "/dashboard/bon-de-livraison/5?company_id=3"
    )


def test_document_target_url_uses_document_class_name():
    document = type("FactureProForma", (), {"id": 40, "company_id": 3})()

    assert _get_document_target_url(document) == (
        "/dashboard/facture-pro-forma/40?company_id=3"
    )
