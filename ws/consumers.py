from json import dumps, loads

from channels.generic.websocket import AsyncWebsocketConsumer


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Consumer used to ws functionality
    this consumer provide the websocket for
    unentrupted communication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None

    async def connect(self):
        user = await self.scope["user"]
        self.group_name = "%s" % user.id
        # Join room group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """
        Method called every time a connection to websocket
        Is closed by the user or user is disconnected.
        """
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Method used to receive the message through
        websocket interface
        """
        text_data_json = loads(text_data)
        message = text_data_json["message"]

        # Send message to room group
        await self.channel_layer.group_send(
            self.group_name, {"type": "recieve_group_message", "message": message}
        )

    async def recieve_group_message(self, event):
        """
        Method used to broadcast the message the group
        """
        message = event["message"]
        await self.send(text_data=dumps({"message": message}))
