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


class PdfTranslationPending(APIException):
    status_code = 409
    default_detail = "Les traductions du document sont en cours de préparation."
    default_code = "pdf_translation_pending"

    def __init__(self):
        super().__init__({"code": self.default_code, "detail": self.default_detail})
        self.wait = 2


class PdfTranslationFailed(APIException):
    status_code = 503
    default_detail = "La traduction du document est temporairement indisponible. Veuillez réessayer plus tard."
    default_code = "pdf_translation_failed"

    def __init__(self):
        super().__init__({"code": self.default_code, "detail": self.default_detail})


class PdfTranslationEngineUnavailable(APIException):
    status_code = 503
    default_detail = "Le service de traduction est temporairement indisponible."
    default_code = "pdf_translation_engine_unavailable"


class PdfTranslationDeferred(APIException):
    status_code = 409
    default_detail = (
        "La traduction du document est en attente. Veuillez réessayer plus tard."
    )
    default_code = "pdf_translation_deferred"

    def __init__(self, wait):
        import math

        self.wait = max(1, math.ceil(wait))
        super().__init__(
            {
                "code": self.default_code,
                "detail": self.default_detail,
                "retry_after": self.wait,
            }
        )
