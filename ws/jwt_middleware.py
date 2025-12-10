import asyncio
from typing import Any
from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from account.models import CustomUser


class _AwaitableUser:
    """Wraps a user or coroutine to be awaitable and expose attributes synchronously."""

    def __init__(self, coro_or_user: Any):
        if asyncio.iscoroutine(coro_or_user):
            self._coro = coro_or_user
            self._user = None
        else:
            self._coro = None
            self._user = coro_or_user

    def __getattr__(self, name: str) -> Any:
        if self._user is not None:
            return getattr(self._user, name)
        raise AttributeError(f"attribute {name!r} not available until user is awaited")

    def __await__(self):
        if self._user is not None:

            async def _ret():
                return self._user

            return _ret().__await__()

        async def _wrap():
            self._user = await self._coro
            return self._user

        return _wrap().__await__()


class SimpleJwtTokenAuthMiddleware(BaseMiddleware):
    """
    Simple JWT Token authorization middleware for Django Channels 3,
    ?token=<Token> querystring is reuired with the endpoint using this authentication
    middleware to work in synergy with Simple JWT
    """

    def __init__(self, inner):
        super().__init__(inner)
        self.inner = inner

    @database_sync_to_async
    def get_user_from_token(self, user_id):
        return CustomUser.objects.get(pk=user_id)

    async def __call__(self, scope, receive, send):
        # Close old database connections to prevent
        # usage of timed out connections
        close_old_connections()

        try:
            token = parse_qs(scope["query_string"].decode("utf8")).get("token", [None])[
                0
            ]
        except (UnicodeDecodeError, KeyError, IndexError, TypeError):
            token = None

        if not token:
            scope["user"] = _AwaitableUser(AnonymousUser())  # type: ignore[arg-type]
            await self._reject_connection(send)
            return None

        try:
            UntypedToken(token)  # type: ignore[arg-type]
        except (InvalidToken, TokenError):
            scope["user"] = _AwaitableUser(AnonymousUser())  # type: ignore[arg-type]
            await self._reject_connection(send)
            return None

        try:
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user = self.get_user_from_token(decoded_data["user_id"])  # type: ignore[arg-type]
            scope["user"] = _AwaitableUser(user)  # type: ignore[arg-type]
        except (KeyError, CustomUser.DoesNotExist, jwt_decode.DecodeError):
            scope["user"] = _AwaitableUser(AnonymousUser())  # type: ignore[arg-type]
            await self._reject_connection(send)
            return None

        return await super().__call__(scope, receive, send)

    @staticmethod
    async def _reject_connection(send):
        """Reject WebSocket connection by closing it immediately."""
        await send(
            {
                "type": "websocket.close",
                "code": 4001,
            }
        )


def simplejwttokenauthmiddlewarestack(inner):
    return SimpleJwtTokenAuthMiddleware(AuthMiddlewareStack(inner))
