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
    """
    Small wrapper that is awaitable (so consumers can `await scope["user"]`)
    and, if constructed with an immediate user instance, exposes attributes
    synchronously (so tests can read `scope["user"].is_anonymous`).
    If constructed with a coroutine, attribute access before awaiting will raise.
    """

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
        else:

            async def _wrap():
                self._user = await self._coro
                return self._user

            return _wrap().__await__()


class SimpleJwtTokenAuthMiddleware(BaseMiddleware):
    """
    Simple JWT Token authorization middleware for Django Channels 3,
    ?token=<Token> querystring is required with the endpoint using this authentication
    middleware to work in synergy with Simple JWT
    """

    def __init__(self, inner):
        super().__init__(inner)
        self.inner = inner

    @staticmethod
    def get_user_from_token(user_id):
        return CustomUser.objects.get(pk=user_id)

    @staticmethod
    def get_anonymous_user():
        return AnonymousUser()

    async def __call__(self, scope, receive, send):
        # Close old database connections to prevent
        # usage of timed out connections
        close_old_connections()

        # Get the token
        token = parse_qs(scope["query_string"].decode("utf8"))["token"][0]
        try:
            # This will automatically validate the token and raise an error if token is invalid
            UntypedToken(token)  # type: ignore[arg-type]
        except (InvalidToken, TokenError):
            # immediate AnonymousUser but awaitable for consumers
            anon = self.get_anonymous_user()
            scope["user"] = _AwaitableUser(anon)  # type: ignore[arg-type]
        else:
            # Then token is valid, decode it and keep DB call as coroutine, wrapped to be awaitable
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user_coro = database_sync_to_async(self.get_user_from_token)(
                decoded_data["user_id"]
            )
            scope["user"] = _AwaitableUser(user_coro)  # type: ignore[arg-type]
        return await super().__call__(scope, receive, send)


def simplejwttokenauthmiddlewarestack(inner):
    return SimpleJwtTokenAuthMiddleware(AuthMiddlewareStack(inner))
