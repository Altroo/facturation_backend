from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ws.models import ChangelogEntry, maintenance_snapshot
from ws.serializers import ChangelogEntrySerializer


class GetMaintenanceView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = ()

    @staticmethod
    def get(request, *args, **kwargs):
        return Response(
            data=maintenance_snapshot(),
            status=status.HTTP_200_OK,
            headers={"Cache-Control": "no-store"},
        )


class ChangelogView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request):
        entries = ChangelogEntry.objects.filter(
            is_published=True, date__lte=timezone.localdate()
        )
        return Response(
            ChangelogEntrySerializer(entries, many=True).data,
            headers={"Cache-Control": "no-store"},
        )
