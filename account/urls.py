from django.urls import path
from .views import LoginView, LogoutView, PasswordResetView, PasswordChangeView, PasswordResetConfirmView
from rest_framework_simplejwt.views import TokenVerifyView
from dj_rest_auth.jwt_auth import get_refresh_view

app_name = 'account'

urlpatterns = [
    # POST : Login with raw email/password
    path('login/', LoginView.as_view()),
    # POST : Logout
    path('logout/', LogoutView.as_view()),
    # POST : Password reset
    path('password_reset/', PasswordResetView.as_view()),
    # POST : Password reset confirmation
    path('password_reset_confirm/<uidb64>/<token>/', PasswordResetConfirmView.as_view()),
    # POST : Password change
    path('password_change/', PasswordChangeView.as_view()),
    # POST : Tokens, Verify if token valid, Refresh access token
    path('token_verify/', TokenVerifyView.as_view()),
    path('token_refresh/', get_refresh_view().as_view()),
]
