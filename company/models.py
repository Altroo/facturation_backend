from os import path
from uuid import uuid4

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


def get_company_image_path(_, filename):
    """Store company images in a dedicated folder with a random name."""
    _, ext = path.splitext(filename)
    return path.join("company_images", f"{uuid4()}{ext}")


class Company(models.Model):
    # Basic info
    raison_sociale = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Raison sociale",
        db_index=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        default=None,
        verbose_name="E‑mail",
    )
    logo = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Logo",
        max_length=1000,
    )
    logo_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Logo cropped",
        max_length=1000,
    )

    cachet = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Cachet",
        max_length=1000,
    )

    cachet_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Cachet cropped",
        max_length=1000,
    )

    # Number of employees (choice)
    NBR_EMPLOYE_CHOICES = [
        ("1 à 5", "1 à 5"),
        ("5 à 10", "5 à 10"),
        ("10 à 50", "10 à 50"),
        ("50 à 100", "50 à 100"),
        ("plus que 100", "plus que 100"),
    ]
    nbr_employe = models.CharField(
        max_length=12,
        choices=NBR_EMPLOYE_CHOICES,
        default=1,
        verbose_name="Nombre d'employés",
    )

    # Responsable details
    CIVILITE_CHOICES = [
        ("", ""),
        ("Mme", "Mme"),
        ("Mlle", "Mlle"),
        ("M.", "M."),
    ]
    civilite_responsable = models.CharField(
        max_length=4,
        choices=CIVILITE_CHOICES,
        default="",
        verbose_name="Civilité du responsable",
    )
    nom_responsable = models.CharField(
        max_length=255,
        default=None,
        blank=True,
        null=True,
        verbose_name="Nom du responsable",
    )

    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message="Tapez un numéro de téléphone valide",
    )
    gsm_responsable = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name="GSM du responsable",
    )
    adresse = models.TextField(
        default=None,
        blank=True,
        null=True,
        verbose_name="Adresse",
    )
    telephone = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name="Téléphone",
    )
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name="Fax",
    )
    site_web = models.URLField(
        default="",
        blank=True,
        null=True,
        verbose_name="Site web",
    )

    # Administrative identifiers
    numero_du_compte = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Numéro du compte",
    )
    ICE = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="ICE",
    )
    registre_de_commerce = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Registre de commerce",
    )
    identifiant_fiscal = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Identifiant fiscal",
    )
    tax_professionnelle = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Taxe professionnelle",
    )
    CNSS = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="CNSS",
    )

    # DATES
    date_created = models.DateTimeField(
        verbose_name="Date de création",
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ("-date_created",)

    def __str__(self):
        return self.raison_sociale
