from rest_framework.views import exception_handler
from http import HTTPStatus
from rest_framework.response import Response


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        http_code_to_message = {v.value: v.description for v in HTTPStatus}
        error_payload = {
            "status_code": response.status_code,
            "message": http_code_to_message.get(response.status_code, ""),
            "details": response.data,
        }
        # Preserve the HTTP status code!
        return Response(error_payload, status=response.status_code)

    return response
