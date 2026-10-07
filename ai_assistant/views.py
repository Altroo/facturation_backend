from django.conf import settings
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from .client import AiAssistantClient
from .exceptions import AssistantDisabled
from .serializers import AssistRequestSerializer


class AssistantThrottle(UserRateThrottle):
    rate = "10/minute"


class AssistView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (AssistantThrottle,)

    def post(self, request):
        if not settings.AI_ASSISTANT_ENABLED:
            raise AssistantDisabled()
        serializer = AssistRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(AiAssistantClient().assist(**serializer.validated_data))
