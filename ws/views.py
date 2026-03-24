from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ws.models import WsMaintenanceState


class GetMaintenanceView(APIView):
    permission_classes = (permissions.AllowAny,)

    @staticmethod
    def get(request, *args, **kwargs):
        maintenance_state = WsMaintenanceState.objects.order_by("-updated_at").first()
        data = {
            "maintenance": bool(maintenance_state.maintenance) if maintenance_state else False,
        }
        return Response(data=data, status=status.HTTP_200_OK)
