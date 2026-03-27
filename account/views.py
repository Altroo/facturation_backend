from datetime import timedelta, datetime, timezone as dt_timezone

from django.utils import timezone as dj_timezone
import hmac
import logging
from os import remove
import secrets
from string import digits, ascii_letters
from sys import platform

from celery import current_app
from dj_rest_auth.views import LoginView as Dj_rest_login
from dj_rest_auth.views import LogoutView as Dj_rest_logout
from django.conf import settings
from django.core.exceptions import (
    SuspiciousFileOperation,
    ValidationError as DjangoValidationError,
)
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from account.models import Membership, Role
from core.constants import ROLES_RESTRICTED
from facturation_backend.utils import CustomPagination
from .filters import UsersFilter
from .models import CustomUser
from .serializers import (
    PasswordResetSerializer,
    ChangePasswordSerializer,
    UserEmailSerializer,
    CreateAccountSerializer,
    ProfileGETSerializer,
    ProfilePutSerializer,
    UsersListSerializer,
    UserDetailSerializer,
    UserPatchSerializer,
)
from .tasks import (
    send_email,
    start_deleting_expired_codes,
    generate_user_thumbnail,
)

logger = logging.getLogger(__name__)


class CheckEmailView(APIView):
    permission_classes = (permissions.IsAdminUser,)
    errors = {
        "email": ["Un utilisateur avec ce champ adresse électronique existe déjà."]
    }

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        if not email:
            raise ValidationError({"email": ["L'adresse électronique est requise."]})

        email = str(email).strip().lower()

        try:
            validate_email(email)
        except DjangoValidationError:
            raise ValidationError(
                {"email": ["Entrez une adresse électronique valide."]}
            )

        try:
            CustomUser.objects.get(email=email)
            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(Dj_rest_login):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def login(self):
        return super(LoginView, self).login()

    def get_response(self):
        response = super().get_response()
        # dj-rest-auth strips the refresh token from the JSON body when
        # JWT_AUTH_HTTPONLY is True.  The NextAuth frontend needs it in the
        # body so it can send it back for token refresh, so re-inject it.
        if (
            response.status_code == status.HTTP_200_OK
            and hasattr(self, "refresh_token")
            and not response.data.get("refresh")
        ):
            response.data["refresh"] = str(self.refresh_token)
        return response


class LogoutView(Dj_rest_logout):
    permission_classes = (permissions.IsAuthenticated,)

    def logout(self, request):
        return super(LogoutView, self).logout(request)


class TokenRefreshView(APIView):
    """Custom token refresh that always returns the rotated refresh token
    and its expiration in the JSON body, regardless of JWT_AUTH_HTTPONLY.

    dj-rest-auth's default refresh view strips the refresh token from the
    response when JWT_AUTH_HTTPONLY is True and never returns
    refresh_expiration in that mode.  The NextAuth frontend needs both
    values to keep the session alive across token rotations."""

    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        from dj_rest_auth.jwt_auth import CookieTokenRefreshSerializer, set_jwt_cookies
        from rest_framework_simplejwt.settings import (
            api_settings as jwt_settings,
        )

        serializer = CookieTokenRefreshSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        access = serializer.validated_data["access"]
        refresh = serializer.validated_data.get("refresh", "")

        data = {
            "access": access,
            "access_expiration": (
                dj_timezone.now() + jwt_settings.ACCESS_TOKEN_LIFETIME
            ).isoformat(),
        }
        if refresh:
            data["refresh"] = refresh
            data["refresh_expiration"] = (
                dj_timezone.now() + jwt_settings.REFRESH_TOKEN_LIFETIME
            ).isoformat()

        response = Response(data, status=status.HTTP_200_OK)
        set_jwt_cookies(response, access, refresh or "")
        return response


class PasswordChangeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def put(request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            # check old password
            old_password = serializer.data.get("old_password")
            new_password = serializer.data.get("new_password")
            new_password2 = serializer.data.get("new_password2")
            user = request.user
            if not user.check_password(old_password):
                errors = {"old_password": ["Votre mot de passe est invalide."]}
                raise ValidationError(errors)
            if new_password != new_password2:
                errors = {"new_password2": ["Les mots de passe ne correspondent pas."]}
                raise ValidationError(errors)
            if len(new_password) < 8:
                errors = {
                    "new_password": [
                        "Le mot de passe doit contenir au moins 8 caractères."
                    ]
                }
                raise ValidationError(errors)
            user.set_password(serializer.data.get("new_password"))
            user.default_password_set = False
            user.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        raise ValidationError(serializer.errors)


class PasswordResetView(APIView):
    permission_classes = (permissions.AllowAny,)
    errors = {"error": ["Utilisateur ou code verification invalide."]}

    def get(self, request, *args, **kwargs):
        email = kwargs.get("email")
        if not email:
            raise ValidationError({"email": ["L'adresse électronique est requise."]})

        email = str(email).strip().lower()

        try:
            validate_email(email)
        except DjangoValidationError:
            raise ValidationError(
                {"email": ["Entrez une adresse électronique valide."]}
            )

        code = kwargs.get("code")

        try:
            user = CustomUser.objects.get(email=email)
            stored_code = user.password_reset_code or ""
            if (
                code is not None
                and stored_code
                and hmac.compare_digest(str(code), stored_code)
            ):
                # Check if code is still valid (5-minute window)
                if user.password_reset_code_created_at:
                    time_elapsed = (
                        datetime.now(dt_timezone.utc) - user.password_reset_code_created_at
                    )
                    if time_elapsed > timedelta(minutes=5):
                        raise ValidationError(
                            {
                                "code": [
                                    "Le code de réinitialisation a expiré. Veuillez demander un nouveau code."
                                ]
                            }
                        )
                return Response(status=status.HTTP_204_NO_CONTENT)
            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)

    def put(self, request, *args, **kwargs):
        raw_email = request.data.get("email")
        if not raw_email or not isinstance(raw_email, str) or not raw_email.strip():
            raise ValidationError({"email": ["This field is required."]})
        email = raw_email.strip().lower()
        try:
            validate_email(email)
        except DjangoValidationError:
            raise ValidationError({"email": ["Enter a valid email address."]})
        code = request.data.get("code")
        try:
            user = CustomUser.objects.get(email=email)
            stored_code = user.password_reset_code or ""
            if (
                code is not None
                and email is not None
                and stored_code
                and hmac.compare_digest(str(code), stored_code)
            ):
                # Check if code is still valid (5-minute window)
                if user.password_reset_code_created_at:
                    time_elapsed = (
                        datetime.now(dt_timezone.utc) - user.password_reset_code_created_at
                    )
                    if time_elapsed > timedelta(minutes=5):
                        raise ValidationError(
                            {
                                "code": [
                                    "Le code de réinitialisation a expiré. Veuillez demander un nouveau code."
                                ]
                            }
                        )

                serializer = PasswordResetSerializer(data=request.data)
                if serializer.is_valid():
                    with transaction.atomic():
                        # revoke 24h previous periodic task (default password_reset)
                        if user.task_id_password_reset:
                            task_id_password_reset = user.task_id_password_reset
                            try:
                                if platform == "win32":
                                    # Windows : signal POSIX
                                    current_app.control.revoke(
                                        task_id_password_reset, terminate=False
                                    )
                                else:
                                    # Unix :
                                    current_app.control.revoke(
                                        task_id_password_reset,
                                        terminate=True,
                                        signal="SIGKILL",
                                    )
                            except Exception as e:
                                # Log but continue - task revocation failure shouldn't block password reset
                                logger.warning(
                                    f"Failed to revoke task {task_id_password_reset}: {e}"
                                )

                            user.task_id_password_reset = None
                            user.save(update_fields=["task_id_password_reset"])

                        user.set_password(serializer.data.get("new_password"))
                        user.password_reset_code = None
                        user.password_reset_code_created_at = None
                        user.default_password_set = False
                        user.save(
                            update_fields=[
                                "password",
                                "password_reset_code",
                                "password_reset_code_created_at",
                                "default_password_set",
                            ]
                        )

                    return Response(status=status.HTTP_204_NO_CONTENT)
                raise ValidationError(serializer.errors)

            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)


