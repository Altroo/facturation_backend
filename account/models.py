from io import BytesIO
from os import path
from uuid import uuid4

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from facturation_backend.settings import API_URL
from .managers import CustomUserManager


class Role(models.Model):
    """Custom role model to extend Django's Group with additional fields."""

    name = models.CharField(max_length=150, unique=True, verbose_name="Role Name")
    is_admin = models.BooleanField(
        default=False,
        verbose_name="Is Admin",
        help_text="Designates whether users with this role can manage companies and users.",
    )

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ("-is_admin", "name")

    def __str__(self):
        return self.name


def get_avatar_path(_, filename):
    _, ext = path.splitext(filename)
    return path.join("user_avatars/", str(uuid4()) + ext)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Password (hidden)
    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(_("first name"), max_length=30, blank=True)
    last_name = models.CharField(_("last name"), max_length=30, blank=True)
    GENDER_CHOICES = (("", "Unset"), ("H", "Homme"), ("F", "Femme"))
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        default="",
    )
    avatar = models.ImageField(
        verbose_name="User Avatar",
        upload_to=get_avatar_path,
        blank=True,
        null=True,
        default=None,
    )
    avatar_cropped = models.ImageField(
        upload_to=get_avatar_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Avatar cropped",
        max_length=1000,
    )
    # permissions
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
        db_index=True,
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
        db_index=True,
    )
    # DATES
    date_joined = models.DateTimeField(
        _("date joined"), default=timezone.now, db_index=True
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        db_index=True,
    )
    # Codes
    password_reset_code = models.CharField(
        verbose_name="Password Reset Code",
        blank=True,
        null=True,
        db_index=True,
    )
    # Task ids for Codes
    task_id_password_reset = models.CharField(
        verbose_name="Task ID password reset",
        max_length=40,
        default=None,
        null=True,
        blank=True,
        db_index=True,
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()
    history = HistoricalRecords()

    def __str__(self):
        full_name = "{} {}".format(self.first_name, self.last_name).strip()
        return full_name if full_name else self.email

    @property
    def get_absolute_avatar_img(self):
        if self.avatar:
            return f"{API_URL}{self.avatar.url}"
        return None

    @property
    def get_absolute_avatar_cropped_img(self):
        if self.avatar_cropped:
            return f"{API_URL}{self.avatar_cropped.url}"
        return None

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ("-date_joined",)

    def save_image(self, file_name, image):
        if not isinstance(image, BytesIO):
            return
        getattr(self, file_name).save(
            f"{str(uuid4())}.webp", ContentFile(image.getvalue()), save=True
        )


class Membership(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
        verbose_name="Company",
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="User",
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"
        ordering = ("role",)
        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["company", "role"]),
        ]

    def __str__(self):
        return f"{self.user.email} – {self.role} @ {self.company or 'No Company'}"
