"""Exercise real DRF dispatch/rate limits without business queries or model calls."""
from types import SimpleNamespace
import uuid

import pytest
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from .views import (
    CapabilitiesView, ConversationsView, ConversationView, MessagesView,
    ConfirmActionView, FeedbackView, RecordSelectionView,
    ChatReadThrottle, ChatMutationThrottle, ChatInferenceThrottle,
    ChatConfirmationThrottle,
)


@pytest.fixture
def dispatch(settings, monkeypatch):
    settings.CHAT_AI_ASSISTANT_ENABLED = True
    cache = LocMemCache(str(uuid.uuid4()), {})
    for cls in (ChatReadThrottle, ChatMutationThrottle, ChatInferenceThrottle, ChatConfirmationThrottle):
        monkeypatch.setattr(cls, 'cache', cache)
        monkeypatch.setattr(cls, 'timer', staticmethod(lambda: 1000.0))
    handlers = {
        CapabilitiesView: ('get',), ConversationsView: ('get', 'post'),
        ConversationView: ('get', 'delete'), MessagesView: ('post',),
        ConfirmActionView: ('post',), FeedbackView: ('post',),
        RecordSelectionView: ('post',),
    }
    for view, methods in handlers.items():
        for method in methods:
            monkeypatch.setattr(view, method, lambda self, request, *args, **kwargs: Response({'ok': True}))
    factory = APIRequestFactory()

    def call(view, method='get', user_id=42):
        request = getattr(factory, method)('/api/ai/v1/', data={}, format='json')
        force_authenticate(request, user=SimpleNamespace(pk=user_id, is_authenticated=True))
        return view.as_view()(request)

    return call


def test_history_and_capabilities_do_not_consume_message_budget(dispatch):
    for _ in range(20):
        assert dispatch(CapabilitiesView).status_code == 200
        assert dispatch(ConversationsView).status_code == 200
        assert dispatch(ConversationView).status_code == 200
    for _ in range(12):
        assert dispatch(MessagesView, 'post').status_code == 200
    limited = dispatch(MessagesView, 'post')
    assert limited.status_code == 429 and limited['Retry-After'] == '60'
    assert dispatch(CapabilitiesView).status_code == 200
    assert dispatch(ConversationView).status_code == 200
    assert dispatch(MessagesView, 'post', user_id=43).status_code == 200


def test_confirmation_budget_is_separate_and_bounded(dispatch):
    for _ in range(12):
        assert dispatch(MessagesView, 'post').status_code == 200
    for _ in range(20):
        assert dispatch(ConfirmActionView, 'post').status_code == 200
    assert dispatch(ConfirmActionView, 'post').status_code == 429
    assert dispatch(CapabilitiesView).status_code == 200
    assert dispatch(ConversationsView, 'post').status_code == 200


def test_ordinary_write_budget_shared_without_blocking_reads_or_confirmations(dispatch):
    operations = ((ConversationsView, 'post'), (ConversationView, 'delete'),
                  (FeedbackView, 'post'), (RecordSelectionView, 'post'))
    for index in range(60):
        assert dispatch(*operations[index % len(operations)]).status_code == 200
    for view, method in operations:
        assert dispatch(view, method).status_code == 429
    assert dispatch(CapabilitiesView).status_code == 200
    assert dispatch(MessagesView, 'post').status_code == 200
    assert dispatch(ConfirmActionView, 'post').status_code == 200


def test_read_budget_is_bounded_separately(dispatch):
    for _ in range(120):
        assert dispatch(CapabilitiesView).status_code == 200
    assert dispatch(ConversationView).status_code == 429
    assert dispatch(MessagesView, 'post').status_code == 200
    assert dispatch(ConfirmActionView, 'post').status_code == 200