class SendPasswordResetView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"
    # Generic message to prevent account enumeration
    success_message = (
        "Si un compte existe avec cet email, un code de vérification vous sera envoyé."
    )
    errors = {"email": ["Aucun compte existant utilisant cette adresse électronique."]}

    @staticmethod
    def generate_random_code(length=6):
        """Generate a cryptographically secure random code using secrets module."""
        return "".join(secrets.choice(digits) for _ in range(length))

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        if not email:
            raise ValidationError({"email": ["L'adresse électronique est requise."]})

        email = str(email).strip().lower()

        try:
            validate_email(email)
        except DjangoValidationError:
            raise ValidationError(
                {"email": ["Entrez une adresse électronique valide."]}
            )

        try:
            user = CustomUser.objects.get(email=email)
            if user.email is not None:
                serializer = UserEmailSerializer(data=request.data)
                if serializer.is_valid():
                    with transaction.atomic():
                        # revoke 24h previous periodic task (default password reset)
                        task_id_password_reset = user.task_id_password_reset
                        if task_id_password_reset:
                            try:
                                if platform == "win32":
                                    # Windows : signal POSIX
                                    current_app.control.revoke(
                                        task_id_password_reset, terminate=False
                                    )
                                else:
                                    # Unix :
                                    current_app.control.revoke(
                                        task_id_password_reset,
                                        terminate=True,
                                        signal="SIGKILL",
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to revoke task {task_id_password_reset}: {e}"
                                )

                            user.task_id_password_reset = None
                            user.save(update_fields=["task_id_password_reset"])

                        mail_subject = "Renouvellement du mot de passe - E.B.H Facturation"
                        mail_template = "password_reset.html"
                        code = self.generate_random_code()
                        message = render_to_string(
                            mail_template,
                            {
                                "first_name": user.first_name,
                                "code": code,
                                "frontend_url": settings.FRONTEND_URL,
                            },
                        )
                        send_email.apply_async(
                            (
                                user.pk,
                                user.email,
                                mail_subject,
                                message,
                                code,
                                "password_reset_code",
                            ),
                        )
                        date_now = datetime.now(dt_timezone.utc)
                        # Set code creation timestamp for 5-minute expiration
                        user.password_reset_code_created_at = date_now
                        shift = date_now + timedelta(hours=24)
                        task_id_password_reset = (
                            start_deleting_expired_codes.apply_async(
                                (user.pk, "password_reset"), eta=shift
                            )
                        )
                        user.task_id_password_reset = task_id_password_reset.id
                        user.save(
                            update_fields=[
                                "task_id_password_reset",
                                "password_reset_code_created_at",
                            ]
                        )
                    return Response(status=status.HTTP_204_NO_CONTENT)
                raise ValidationError(serializer.errors)
            else:
                # Return same 204 response to prevent account enumeration
                return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomUser.DoesNotExist:
            # Return same 204 response to prevent account enumeration
            return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    errors = {"error": ["Utilisateur n'éxiste pas!"]}

    def get(self, request, *args, **kwargs):
        try:
            user = CustomUser.objects.get(pk=request.user.pk)
            user_serializer = ProfileGETSerializer(user)
            # group_names = list(user.groups.values_list("name", flat=True))
            user_data = {
                **user_serializer.data,
                "is_staff": user.is_staff,
            }
            return Response(user_data, status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)

    @staticmethod
    def patch(request, *args, **kwargs):
        user = request.user
        data = {
            "first_name": request.data.get("first_name"),
            "last_name": request.data.get("last_name"),
            "gender": request.data.get("gender", ""),
            "avatar": request.data.get("avatar"),  # Can be base64, URL, or file
            "avatar_cropped": request.data.get(
                "avatar_cropped"
            ),  # Can be base64, URL, or file
        }
        # Initialize serializer with context for URL building
        serializer = ProfilePutSerializer(
            instance=user, data=data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            updated_account = serializer.save()
            # Build response data
            user_data = {
                **serializer.data,
                "id": updated_account.pk,
                "avatar": updated_account.get_absolute_avatar_img,
                "avatar_cropped": updated_account.get_absolute_avatar_cropped_img,
                "date_joined": updated_account.date_joined,
                "is_staff": updated_account.is_staff,
            }
            return Response(user_data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)


class GroupView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        titles = list(Role.objects.values_list("name", flat=True))
        return Response({"group_titles": titles}, status=status.HTTP_200_OK)


class UsersListCreateView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def generate_random_password(length=8):
        characters = digits + ascii_letters
        return "".join(secrets.choice(characters) for _ in range(length))

    @staticmethod
    def get(request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        queryset = CustomUser.objects.all().exclude(pk=request.user.pk)
        filterset = UsersFilter(request.GET, queryset=queryset)
        queryset = filterset.qs.order_by("-date_joined")
        if pagination:
            paginator = CustomPagination()
            page = paginator.paginate_queryset(queryset, request)
            serializer = UsersListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        else:
            serializer = UsersListSerializer(queryset[:500], many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Check if user is Commercial - they cannot create users
        for membership in Membership.objects.filter(user=request.user).select_related(
            "role"
        ):
            if membership.role.name in ROLES_RESTRICTED:
                raise PermissionDenied(
                    _("Vous n'avez pas les droits pour créer des utilisateurs.")
                )

        avatar = request.data.get("avatar")  # Can be base64, or file
        avatar_cropped = request.data.get("avatar_cropped")  # Can be base64, or file
        password = self.generate_random_password()

        data = request.data.copy()
        data["password"] = password
        data["email"] = str(data.get("email", "")).lower()
        data["default_password_set"] = True

        serializer = CreateAccountSerializer(
            data=data,
            context={"request": request},
        )
        if serializer.is_valid():
            user = serializer.save()
            # Generate user avatar and thumbnail if not provided
            if avatar == "" or avatar_cropped == "":
                generate_user_thumbnail.apply_async(
                    (user.pk,),
                )
            mail_subject = "Invitation - Application de E.B.H Facturation"
            mail_template = "new_account.html"
            message = render_to_string(
                mail_template, {"first_name": user.first_name, "password": password, "frontend_url": settings.FRONTEND_URL}
            )
            send_email.apply_async(
                (user.pk, user.email, mail_subject, message),
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        raise ValidationError(serializer.errors)


class UserDetailEditDeleteView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def get_object(pk):
        try:
            user = CustomUser.objects.prefetch_related(
                "memberships__company",
                "memberships__role",
            ).get(pk=pk)
        except CustomUser.DoesNotExist:
            raise Http404(_("Aucune utilisateur ne correspond à la requête."))
        return user

    def get(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        if pk == request.user.pk:
            raise Http404(_("Aucune utilisateur ne correspond à la requête."))
        user = self.get_object(pk)
        serializer = UserDetailSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, *args, **kwargs):
        # Check if user is Commercial - they cannot update users
        for membership in Membership.objects.filter(user=request.user).select_related(
            "role"
        ):
            if membership.role.name in ROLES_RESTRICTED:
                raise PermissionDenied(
                    _("Vous n'avez pas les droits pour modifier des utilisateurs.")
                )

        pk = kwargs.get("pk")
        if pk == request.user.pk:
            raise Http404(
                _("Vous ne pouvez pas modifier votre utilisateur dans cette page.")
            )
        user = self.get_object(pk)
        serializer = UserPatchSerializer(
            user, data=request.data, context={"request": request}, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)

    def delete(self, request, *args, **kwargs):
        # Check if user is Commercial - they cannot delete users
        for membership in Membership.objects.filter(user=request.user).select_related(
            "role"
        ):
            if membership.role.name in ROLES_RESTRICTED:
                raise PermissionDenied(
                    _("Vous n'avez pas les droits pour supprimer des utilisateurs.")
                )

        pk = kwargs.get("pk")
        if pk == request.user.pk:
            raise Http404(_("Vous ne pouvez pas supprimer votre utilisateur."))
        user = self.get_object(pk)
        media_paths_list = []
        if user.avatar:
            media_paths_list.append(user.avatar.path)
        if user.avatar_cropped:
            media_paths_list.append(user.avatar_cropped.path)
        for media_path in media_paths_list:
            try:
                remove(media_path)
            except (ValueError, SuspiciousFileOperation, FileNotFoundError):
                pass
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkDeleteUsersView(APIView):
    """DELETE a list of users by ID. Admin-only endpoint."""

    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def delete(request, *args, **kwargs):
        ids = request.data.get("ids")
        if not ids or not isinstance(ids, list):
            raise ValidationError({"ids": _("Une liste d'identifiants est requise.")})

        ids = [int(i) for i in ids]

        # Cannot include the requesting user's own account
        if request.user.pk in ids:
            raise ValidationError(
                {"ids": _("Vous ne pouvez pas supprimer votre propre utilisateur.")}
            )

        users = list(CustomUser.objects.filter(pk__in=ids))
        if len(users) != len(ids):
            raise Http404(_("Certains utilisateurs sont introuvables."))

        with transaction.atomic():
            for user in users:
                media_paths_list = []
                if user.avatar:
                    media_paths_list.append(user.avatar.path)
                if user.avatar_cropped:
                    media_paths_list.append(user.avatar_cropped.path)
                for media_path in media_paths_list:
                    try:
                        remove(media_path)
                    except (ValueError, SuspiciousFileOperation, FileNotFoundError):
                        pass
            CustomUser.objects.filter(pk__in=ids).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
