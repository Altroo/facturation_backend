from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from core.exceptions import api_exception_handler


class TestApiExceptionHandler:
    def test_api_exception_handler_wraps_response(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        # DRF Request accepts an HttpRequest; its dynamic signature confuses PyCharm.
        # noinspection PyArgumentList
        context = {"request": Request(req)}
        exc = ValidationError({"field": "error"})
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 400
        assert isinstance(resp.data, dict)
        assert resp.data["status_code"] == 400
        assert "details" in resp.data

        # Normalize ErrorDetail objects (or strings) to lists of strings for stable assertion
        details = resp.data["details"]
        # ErrorDetail objects behave like strings, so we need to handle them properly
        normalized = {}
        for k, v in details.items():
            if isinstance(v, list):
                normalized[k] = [str(item) for item in v]
            else:
                normalized[k] = [str(v)]
        assert normalized == {"field": ["error"]}

    def test_api_exception_handler_404(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        # noinspection PyArgumentList
        context = {"request": Request(req)}

        exc = NotFound()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 404
        assert resp.data["status_code"] == 404
        assert "message" in resp.data

    def test_api_exception_handler_401(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        # noinspection PyArgumentList
        context = {"request": Request(req)}

        exc = AuthenticationFailed()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 401
        assert resp.data["status_code"] == 401

    def test_api_exception_handler_403(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        # noinspection PyArgumentList
        context = {"request": Request(req)}

        exc = PermissionDenied()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 403
        assert resp.data["status_code"] == 403

    def test_api_exception_handler_500(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        # noinspection PyArgumentList
        context = {"request": Request(req)}

        exc = APIException()
        exc.status_code = 500
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 500
        assert resp.data["status_code"] == 500

    def test_api_exception_handler_none_response(self):
        # When exception_handler returns None, api_exception_handler should also return None
        context = {}

        # Use an exception that won't be handled by DRF's exception_handler
        exc = ValueError("Not a DRF exception")
        resp = api_exception_handler(exc, context)

        assert resp is None


class TestApiExceptionHandlerExtra:
    """Extra tests for api_exception_handler function."""

    def test_401_error(self):
        """Test handling 401 error."""
        factory = APIRequestFactory()
        request = factory.get("/")
        exc = AuthenticationFailed("Invalid")
        response = api_exception_handler(exc, {"request": request, "view": None})
        assert response.status_code == 401

    def test_403_error(self):
        """Test handling 403 error."""
        factory = APIRequestFactory()
        request = factory.get("/")
        exc = PermissionDenied("Denied")
        response = api_exception_handler(exc, {"request": request, "view": None})
        assert response.status_code == 403

    def test_404_error(self):
        """Test handling 404 error."""
        factory = APIRequestFactory()
        request = factory.get("/")
        exc = NotFound("Not found")
        response = api_exception_handler(exc, {"request": request, "view": None})
        assert response.status_code == 404

    def test_405_error(self):
        """Test handling 405 error."""
        factory = APIRequestFactory()
        request = factory.get("/")
        exc = MethodNotAllowed("GET")
        response = api_exception_handler(exc, {"request": request, "view": None})
        assert response.status_code == 405
