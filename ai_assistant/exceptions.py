from rest_framework.exceptions import APIException


class AssistantDisabled(APIException):
    status_code = 503
    default_detail = "L'assistant IA n'est pas disponible."
    default_code = "ai_assistant_disabled"


class ModelUnavailable(APIException):
    status_code = 503
    default_detail = "Le modèle IA est temporairement indisponible."
    default_code = "ai_model_unavailable"


class ModelTimeout(APIException):
    status_code = 504
    default_detail = "Le modèle IA a dépassé le délai de réponse."
    default_code = "ai_model_timeout"


class InvalidModelResponse(APIException):
    status_code = 502
    default_detail = "La réponse du modèle IA n'a pas pu être validée."
    default_code = "ai_invalid_response"
