from django.urls import path
from .views import (LoginView, LogoutView, PasswordResetView, PasswordChangeView,
                    SendPasswordResetView, CheckEmailView, CreateAccountView)
from rest_framework_simplejwt.views import TokenVerifyView
from dj_rest_auth.jwt_auth import get_refresh_view

app_name = 'account'

urlpatterns = [
    # POST : Login with raw email/password
    path('login/', LoginView.as_view()),
    # POST : Logout
    path('logout/', LogoutView.as_view()),
    # POST : Create Account
    path('create_account/', CreateAccountView.as_view()),
    # POST : Check if email already exists
    path('check_email/', CheckEmailView.as_view()),
    # POST : Password change
    path('password_change/', PasswordChangeView.as_view()),
    # POST : Password reset
    path('send_password_reset/', SendPasswordResetView.as_view()),
    # GET : check if email & code are valid
    # PUT : reset with new password
    path('password_reset/', PasswordResetView.as_view()),
    path('password_reset/<str:email>/<str:code>/', PasswordResetView.as_view()),
    # POST : Tokens, Verify if token valid, Refresh access token
    path('token_verify/', TokenVerifyView.as_view()),
    path('token_refresh/', get_refresh_view().as_view()),
]
