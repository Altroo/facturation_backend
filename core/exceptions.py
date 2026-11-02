from http import HTTPStatus

from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    # Handle ProtectedError (on_delete=PROTECT) with a clear French message
    if isinstance(exc, ProtectedError):
        protected_message = getattr(
            context.get("view"),
            "protected_delete_message",
            "Cet élément ne peut pas être supprimé car il est utilisé "
            "dans d'autres documents. Utilisez l'archivage à la place.",
        )
        error_payload = {
            "status_code": 409,
            "message": "Suppression impossible",
            "details": {"protected": [protected_message]},
        }
        return Response(error_payload, status=status.HTTP_409_CONFLICT)

    # Translate DRF throttle message to French before handling
    if isinstance(exc, Throttled):
        raw_wait = getattr(exc, "wait", None)
        wait = int(str(raw_wait)) if raw_wait else 0
        message = (
            f"Requête ralentie. Réessayez dans {wait} "
            f"seconde{'s' if wait != 1 else ''}."
        )
        exc.detail = ErrorDetail(message, code="throttled")

    response = exception_handler(exc, context)

    if response is not None:
        # French translations for HTTP status descriptions
        http_code_to_message = {
            400: "Requête invalide",
            401: "Non autorisé",
            403: "Accès refusé",
            404: "Aucune correspondance avec l’URI donnée",
            405: "Méthode non autorisée",
            429: "Trop de requêtes",
            500: "Erreur interne du serveur",
            # fallback to English for others
            **{
                v.value: v.description
                for v in HTTPStatus
                if v.value not in [400, 401, 403, 404, 405, 500]
            },
        }

        error_payload = {
            "status_code": response.status_code,
            "message": http_code_to_message.get(response.status_code, ""),
            "details": response.data,
        }
        return Response(error_payload, status=response.status_code)

    return response
