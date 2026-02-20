from dj_rest_auth.jwt_auth import get_refresh_view
from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView

from .views import (
    LoginView,
    LogoutView,
    PasswordResetView,
    PasswordChangeView,
    SendPasswordResetView,
    CheckEmailView,
    ProfileView,
    GroupView,
    UsersListCreateView,
    UserDetailEditDeleteView,
    BulkDeleteUsersView,
)

app_name = "account"

urlpatterns = [
    # POST : Login with raw email/password
    path("login/", LoginView.as_view(), name="login"),
    # POST : Logout
    path("logout/", LogoutView.as_view(), name="logout"),
    # GET : Check if email already exists
    path("check_email/", CheckEmailView.as_view(), name="check_email"),
    # PUT : Password change
    path("password_change/", PasswordChangeView.as_view(), name="password_change"),
    # POST : Password reset
    path(
        "send_password_reset/",
        SendPasswordResetView.as_view(),
        name="send_password_reset",
    ),
    # GET : check if email & code are valid
    # PUT : reset with new password
    path("password_reset/", PasswordResetView.as_view(), name="password_reset"),
    path(
        "password_reset/<str:email>/<str:code>/",
        PasswordResetView.as_view(),
        name="password_reset_detail",
    ),
    # PATCH : Edit profil
    # GET : Get profil data include avatar
    path("profil/", ProfileView.as_view(), name="profil"),
    # GET : Get group permission
    path("group/", GroupView.as_view(), name="group"),
    # GET : Users list
    path("users/", UsersListCreateView.as_view(), name="users"),
    # DELETE : Bulk delete users
    path("users/bulk_delete/", BulkDeleteUsersView.as_view(), name="users-bulk-delete"),
    # GET user detail, PUT update, DELETE
    path("users/<int:pk>/", UserDetailEditDeleteView.as_view(), name="users_detail"),
    # POST : Tokens, Verify if token valid, Refresh access token
    path("token_verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("token_refresh/", get_refresh_view().as_view(), name="token_refresh"),
]
