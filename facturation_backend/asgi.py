import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "facturation_backend.settings")

# Avoid daphne apps not loaded yet
import django

django.setup()

from django.core.asgi import get_asgi_application
from ws.jwt_middleware import SimpleJwtTokenAuthMiddleware
from channels.routing import ProtocolTypeRouter, URLRouter
from ws.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": SimpleJwtTokenAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
