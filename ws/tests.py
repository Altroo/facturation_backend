import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from facturation_backend.asgi import application
from ws.jwt_middleware import (
    SimpleJwtTokenAuthMiddleware,
    simplejwttokenauthmiddlewarestack,
)


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

    async def test_invalid_token_sets_anonymous_user_and_rejects_connection(self):
        communicator = WebsocketCommunicator(application, "/ws?token=invalidtoken")
        connected, _ = await communicator.connect()
        assert not connected

    async def test_missing_token_rejects_connection(self):
        communicator = WebsocketCommunicator(application, "/ws")
        connected, _ = await communicator.connect()
        assert not connected

    async def test_simplejwttokenauthmiddlewarestack_returns_middleware(self):
        # helper should wrap an inner app and return the middleware instance
        result = simplejwttokenauthmiddlewarestack(lambda scope, receive, send: None)
        assert callable(result)
        assert isinstance(result, SimpleJwtTokenAuthMiddleware)
