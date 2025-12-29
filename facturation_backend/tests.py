import base64
import binascii
from io import BytesIO
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from django.core.files.base import ContentFile
from rest_framework import serializers
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    NotFound,
    MethodNotAllowed,
)
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from .utils import (
    ImageProcessor,
    Base64ImageField,
    api_exception_handler,
    CustomPagination,
)


@pytest.mark.django_db
class TestImageProcessor:
    def test_load_image_from_io(self):
        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="red")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)

        result = ImageProcessor.load_image_from_io(bytes_io)

        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.shape == (100, 100, 3)

    def test_from_img_to_io(self):
        # Create a numpy array representing an image
        image_array = np.zeros((100, 100, 3), dtype=np.uint8)
        image_array[:, :] = [255, 0, 0]  # Red image

        result = ImageProcessor.from_img_to_io(image_array, "PNG")

        assert isinstance(result, BytesIO)
        result.seek(0)
        img = Image.open(result)
        assert img.size == (100, 100)
        assert img.format == "PNG"

    def test_data_url_to_uploaded_file_with_header(self):
        # Create a test image and encode it
        img = Image.new("RGB", (10, 10), color="blue")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)
        encoded = base64.b64encode(bytes_io.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{encoded}"

        result = ImageProcessor.data_url_to_uploaded_file(data_url)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".png")

    def test_data_url_to_uploaded_file_without_header(self):
        # Create a test image and encode it
        img = Image.new("RGB", (10, 10), color="green")
        bytes_io = BytesIO()
        img.save(bytes_io, format="JPEG")
        bytes_io.seek(0)
        encoded = base64.b64encode(bytes_io.read()).decode("utf-8")

        result = ImageProcessor.data_url_to_uploaded_file(encoded)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".jpg")

    def test_data_url_to_uploaded_file_invalid_data(self):
        result = ImageProcessor.data_url_to_uploaded_file("invalid_base64!")
        assert result is None

    def test_data_url_to_uploaded_file_non_string(self):
        result = ImageProcessor.data_url_to_uploaded_file(12345)
        assert result is None

    def test_resize_with_blurred_background_landscape(self):
        # Create a landscape image (wider than tall)
        image = np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)

        result = ImageProcessor.resize_with_blurred_background(image, target_size=300)

        assert result.shape == (300, 300, 3)
        assert isinstance(result, np.ndarray)

    def test_resize_with_blurred_background_portrait(self):
        # Create a portrait image (taller than wide)
        image = np.random.randint(0, 255, (200, 100, 3), dtype=np.uint8)

        result = ImageProcessor.resize_with_blurred_background(image, target_size=300)

        assert result.shape == (300, 300, 3)
        assert isinstance(result, np.ndarray)

    def test_resize_with_blurred_background_square(self):
        # Create a square image
        image = np.random.randint(0, 255, (150, 150, 3), dtype=np.uint8)

        result = ImageProcessor.resize_with_blurred_background(image, target_size=300)

        assert result.shape == (300, 300, 3)
        assert isinstance(result, np.ndarray)


@pytest.mark.django_db
class TestBase64ImageField:
    def test_to_internal_value_with_base64_data_url(self):
        field = Base64ImageField()

        # Create a test image
        img = Image.new("RGB", (10, 10), color="red")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)
        encoded = base64.b64encode(bytes_io.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{encoded}"

        result = field.to_internal_value(data_url)

        assert result is not None
        assert hasattr(result, "name")
        assert result.name.endswith(".png")

    def test_to_internal_value_with_base64_no_header(self):
        field = Base64ImageField()

        # Create a test image
        img = Image.new("RGB", (10, 10), color="blue")
        bytes_io = BytesIO()
        img.save(bytes_io, format="JPEG")
        bytes_io.seek(0)
        encoded = base64.b64encode(bytes_io.read()).decode("utf-8")

        result = field.to_internal_value(encoded)

        assert result is not None
        assert hasattr(result, "name")
        assert result.name.endswith(".jpg")

    def test_to_internal_value_with_invalid_base64(self):
        field = Base64ImageField()

        with pytest.raises(binascii.Error):
            field.to_internal_value("invalid_base64_string!!!")

    def test_to_internal_value_with_file_object(self):
        field = Base64ImageField()

        # Create a mock file object
        img = Image.new("RGB", (10, 10), color="yellow")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)

        # ContentFile should be handled by parent class
        content_file = ContentFile(bytes_io.read(), name="test.png")

        # This should be handled by the parent ImageField
        with patch.object(
            serializers.ImageField, "to_internal_value", return_value=content_file
        ):
            result = field.to_internal_value(content_file)
            assert result == content_file

    def test_get_file_extension_png(self):
        img = Image.new("RGB", (10, 10), color="red")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)
        decoded = bytes_io.read()

        extension = Base64ImageField.get_file_extension("test", decoded)

        assert extension == "png"

    def test_get_file_extension_jpeg(self):
        img = Image.new("RGB", (10, 10), color="blue")
        bytes_io = BytesIO()
        img.save(bytes_io, format="JPEG")
        bytes_io.seek(0)
        decoded = bytes_io.read()

        extension = Base64ImageField.get_file_extension("test", decoded)

        assert extension == "jpg"

    def test_get_file_extension_invalid_image(self):
        decoded = b"not_an_image"

        extension = Base64ImageField.get_file_extension("test", decoded)

        assert extension == "jpg"  # Default fallback


class TestApiExceptionHandler:
    def test_api_exception_handler_wraps_response(self):
        factory = APIRequestFactory()
        req = factory.get("/")
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
        context = {"request": Request(req)}

        from rest_framework.exceptions import NotFound

        exc = NotFound()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 404
        assert resp.data["status_code"] == 404
        assert "message" in resp.data

    def test_api_exception_handler_401(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        context = {"request": Request(req)}

        from rest_framework.exceptions import AuthenticationFailed

        exc = AuthenticationFailed()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 401
        assert resp.data["status_code"] == 401

    def test_api_exception_handler_403(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        context = {"request": Request(req)}

        from rest_framework.exceptions import PermissionDenied

        exc = PermissionDenied()
        resp = api_exception_handler(exc, context)

        assert resp is not None
        assert resp.status_code == 403
        assert resp.data["status_code"] == 403

    def test_api_exception_handler_500(self):
        factory = APIRequestFactory()
        req = factory.get("/")
        context = {"request": Request(req)}

        from rest_framework.exceptions import APIException

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


class TestCustomPagination:
    def test_custom_pagination_defaults(self):
        p = CustomPagination()
        assert p.page_size == 10
        assert p.page_size_query_param == "page_size"
        assert p.max_page_size == 100

    def test_custom_pagination_page_size_query_param(self):
        p = CustomPagination()

        # Verify the query param name is correct
        assert p.page_size_query_param == "page_size"

        # This allows clients to request different page sizes via ?page_size=20

    def test_custom_pagination_max_page_size_limit(self):
        p = CustomPagination()

        # Verify max_page_size prevents abuse
        assert p.max_page_size == 100

        # This means even if client requests ?page_size=1000, it will be capped at 100


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
