from rest_framework.views import exception_handler
from http import HTTPStatus
from rest_framework.views import Response


def api_exception_handler(exc, context) -> Response:
    """Custom API exception handler."""

    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    if response is not None:
        # Using the description's of the HTTPStatus class as error message.
        http_code_to_message = {v.value: v.description for v in HTTPStatus}
        error_payload = [
            {
                "status_code": response.status_code,
                "message": http_code_to_message[response.status_code],
                "details": response.data,
            }
        ]
        response.data = error_payload
    return response
