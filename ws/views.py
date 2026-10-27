from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
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
        # Mobile has its own history. Existing web clients keep their current feed.
        platform = request.query_params.get("platform", ChangelogEntry.Platform.WEB)
        if platform not in (ChangelogEntry.Platform.WEB, ChangelogEntry.Platform.MOBILE):
            raise ValidationError({"platform": "Choose web or mobile."})
        platforms = (platform,) if platform == ChangelogEntry.Platform.MOBILE else (platform, ChangelogEntry.Platform.BOTH)
        entries = ChangelogEntry.objects.filter(
            is_published=True,
            date__lte=timezone.localdate(),
            platform__in=platforms,
        )
        return Response(
            ChangelogEntrySerializer(entries, many=True).data,
            headers={"Cache-Control": "no-store"},
        )
