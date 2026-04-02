from io import BytesIO
from os import path
from uuid import uuid4

from django.contrib.auth.models import AbstractBaseUser
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import PermissionsMixin
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from facturation_backend.settings import API_URL
from .managers import CustomUserManager


class Role(models.Model):
    """Custom role model to extend Django's Group with additional fields."""

    name = models.CharField(max_length=150, unique=True, verbose_name=_("Nom rôle"))
    name.help_text = _("Nom unique du rôle")

    class Meta:
        verbose_name = _("Rôle")
        verbose_name_plural = _("Rôles")
        ordering = ("name",)

    def __str__(self):
        return self.name


def get_avatar_path(_, filename):
    _, ext = path.splitext(filename)
    return path.join("user_avatars/", str(uuid4()) + ext)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Password (hidden)
    email = models.EmailField(
        _("Adresse e‑mail"), unique=True, help_text=_("Adresse e‑mail de l'utilisateur")
    )
    first_name = models.CharField(
        _("Prénom"), max_length=30, blank=True, help_text=_("Prénom de l'utilisateur")
    )
    last_name = models.CharField(
        _("Nom"), max_length=30, blank=True, help_text=_("Nom de famille de l'utilisateur")
    )
    GENDER_CHOICES = (("", _("Unset")), ("H", _("Homme")), ("F", _("Femme")))
    gender = models.CharField(
        verbose_name=_("Sexe"),
        max_length=1,
        choices=GENDER_CHOICES,
        default="",
        help_text=_("Sexe de l'utilisateur"),
    )
    avatar = models.ImageField(
        verbose_name=_("Photo de profil"),
        upload_to=get_avatar_path,
        blank=True,
        null=True,
        default=None,
        help_text=_("Image de profil de l'utilisateur (format recommandé: WebP)"),
    )
    avatar_cropped = models.ImageField(
        upload_to=get_avatar_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Photo de profil recadrée"),
        max_length=1000,
        help_text=_("Version recadrée de la photo de profil"),
    )
    # permissions
    is_staff = models.BooleanField(
        _("Statut personnel"),
        default=False,
        help_text=_("Indique si l'utilisateur peut se connecter au panneau d'administration."),
        db_index=True,
    )
    is_active = models.BooleanField(
        _("Actif"),
        default=True,
        help_text=_("Indique si ce compte doit être considéré comme actif."),
        db_index=True,
    )
    # DATES
    date_joined = models.DateTimeField(
        _("Date d'inscription"),
        default=timezone.now,
        help_text=_("Horodatage de l'inscription de l'utilisateur"),
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification"),
        help_text=_("Horodatage de la dernière modification du compte"),
        db_index=True,
    )
    # Codes
    password_reset_code = models.CharField(
        verbose_name=_("Mot de passe - Code de réinitialisation"),
        help_text=_("Code envoyé pour la réinitialisation du mot de passe"),
        blank=True,
        null=True,
        db_index=True,
    )
    password_reset_code_created_at = models.DateTimeField(
        verbose_name=_("Mot de passe - Date de création du code"),
        help_text=_("Date et heure de création du code de réinitialisation (expire après 5 minutes)"),
        blank=True,
        null=True,
        db_index=True,
    )
    # Task ids for Codes
    task_id_password_reset = models.CharField(
        verbose_name=_("Mot de passe - Task ID de réinitialisation"),
        max_length=40,
        default=None,
        null=True,
        blank=True,
        help_text=_("Identifiant de la tâche de réinitialisation du mot de passe"),
        db_index=True,
    )
    # Password tracking
    default_password_set = models.BooleanField(
        verbose_name=_("Mot de passe par défaut défini"),
        default=False,
        help_text=_("Indique si l'utilisateur utilise encore le mot de passe par défaut envoyé par e-mail"),
        db_index=True,
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()
    history = HistoricalRecords(
        verbose_name=_("Historique Utilisateur"),
        verbose_name_plural=_("Historiques Utilisateurs"),
    )

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
        verbose_name = _("Utilisateur")
        verbose_name_plural = _("Utilisateurs")
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
        verbose_name=_("Société"),
        help_text=_("Société à laquelle l'utilisateur est rattaché"),
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Utilisateur"),
        help_text=_("Utilisateur membre"),
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text=_("Rôle assigné à l'utilisateur dans l'entreprise"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Membre"), verbose_name_plural=_("Historiques Membres")
    )

    class Meta:
        verbose_name = _("Membre")
        verbose_name_plural = _("Membres")
        ordering = ("role",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"], name="unique_user_company_membership"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["company", "role"]),
        ]

    def __str__(self):
        return f"{self.user.email} – {self.role} @ {self.company or 'No Company'}"
