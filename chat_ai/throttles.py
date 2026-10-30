from rest_framework.throttling import UserRateThrottle


class ChatReadThrottle(UserRateThrottle):
    scope = "chat_ai_read"
    rate = "120/minute"


class ChatMutationThrottle(UserRateThrottle):
    scope = "chat_ai_mutation"
    rate = "60/minute"


class ChatInferenceThrottle(UserRateThrottle):
    scope = "chat_ai_inference"
    rate = "12/minute"


class ChatConfirmationThrottle(UserRateThrottle):
    scope = "chat_ai_confirmation"
    rate = "20/minute"
