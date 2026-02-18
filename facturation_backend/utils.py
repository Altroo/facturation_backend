import binascii
from base64 import b64decode
from http import HTTPStatus
from io import BytesIO
from typing import Any
from uuid import uuid4

import cv2
from PIL import Image, UnidentifiedImageError

imdecode: Any = cv2.imdecode
resize: Any = cv2.resize
INTER_AREA: Any = cv2.INTER_AREA
cvtColor: Any = cv2.cvtColor
COLOR_BGR2RGB: Any = cv2.COLOR_BGR2RGB
GaussianBlur: Any = cv2.GaussianBlur

from django.core.files.base import ContentFile
from numpy import uint8, frombuffer
from rest_framework import serializers
from rest_framework.exceptions import Throttled
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import exception_handler



class ImageProcessor:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

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
    def convert_to_webp(image_data) -> ContentFile:
        """
        Convert image data to WebP format and return as ContentFile.
        Args:
            image_data: bytes or BytesIO object containing image data
        """
        try:
            # Check file size first
            if isinstance(image_data, BytesIO):
                image_data.seek(0, 2)  # Seek to end
                size = image_data.tell()
                image_data.seek(0)  # Reset to start
            else:
                size = len(image_data)

            if size > ImageProcessor.MAX_FILE_SIZE:
                raise ValueError(
                    f"File size {size} bytes exceeds maximum {ImageProcessor.MAX_FILE_SIZE} bytes"
                )

            # Handle both bytes and BytesIO objects
            if isinstance(image_data, BytesIO):
                image_data.seek(0)
                try:
                    image = Image.open(image_data)
                except UnidentifiedImageError:
                    raise ValueError(
                        "Unrecognized image format. Please upload a valid image file (PNG, JPG, GIF)."
                    )
                except Exception as e:
                    raise ValueError(f"Failed to read image: {str(e)}")
            else:
                try:
                    image = Image.open(BytesIO(image_data))
                except UnidentifiedImageError:
                    raise ValueError(
                        "Unrecognized image format. Please upload a valid image file (PNG, JPG, GIF)."
                    )
                except Exception as e:
                    raise ValueError(f"Failed to read image: {str(e)}")

            # Validate image dimensions
            width, height = image.size
            if width < 10 or height < 10:
                raise ValueError(
                    f"Image too small: {width}x{height}. Minimum is 10x10 pixels."
                )
            if width > 10000 or height > 10000:
                raise ValueError(
                    f"Image too large: {width}x{height}. Maximum is 10000x10000 pixels."
                )

            # Convert to RGB if necessary (WebP doesn't support some modes)
            if image.mode in ("RGBA", "LA", "P"):
                # Keep transparency for RGBA
                if image.mode == "RGBA":
                    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
                    background.paste(
                        image,
                        mask=image.split()[-1] if len(image.split()) > 3 else None,
                    )
                    image = background
                else:
                    image = image.convert("RGB")
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            # Save as WebP
            output = BytesIO()
            image.save(output, format="WEBP", quality=85)
            output.seek(0)

            # Check output size
            if output.getbuffer().nbytes > ImageProcessor.MAX_FILE_SIZE:
                # Try with lower quality
                output = BytesIO()
                image.save(output, format="WEBP", quality=60)
                output.seek(0)

                if output.getbuffer().nbytes > ImageProcessor.MAX_FILE_SIZE:
                    raise ValueError(
                        f"Image too large even after compression: {output.getbuffer().nbytes} bytes. "
                        f"Please upload a smaller image."
                    )

            # Create a unique filename with .webp extension
            filename = f"{uuid4()}.webp"
            return ContentFile(output.read(), name=filename)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(
                f"Image processing failed: {str(e)}. Please ensure the file is a valid image."
            )

    @staticmethod
    def data_url_to_uploaded_file(data):
        if isinstance(data, str):
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
        if isinstance(data, str):
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
    # Translate DRF throttle message to French before handling
    if isinstance(exc, Throttled):
        wait = int(exc.wait) if exc.wait else 0
        exc.detail = f"Requête ralentie. Réessayez dans {wait} seconde{'s' if wait != 1 else ''}."

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


class CustomPagination(PageNumberPagination):
    # default size when the client does not specify one
    page_size = 10
    # allow the client to set the size with the `page_size` query param
    page_size_query_param = "page_size"
    # optional maximum to prevent abuse
    max_page_size = 100
