from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.db import close_old_connections
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from jwt import decode as jwt_decode
from channels.middleware import BaseMiddleware
from django.conf import settings
from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from account.models import CustomUser


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

        # Get the token
        token = parse_qs(scope["query_string"].decode("utf8"))["token"][0]
        try:
            # This will automatically validate the token and raise an error if token is invalid
            UntypedToken(token)
        except (InvalidToken, TokenError):
            scope['user'] = AnonymousUser()
        else:
            #  Then token is valid, decode it
            decoded_data = jwt_decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user = self.get_user_from_token(decoded_data['user_id'])
            scope['user'] = user
        return await super().__call__(scope, receive, send)


def simplejwttokenauthmiddlewarestack(inner):
    return SimpleJwtTokenAuthMiddleware(AuthMiddlewareStack(inner))
