from . import consumers
from django.urls import path

websocket_urlpatterns = [
    path('ws', consumers.ChatConsumer.as_asgi()),
]
