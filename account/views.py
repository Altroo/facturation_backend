from datetime import timedelta, timezone, datetime
from os import remove
from random import choice
from string import digits, ascii_letters
from sys import platform

from celery import current_app
from dj_rest_auth.views import LoginView as Dj_rest_login
from dj_rest_auth.views import LogoutView as Dj_rest_logout
from django.contrib.auth.models import Group
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import UsersFilter
from .models import CustomUser
from .pagination import UsersPagination
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
    resize_avatar_thumbnail,
)


class CheckEmailView(APIView):
    permission_classes = (permissions.IsAdminUser,)
    errors = {
        "email": ["Un utilisateur avec ce champ adresse électronique existe déjà."]
    }

    def get(self, request, *args, **kwargs):
        email = str(kwargs.get("email")).lower()
        try:
            CustomUser.objects.get(email=email)
            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(Dj_rest_login):
    def login(self):
        return super(LoginView, self).login()


class LogoutView(Dj_rest_logout):
    permission_classes = (permissions.IsAuthenticated,)

    def logout(self, request):
        return super(LogoutView, self).logout(request)


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
            user.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        raise ValidationError(serializer.errors)


class PasswordResetView(APIView):
    permission_classes = (permissions.AllowAny,)
    errors = {"error": ["Utilisateur ou code verification invalide."]}

    def get(self, request, *args, **kwargs):
        email = str(kwargs.get("email")).lower()
        code = kwargs.get("code")

        try:
            user = CustomUser.objects.get(email=email)
            if code is not None and code == user.password_reset_code:
                return Response(status=status.HTTP_204_NO_CONTENT)
            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)

    def put(self, request, *args, **kwargs):
        email = str(request.data.get("email")).lower()
        code = request.data.get("code")
        try:
            user = CustomUser.objects.get(email=email)
            if (
                code is not None
                and email is not None
                and code == str(user.password_reset_code)
            ):
                serializer = PasswordResetSerializer(data=request.data)
                if serializer.is_valid():
                    # revoke 24h previous periodic task (default password_reset)
                    if user.task_id_password_reset:
                        task_id_password_reset = user.task_id_password_reset
                        if platform == "win32":
                            # Windows : signal POSIX
                            current_app.control.revoke(
                                task_id_password_reset, terminate=False
                            )
                        else:
                            # Unix :
                            current_app.control.revoke(
                                task_id_password_reset, terminate=True, signal="SIGKILL"
                            )
                        user.task_id_password_reset = None
                        user.save()
                    user.set_password(serializer.data.get("new_password"))
                    user.password_reset_code = None
                    user.save()
                    return Response(status=status.HTTP_204_NO_CONTENT)
                raise ValidationError(serializer.errors)

            raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)


