from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.files.base import ContentFile
from .managers import CustomUserManager
from facturation_backend.settings import API_URL
from os import path
from io import BytesIO
from uuid import uuid4


def get_avatar_path(instance, filename):
    filename, file_extension = path.splitext(filename)
    return path.join('user_avatars/', str(uuid4()) + file_extension)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Password (hidden)
    email = models.EmailField(_('email address'), unique=True)
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    GENDER_CHOICES = (
        ('', 'Unset'),
        ('H', 'Homme'),
        ('F', 'Femme')
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='', blank=True, null=True)
    avatar = models.ImageField(verbose_name='User Avatar', upload_to=get_avatar_path, blank=True, null=True,
                               default=None)
    avatar_thumbnail = models.ImageField(verbose_name='User Avatar thumbnail', upload_to=get_avatar_path, blank=True, null=True,
                                         default=None)
    # permissions
    is_staff = models.BooleanField(_('staff status'),
                                   default=False,
                                   help_text=_('Designates whether the user can log into this admin site.'), )
    is_active = models.BooleanField(_('active'),
                                    default=True,
                                    help_text=_(
                                        'Designates whether this user should be treated as active. '
                                        'Unselect this instead of deleting accounts.'
                                    ), )
    # DATES
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    # Codes
    password_reset_code = models.IntegerField(verbose_name='Password Reset Code', blank=True, null=True)
    # Task ids for Codes
    task_id_password_reset = models.CharField(verbose_name='Task ID password reset',
                                              max_length=40, default=None, null=True, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return '{}'.format(self.email)

    @property
    def get_absolute_avatar_img(self):
        if self.avatar:
            return f"{API_URL}{self.avatar.url}"
        return None

    @property
    def get_absolute_avatar_thumbnail(self):
        if self.avatar_thumbnail:
            return f"{API_URL}{self.avatar_thumbnail.url}"
        return None

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ('date_joined',)

    def save_image(self, file_name, image):
        if not isinstance(image, BytesIO):
            return
        getattr(self, file_name).save(f'{str(uuid4())}.webp', ContentFile(image.getvalue()), save=True)
