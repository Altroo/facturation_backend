import json
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser


class SSOExchangeView(APIView):
    permission_classes = (permissions.AllowAny,)

    @staticmethod
    def _verify_code(code):
        payload = json.dumps(
            {
                "app": settings.EBH_SSO_APP_SLUG,
                "code": code,
                "service_secret": settings.EBH_SSO_SHARED_SECRET,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            settings.EBH_SSO_VERIFY_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise PermissionDenied(detail or "SSO verification failed.")
        except urllib.error.URLError:
            raise ValidationError({"sso": ["Service SSO indisponible."]})

    @staticmethod
    def _get_or_create_user(claims):
        sso_subject = str(claims["sub"])
        email = str(claims["email"]).strip().lower()
        first_name = claims.get("first_name") or ""
        last_name = claims.get("last_name") or ""

        with transaction.atomic():
            user = CustomUser.objects.filter(sso_subject=sso_subject).first()
            if user is None:
                user = CustomUser.objects.filter(email=email).first()
            if user is None:
                user = CustomUser(email=email, is_active=True)
                user.set_unusable_password()

            user.sso_subject = sso_subject
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.default_password_set = False
            user.save()
            return user

    @staticmethod
    def post(request, *args, **kwargs):
        code = request.data.get("code")
        if not code:
            raise ValidationError({"code": ["Code SSO requis."]})

        claims = SSOExchangeView._verify_code(code).get("user")
        if not claims:
            raise ValidationError({"sso": ["Réponse SSO invalide."]})

        user = SSOExchangeView._get_or_create_user(claims)
        if not user.is_active:
            raise PermissionDenied("Compte désactivé.")

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        now = timezone.now()
        return Response(
            {
                "user": {
                    "pk": user.pk,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "access": str(access),
                "refresh": str(refresh),
                "access_expiration": (
                    now + jwt_settings.ACCESS_TOKEN_LIFETIME
                ).isoformat(),
                "refresh_expiration": (
                    now + jwt_settings.REFRESH_TOKEN_LIFETIME
                ).isoformat(),
            },
            status=status.HTTP_200_OK,
        )
