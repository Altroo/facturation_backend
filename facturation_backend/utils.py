import binascii
from base64 import b64decode
from http import HTTPStatus
from io import BytesIO
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from cv2 import imdecode, resize, INTER_AREA, cvtColor, COLOR_BGR2RGB, GaussianBlur
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from numpy import uint8, frombuffer
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import exception_handler
from six import string_types


class ImageProcessor:
    @staticmethod
    def load_image_from_io(bytes_: BytesIO):
        return cvtColor(imdecode(frombuffer(bytes_.read(), uint8), 1), COLOR_BGR2RGB)

    @staticmethod
    def from_img_to_io(image, format_):
        image = Image.fromarray(image)
        bytes_io = BytesIO()
        image.save(bytes_io, format=format_)
        bytes_io.seek(0)
        return bytes_io

    @staticmethod
    def data_url_to_uploaded_file(data):
        if isinstance(data, string_types):
            # Check if the base64 string is in the "data:" format
            if "data:" in data and ";base64," in data:
                # Break out the header from the base64 content
                header, data = data.split(";base64,")
            # Try to decode the file. Return validation error if it fails.
            try:
                decoded_file = b64decode(data)
                # Generate file name:
                file_name = str(uuid4())
                # Get the file name extension:
                file_extension = Base64ImageField.get_file_extension(
                    file_name, decoded_file
                )
                complete_file_name = f"{file_name}.{file_extension}"
                return ContentFile(decoded_file, name=complete_file_name)
            except (
                binascii.Error,
                ValueError,
                TypeError,
                UnidentifiedImageError,
                OSError,
            ):
                return None
        return None

    @staticmethod
    def resize_with_blurred_background(image, target_size=600):
        """
        Resize image proportionally and place it on a blurred background.
        """
        h, w = image.shape[:2]
        scale = target_size / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)

        # Resize proportionally
        resized = resize(image, (new_w, new_h), interpolation=INTER_AREA)

        # Create blurred background from original
        background = resize(image, (target_size, target_size))
        background = GaussianBlur(background, (51, 51), 0)

        # Overlay resized image in the center
        x_offset = (target_size - new_w) // 2
        y_offset = (target_size - new_h) // 2
        background[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

        return background


class Base64ImageField(serializers.ImageField):
    def to_internal_value(self, data):
        # Check if this is a base64 string
        decoded_file = None
        if isinstance(data, string_types):
            # Check if the base64 string is in the "data:" format
            if "data:" in data and ";base64," in data:
                # Break out the header from the base64 content
                header, data = data.split(";base64,")
            # Try to decode the file. Return validation error if it fails.
            try:
                decoded_file = b64decode(data)
            except TypeError:
                self.fail("invalid_image")

            # Generate file name:
            file_name = str(uuid4())
            # Get the file name extension:
            file_extension = self.get_file_extension(file_name, decoded_file)
            complete_file_name = f"{file_name}.{file_extension}"
            data = ContentFile(decoded_file, name=complete_file_name)

        return super(Base64ImageField, self).to_internal_value(data)

    @staticmethod
    def get_file_extension(_, decoded_file):
        try:
            image = Image.open(BytesIO(decoded_file))
            extension = image.format.lower()
            return "jpg" if extension == "jpeg" else extension
        except UnidentifiedImageError:
            return "jpg"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # French translations for HTTP status descriptions
        http_code_to_message = {
            400: _("Requête invalide"),
            401: _("Non autorisé"),
            403: _("Accès refusé"),
            404: _("Aucune correspondance avec l’URI donnée"),
            405: _("Méthode non autorisée"),
            500: _("Erreur interne du serveur"),
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


class CustomPagination(PageNumberPagination):
    # default size when the client does not specify one
    page_size = 10
    # allow the client to set the size with the `page_size` query param
    page_size_query_param = "page_size"
    # optional maximum to prevent abuse
    max_page_size = 100
