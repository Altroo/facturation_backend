from rest_framework import permissions
from dj_rest_auth.views import LoginView as Dj_rest_login
from dj_rest_auth.views import LogoutView as Dj_rest_logout
from dj_rest_auth.views import PasswordChangeView as Dj_rest_Password_change
from dj_rest_auth.views import PasswordResetView as Dj_rest_password_reset
from dj_rest_auth.views import PasswordResetConfirmView as Dj_rest_password_reset_confirm


class LoginView(Dj_rest_login):
    def login(self):
        return super(LoginView, self).login()


class LogoutView(Dj_rest_logout):
    permission_classes = (permissions.IsAuthenticated,)

    def logout(self, request):
        return super(LogoutView, self).logout(request)


class PasswordChangeView(Dj_rest_Password_change):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        return super(PasswordChangeView, self).post(request, *args, **kwargs)


class PasswordResetView(Dj_rest_password_reset):

    def post(self, request, *args, **kwargs):
        return super(PasswordResetView, self).post(request, *args, **kwargs)


class PasswordResetConfirmView(Dj_rest_password_reset_confirm):

    def post(self, request, *args, **kwargs):
        return super(PasswordResetConfirmView, self).post(request, *args, **kwargs)
