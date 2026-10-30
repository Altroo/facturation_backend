import uuid
from datetime import timedelta

import pytest
from chat_ai_assistant.contracts import ChatAIError
from django.utils import timezone

from chat_ai.models import Conversation
from chat_ai.security import authorization_stamp
from chat_ai.tools.executor import ChatAIToolExecutor


def executor(s, user=None, company=None, state=None):
    return ChatAIToolExecutor(
        (user or s.user).pk, (company or s.a).pk, uuid.uuid4(), state
    )


def conv(s):
    return Conversation.objects.create(
        user=s.user,
        company=s.a,
        authorization_stamp=authorization_stamp(s.user.pk, s.a.pk),
        expires_at=timezone.now() + timedelta(days=1),
    )


def assert_code(code, func):
    with pytest.raises(ChatAIError) as exc:
        func()
    assert exc.value.code == code
