import base64
import binascii
from io import BytesIO
from unittest.mock import patch

import numpy as np
import pytest
from django.core.files.base import ContentFile
from PIL import Image
from rest_framework import serializers

from core.images import Base64ImageField, ImageProcessor


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

    def test_convert_to_webp(self):
        # Create a test image in PNG format
        img = Image.new("RGB", (100, 100), color="blue")
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)
        png_data = bytes_io.read()

        result = ImageProcessor.convert_to_webp(png_data)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

        # Verify the result is actually a WebP image
        result.seek(0)
        converted_img = Image.open(result)
        assert converted_img.format == "WEBP"
        assert converted_img.size == (100, 100)

    def test_convert_to_webp_with_transparency(self):
        # Create a test image with transparency (RGBA)
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)
        png_data = bytes_io.read()

        result = ImageProcessor.convert_to_webp(png_data)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

    def test_convert_to_webp_bytesio_input(self):
        """Test convert_to_webp with BytesIO object as input."""
        img = Image.new("RGB", (50, 50), color="green")
        bytes_io = BytesIO()
        img.save(bytes_io, format="JPEG")
        bytes_io.seek(0)

        result = ImageProcessor.convert_to_webp(bytes_io)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")
        result.seek(0)
        converted_img = Image.open(result)
        assert converted_img.format == "WEBP"

    def test_convert_to_webp_mode_la(self):
        """Test convert_to_webp with LA mode image (luminance with alpha)."""
        img = Image.new("LA", (50, 50), color=(128, 200))
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)

        result = ImageProcessor.convert_to_webp(bytes_io)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

    def test_convert_to_webp_mode_p(self):
        """Test convert_to_webp with P mode image (palette mode)."""
        img = Image.new("P", (50, 50))
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)

        result = ImageProcessor.convert_to_webp(bytes_io)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

    def test_convert_to_webp_mode_l(self):
        """Test convert_to_webp with L mode image (grayscale)."""
        img = Image.new("L", (50, 50), color=128)
        bytes_io = BytesIO()
        img.save(bytes_io, format="PNG")
        bytes_io.seek(0)

        result = ImageProcessor.convert_to_webp(bytes_io)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

    def test_convert_to_webp_mode_cmyk(self):
        """Test convert_to_webp with CMYK mode image (converts to RGB)."""
        img = Image.new("CMYK", (50, 50), color=(100, 50, 0, 0))
        bytes_io = BytesIO()
        img.save(bytes_io, format="JPEG")
        bytes_io.seek(0)

        result = ImageProcessor.convert_to_webp(bytes_io)

        assert result is not None
        assert isinstance(result, ContentFile)
        assert result.name.endswith(".webp")

    def test_convert_to_webp_invalid_data(self):
        """Test convert_to_webp with invalid data raises ValueError."""
        invalid_data = b"not_an_image_at_all"

        with pytest.raises(ValueError) as exc_info:
            ImageProcessor.convert_to_webp(invalid_data)

        assert "Unrecognized image format" in str(exc_info.value)

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
    # Base64ImageField intentionally extends ImageField to accept strings.
    # noinspection PyTypeChecker
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

    # noinspection PyTypeChecker
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

    # noinspection PyTypeChecker
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
        # noinspection PyUnresolvedReferences
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
