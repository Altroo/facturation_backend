from typing import Tuple

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from facturation_backend.celery_conf import app
from celery.utils.log import get_task_logger
from PIL import Image, ImageDraw, ImageFont
from account.models import CustomUser
from facturation_backend.settings import STATIC_PATH
from io import BytesIO
from random import shuffle
from django.core.files import File
from django.core.mail import EmailMessage

from facturation_backend.utils import ImageProcessor

logger = get_task_logger(__name__)


@app.task(bind=True, serializer='json')
def send_email(self, user_pk, email_, mail_subject, message, code=None, type_=None):
    user = CustomUser.objects.get(pk=user_pk)
    email = EmailMessage(
        mail_subject, message, to=(email_,)
    )
    email.content_subtype = "html"
    email.send(fail_silently=False)
    if type_ == 'password_reset_code' and code is not None:
        user.password_reset_code = code
        user.save(update_fields=['password_reset_code'])


@app.task(bind=True, serializer='json')
def start_deleting_expired_codes(self, user_pk, type_):
    user = CustomUser.objects.get(pk=user_pk)
    if type_ == 'password_reset':
        user.password_reset_code = None
        user.save(update_fields=['password_reset_code'])


# For generating Avatar
def random_color_picker():
    return [
        "#F3DCDC",
        "#FFD9A2",
        "#F8F2DA",
        "#DBF4EA",
        "#DBE8F4",
        "#D5CEEE",
        "#F3D8E1",
        "#EBD2AD",
        "#E2E4E2",
        "#FFA826",
        "#FED301",
        "#07CBAD",
        "#FF9DBF",
        "#CEB186",
        "#FF5D6B",
        "#0274D7",
        "#8669FB",
        "#878E88",
        "#0D070B"
    ]


def get_text_fill_color(bg_color):
    # white 255, 255, 255
    # black 0, 0, 0
    match bg_color:
        case ("#F3DCDC" | "#FFD9A2" | "#F8F2DA" | "#DBF4EA" | "#DBE8F4" | "#D5CEEE" | "#F3D8E1" | "#EBD2AD"
              | "#E2E4E2" | "#FFA826" | "#FED301" | "#07CBAD" | "#FF9DBF" | "#CEB186"):
            return 0, 0, 0
        case ("#FF5D6B" | "#0274D7" | "#8669FB" | "#878E88" | "#0D070B"):
            return 255, 255, 255
        case _:
            # Return black color as default
            return 0, 0, 0


def from_img_to_io(image, format_):
    bytes_io = BytesIO()
    image.save(File(bytes_io), format=format_, save=True)
    bytes_io.seek(0)
    return bytes_io


def generate_avatar_and_thumbnail(last_name, first_name):
    colors = random_color_picker()
    shuffle(colors)
    color = colors.pop()
    fill = get_text_fill_color(color)
    avatar = Image.new("RGB", (600, 600), color=color)
    font_avatar = ImageFont.truetype(STATIC_PATH + "/fonts/Poppins-Bold.ttf", 240)
    drawn_avatar = ImageDraw.Draw(avatar)
    drawn_avatar.text((100, 136), "{}.{}".format(first_name, last_name), font=font_avatar, fill=fill)
    thumbnail = Image.new("RGB", (300, 300), color=color)
    font_thumb = ImageFont.truetype(STATIC_PATH + "/fonts/Poppins-Bold.ttf", 120)
    drawn_thumb = ImageDraw.Draw(thumbnail)
    drawn_thumb.text((50, 68), "{}.{}".format(first_name, last_name), font=font_thumb, fill=fill)
    return avatar, thumbnail


@app.task(bind=True, serializer='json')
def generate_user_thumbnail(self, user_pk):
    user = CustomUser.objects.get(pk=user_pk)
    last_name = str(user.last_name[0]).upper()
    first_name = str(user.first_name[0]).upper()
    avatar, thumbnail = generate_avatar_and_thumbnail(last_name, first_name)
    avatar_ = from_img_to_io(avatar, 'WEBP')
    thumbnail_ = from_img_to_io(thumbnail, 'WEBP')
    user.save_image('avatar', avatar_)
    user.save_image('avatar_thumbnail', thumbnail_)


def resize_images_v2(bytes_) -> Tuple[BytesIO, BytesIO]:
    image_processor = ImageProcessor()
    loaded_img = image_processor.load_image_from_io(bytes_)

    # Avatar 600x600 with blurred background
    avatar_img = image_processor.resize_with_blurred_background(loaded_img, 600)
    avatar_io = image_processor.from_img_to_io(avatar_img, 'WEBP')

    # Thumbnail 300x300 with blurred background
    thumb_img = image_processor.resize_with_blurred_background(loaded_img, 300)
    thumb_io = image_processor.from_img_to_io(thumb_img, 'WEBP')

    return avatar_io, thumb_io


def generate_images_v2(query_, avatar: BytesIO, thumbnail: BytesIO):
    query_.save_image("avatar", avatar)
    query_.save_image("avatar_thumbnail", thumbnail)


@app.task(bind=True, serializer='pickle')
def resize_avatar_thumbnail(self, object_pk: int, avatar: BytesIO | None):
    object_ = CustomUser.objects.get(pk=object_pk)
    if isinstance(avatar, BytesIO):
        avatar_io, thumb_io = resize_images_v2(avatar)
        generate_images_v2(object_, avatar_io, thumb_io)
        event = {
            "type": "recieve_group_message",
            "message": {
                "type": "USER_AVATAR",
                "pk": object_.pk,
                "avatar": object_.get_absolute_avatar_img,
            }
        }
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)("%s" % object_.pk, event)
