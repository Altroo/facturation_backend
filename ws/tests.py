import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from unittest.mock import AsyncMock, MagicMock

from facturation_backend.asgi import application
from ws.jwt_middleware import (
    _AwaitableUser,
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


class TestAwaitableUserExtra:
    """Tests for _AwaitableUser class."""

    def test_with_user_directly(self):
        """Test _AwaitableUser with a user object directly."""
        user = MagicMock(email="test@example.com")
        awaitable = _AwaitableUser(user)
        assert awaitable.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_getattr_raises_when_not_awaited(self):
        """Test that getattr raises when user is coroutine and not awaited."""
        async def coro():
            return MagicMock(email="coro@example.com")
        coroutine = coro()
        awaitable = _AwaitableUser(coroutine)
        with pytest.raises(AttributeError, match="not available until user is awaited"):
            _ = awaitable.email
        # Properly await the coroutine to avoid RuntimeWarning
        await coroutine

    @pytest.mark.asyncio
    async def test_await_with_user(self):
        """Test awaiting _AwaitableUser with a direct user."""
        user = MagicMock(email="direct@example.com")
        awaitable = _AwaitableUser(user)
        result = await awaitable
        assert result == user

    @pytest.mark.asyncio
    async def test_await_with_coroutine(self):
        """Test awaiting _AwaitableUser with a coroutine."""
        async def get_user():
            return MagicMock(email="async@example.com")
        awaitable = _AwaitableUser(get_user())
        result = await awaitable
        assert result.email == "async@example.com"

    @pytest.mark.asyncio
    async def test_await_multiple_times(self):
        """Test awaiting multiple times returns same user."""
        user = MagicMock(id=123)
        awaitable = _AwaitableUser(user)
        result1 = await awaitable
        result2 = await awaitable
        assert result1 == result2


class TestSimpleJwtTokenAuthMiddlewareExtra:
    """Tests for SimpleJwtTokenAuthMiddleware."""

    @pytest.mark.asyncio
    async def test_call_with_unicode_decode_error(self):
        """Test handling of malformed query string."""
        inner = AsyncMock()
        middleware = SimpleJwtTokenAuthMiddleware(inner)
        scope = {"type": "websocket", "query_string": b"\xff\xfe"}
        send = AsyncMock()
        
        await middleware(scope, AsyncMock(), send)
        
        send.assert_called()
        assert send.call_args[0][0]["type"] == "websocket.close"
        assert send.call_args[0][0]["code"] == 4001

    @pytest.mark.asyncio
    async def test_call_without_token(self):
        """Test handling of missing token."""
        inner = AsyncMock()
        middleware = SimpleJwtTokenAuthMiddleware(inner)
        scope = {"type": "websocket", "query_string": b""}
        send = AsyncMock()
        
        await middleware(scope, AsyncMock(), send)
        
        assert isinstance(scope["user"], _AwaitableUser)
        send.assert_called()

    @pytest.mark.asyncio
    async def test_call_with_invalid_token(self):
        """Test handling of invalid token."""
        inner = AsyncMock()
        middleware = SimpleJwtTokenAuthMiddleware(inner)
        scope = {"type": "websocket", "query_string": b"token=invalid_jwt_token"}
        send = AsyncMock()
        
        await middleware(scope, AsyncMock(), send)
        
        send.assert_called()
        assert send.call_args[0][0]["type"] == "websocket.close"

    @pytest.mark.asyncio
    async def test_reject_connection_sends_close(self):
        """Test _reject_connection sends close message."""
        send = AsyncMock()
        await SimpleJwtTokenAuthMiddleware._reject_connection(send)
        send.assert_called_once_with({"type": "websocket.close", "code": 4001})


class TestSimpleJwtTokenAuthMiddlewareStackExtra:
    """Tests for simplejwttokenauthmiddlewarestack helper."""

    def test_returns_callable(self):
        """Test that helper returns a callable middleware."""
        result = simplejwttokenauthmiddlewarestack(MagicMock())
        assert callable(result)

    def test_wraps_inner_with_middleware(self):
        """Test that it wraps inner app with SimpleJwtTokenAuthMiddleware."""
        result = simplejwttokenauthmiddlewarestack(MagicMock())
        assert isinstance(result, SimpleJwtTokenAuthMiddleware)