class SendPasswordResetView(APIView):
    permission_classes = (permissions.AllowAny,)
    errors = {"email": ["Aucun compte existant utilisant cette adresse éléctronique."]}

    @staticmethod
    def generate_random_code(length=4):
        return "".join(choice(digits) for _ in range(length))

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email")).lower()
        try:
            user = CustomUser.objects.get(email=email)
            if user.email is not None:
                serializer = UserEmailSerializer(data=request.data)
                if serializer.is_valid():
                    # revoke 24h previous periodic task (default password reset)
                    task_id_password_reset = user.task_id_password_reset
                    if task_id_password_reset:
                        if platform == "win32":
                            # Windows : signal POSIX
                            current_app.control.revoke(
                                task_id_password_reset, terminate=False
                            )
                        else:
                            # Unix :
                            current_app.control.revoke(
                                task_id_password_reset, terminate=True, signal="SIGKILL"
                            )
                        user.task_id_password_reset = None
                        user.save()
                    mail_subject = "Renouvellement du mot de passe"
                    mail_template = "password_reset.html"
                    code = self.generate_random_code()
                    message = render_to_string(
                        mail_template,
                        {
                            "first_name": user.first_name,
                            "code": code,
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
                    date_now = datetime.now(timezone.utc)
                    shift = date_now + timedelta(hours=24)
                    task_id_password_reset = start_deleting_expired_codes.apply_async(
                        (user.pk, "password_reset"), eta=shift
                    )
                    user.task_id_password_reset = str(task_id_password_reset)
                    user.save()
                    return Response(status=status.HTTP_204_NO_CONTENT)
                raise ValidationError(serializer.errors)
            else:
                raise ValidationError(self.errors)
        except CustomUser.DoesNotExist:
            raise ValidationError(self.errors)


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
        }
        # Initialize serializer with context for URL building
        serializer = ProfilePutSerializer(
            instance=user, data=data, partial=True, context={"request": request}
        )
        if serializer.is_valid():
            updated_account = serializer.save()
            # Trigger Celery task if we have avatar bytes
            avatar_bytes = getattr(updated_account, "_avatar_bytes_for_celery", None)
            if avatar_bytes:
                resize_avatar_thumbnail.apply_async((updated_account.pk, avatar_bytes))
            # Build response data
            user_data = {
                **serializer.data,
                "id": updated_account.pk,
                "avatar": updated_account.get_absolute_avatar_img,
                "date_joined": updated_account.date_joined,
                "is_staff": updated_account.is_staff,
            }
            return Response(user_data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)


class GroupView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def get(request, *args, **kwargs):
        titles = list(Group.objects.values_list("name", flat=True))
        return Response({"group_titles": titles}, status=status.HTTP_200_OK)


class UsersListCreateView(APIView):
    permission_classes = (permissions.IsAdminUser,)

    @staticmethod
    def generate_random_password(length=8):
        characters = digits + ascii_letters
        return "".join(choice(characters) for _ in range(length))

    @staticmethod
    def get(request, *args, **kwargs):
        pagination = request.query_params.get("pagination", "false").lower() == "true"
        queryset = CustomUser.objects.all().exclude(pk=request.user.pk)
        if pagination:
            paginator = UsersPagination()
            filterset = UsersFilter(request.GET, queryset=queryset)
            queryset = filterset.qs.order_by("-date_joined")
            page = paginator.paginate_queryset(queryset, request)
            serializer = UsersListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        else:
            serializer = UsersListSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        email = str(request.data.get("email")).lower()
        first_name = request.data.get("first_name")
        last_name = request.data.get("last_name")
        gender = request.data.get("gender")
        is_staff = request.data.get("is_staff")
        password = self.generate_random_password()

        serializer = CreateAccountSerializer(
            data={
                "email": email,
                "password": password,
                "password2": password,
                "first_name": first_name,
                "last_name": last_name,
                "gender": gender,
                "is_staff": is_staff,
            }
        )
        if serializer.is_valid():
            user = serializer.save()
            # Generate user avatar and thumbnail
            generate_user_thumbnail.apply_async(
                (user.pk,),
            )
            mail_subject = "Invitation (Facturation Casa Di Lusso)"
            mail_template = "new_account.html"
            message = render_to_string(
                mail_template, {"fist_name": user.first_name, "password": password}
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
            user = CustomUser.objects.get(pk=pk)
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
        pk = kwargs.get("pk")
        # if pk == request.user.pk:
        #     raise Http404(_("Vous ne pouvez pas modifier votre utilisateur dans cette page."))
        user = self.get_object(pk)
        serializer = UserPatchSerializer(
            user, data=request.data, context={"request": request}, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        raise ValidationError(serializer.errors)

    def delete(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        if pk == request.user.pk:
            raise Http404(_("Vous ne pouvez pas supprimer votre utilisateur."))
        user = self.get_object(pk)
        media_paths_list = []
        if user.avatar:
            media_paths_list.append(user.avatar.path)
        if user.avatar_thumbnail:
            media_paths_list.append(user.avatar_thumbnail.path)
        for media_path in media_paths_list:
            try:
                remove(media_path)
            except (ValueError, SuspiciousFileOperation, FileNotFoundError):
                pass
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
