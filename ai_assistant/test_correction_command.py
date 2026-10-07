"""Regression coverage for private-service outages during spelling preparation."""

from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from rest_framework.exceptions import Throttled

from ai_assistant import client
from ai_assistant.exceptions import AssistantDisabled, ModelTimeout, ModelUnavailable
from ai_assistant.management.commands import ai_correct_texts as command


@pytest.fixture
def assist():
    target = (
        "ai_assistant.client.AiAssistantClient.assist"
        if hasattr(client, "AiAssistantClient")
        else "ai_assistant.service.AiAssistantService.assist"
    )
    with patch(target) as mocked:
        yield mocked


def upstream_failure(status):
    error = ModelUnavailable()
    error.__cause__ = HTTPError("http://private.invalid", status, "hidden", {}, None)
    return error


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 422])
def test_permanent_gateway_error_is_not_retried(assist, status):
    assist.side_effect = upstream_failure(status)
    with patch.object(command.time, "sleep") as sleep:
        with pytest.raises(ModelUnavailable) as caught:
            command.correct_text("Texte corrige", [])
    assert assist.call_count == 1
    sleep.assert_not_called()
    assert command.service_http_status(caught.value) == status
    assert f"HTTP {status}" in command.service_failure_reason(caught.value)


def test_transient_outage_has_bounded_retries(assist):
    assist.side_effect = upstream_failure(503)
    with patch.object(command.time, "sleep") as sleep:
        with pytest.raises(ModelUnavailable):
            command.correct_text("Texte corrige", [])
    assert assist.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [5, 10]


def test_timeout_can_recover_before_stopping(assist):
    assist.side_effect = [ModelTimeout(), {"suggested_text": "Texte corrigé"}]
    with patch.object(command.time, "sleep") as sleep:
        assert command.correct_text("Texte corrige", []) == "Texte corrigé"
    sleep.assert_called_once_with(5)


def test_throttling_keeps_existing_rate_limit(assist):
    assist.side_effect = [Throttled(wait=60), {"suggested_text": "Texte corrigé"}]
    with patch.object(command.time, "sleep") as sleep:
        assert command.correct_text("Texte corrige", []) == "Texte corrigé"
    sleep.assert_called_once_with(60)


def test_disabled_service_stops_without_retry(assist):
    assist.side_effect = AssistantDisabled()
    with patch.object(command.time, "sleep") as sleep:
        with pytest.raises(AssistantDisabled):
            command.correct_text("Texte corrige", [])
    assert assist.call_count == 1
    sleep.assert_not_called()


def test_interrupt_is_not_swallowed_or_retried(assist):
    assist.side_effect = KeyboardInterrupt()
    with patch.object(command.time, "sleep") as sleep:
        with pytest.raises(KeyboardInterrupt):
            command.correct_text("Texte corrige", [])
    assert assist.call_count == 1
    sleep.assert_not_called()


def test_remaining_time_displays_days_and_hours():
    assert command.remaining_time(90) == "1 min 30 s"
    assert command.remaining_time(3665) == "1 h 1 min"
    assert command.remaining_time(90065) == "1 j 1 h 1 min"


@pytest.mark.parametrize("body, expected", [
    (b'{"detail":"Rejected", "code":"ai_invalid_response"}', "InvalidModelResponse"),
    (b"<html>Bad Gateway</html>", "ModelUnavailable"),
    (b'{"detail":"Bad Gateway"}', "ModelUnavailable"),
])
def test_gateway_distinguishes_rejected_answer_from_proxy_outage(settings, body, expected):
    from io import BytesIO
    from ai_assistant.exceptions import InvalidModelResponse
    settings.AI_ASSISTANT_ENABLED = True
    settings.AI_ASSISTANT_SERVICE_NAME = "test"
    settings.AI_ASSISTANT_SERVICE_SECRET = "test-only"
    settings.AI_ASSISTANT_GATEWAY_URL = "http://private.invalid"
    settings.AI_ASSISTANT_TIMEOUT_SECONDS = 5
    error = HTTPError("http://private.invalid", 502, "hidden", {}, BytesIO(body))
    kind = InvalidModelResponse if expected == "InvalidModelResponse" else ModelUnavailable
    with patch("ai_assistant.client.request.urlopen", side_effect=error):
        with pytest.raises(kind):
            client.AiAssistantClient().assist(action="fix_grammar", text="Texte")
