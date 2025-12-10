import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

from facturation_backend.asgi import application
from ws.jwt_middleware import (
    SimpleJwtTokenAuthMiddleware,
    simplejwttokenauthmiddlewarestack,
)
from ws.jwt_middleware import _AwaitableUser


@pytest.mark.asyncio
@pytest.mark.django_db
class TestWebSocketConsumer:
    async def async_setup(self):
        self.user_model = get_user_model()

        def _create_user_sync():
            return self.user_model.objects.create_user(
                email="wsuser@example.com", password="pass"
            )

        def _generate_token_sync(user_obj):
            return str(AccessToken.for_user(user_obj))

        create_user = database_sync_to_async(_create_user_sync)
        generate_token = database_sync_to_async(_generate_token_sync)

        self.user = await create_user()
        self.token = await generate_token(self.user)

    async def test_echo_message(self):
        await self.async_setup()

        communicator = WebsocketCommunicator(application, f"/ws?token={self.token}")
        connected, _ = await communicator.connect()
        assert connected

        await communicator.send_json_to({"message": "Hello WebSocket!"})
        response = await communicator.receive_json_from()
        assert response["message"] == "Hello WebSocket!"

        await communicator.disconnect()

    async def test_invalid_token_sets_anonymous_user(self):
        # connect with an invalid token; middleware should set AnonymousUser
        communicator = WebsocketCommunicator(application, "/ws?token=invalidtoken")
        connected, _ = await communicator.connect()
        assert connected
        assert communicator.scope["user"].is_anonymous  # type: ignore[arg-type]
        await communicator.disconnect()

    async def test_simplejwttokenauthmiddlewarestack_returns_middleware(self):
        # helper should wrap an inner app and return the middleware instance
        result = simplejwttokenauthmiddlewarestack(lambda scope, receive, send: None)
        assert callable(result)
        assert isinstance(result, SimpleJwtTokenAuthMiddleware)

    async def test_awaitableuser_exposes_attributes_when_immediate(self):
        wrapper = _AwaitableUser(AnonymousUser())
        # Should expose attributes synchronously
        assert wrapper.is_anonymous

    async def test_awaitableuser_raises_before_awaiting_for_coro(self):
        async def make_user():
            class U:
                is_anonymous = False

            return U()

        coro = make_user()
        wrapper = _AwaitableUser(coro)
        # Accessing attribute before awaiting should raise
        with pytest.raises(AttributeError):
            _ = wrapper.is_anonymous

        # After awaiting, attribute should be available
        user_obj = await wrapper
        assert user_obj.is_anonymous is False
