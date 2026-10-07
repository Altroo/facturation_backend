from django.urls import path
from .views import AssistView

app_name = "ai_assistant"
urlpatterns = [path("assist/", AssistView.as_view(), name="assist")]
