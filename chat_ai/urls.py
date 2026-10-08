from django.urls import path
from .views import CapabilitiesView, ConversationsView, ConversationView, MessagesView, FeedbackView, ConfirmActionView, RecordSelectionView

urlpatterns=[
    path('actions/<uuid:id>/confirm/',ConfirmActionView.as_view()),
    path('capabilities/',CapabilitiesView.as_view()),
    path('conversations/',ConversationsView.as_view()),
    path('conversations/<uuid:id>/',ConversationView.as_view()),
    path('conversations/<uuid:id>/selection/',RecordSelectionView.as_view()),
    path('conversations/<uuid:id>/messages/',MessagesView.as_view()),
    path('feedback/',FeedbackView.as_view()),
]
