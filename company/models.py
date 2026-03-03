from os import path
from uuid import uuid4

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


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
        help_text="Raison sociale de l'entreprise",
        db_index=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        default=None,
        verbose_name="E‑mail",
        help_text="Adresse e‑mail de contact de l'entreprise",
    )
    logo = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Logo",
        help_text="Logo de l'entreprise (image)",
        max_length=1000,
    )
    logo_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Logo recadré",
        help_text="Version recadrée du logo",
        max_length=1000,
    )

    cachet = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Cachet",
        help_text="Image du cachet de l'entreprise",
        max_length=1000,
    )

    cachet_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name="Cachet recadré",
        help_text="Version recadrée du cachet",
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
        help_text="Tranche du nombre d'employés",
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
        help_text="Civilité du responsable (Mme, M., ...)",
    )
    nom_responsable = models.CharField(
        max_length=255,
        default=None,
        blank=True,
        null=True,
        verbose_name="Nom du responsable",
        help_text="Nom complet du responsable",
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
        help_text="Numéro mobile du responsable (format international recommandé)",
    )
    adresse = models.TextField(
        default=None,
        blank=True,
        null=True,
        verbose_name="Adresse",
        help_text="Adresse postale complète de l'entreprise",
    )
    telephone = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name="Téléphone",
        help_text="Numéro de téléphone principal",
    )
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name="Fax",
        help_text="Numéro de fax (optionnel)",
    )
    site_web = models.URLField(
        default="",
        blank=True,
        null=True,
        verbose_name="Site web",
        help_text="URL du site web de l'entreprise",
    )

    # Administrative identifiers
    numero_du_compte = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Numéro du compte",
        help_text="Numéro de compte bancaire ou interne",
    )
    ICE = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="ICE",
        help_text="Identifiant Commun de l'Entreprise (ICE)",
    )
    registre_de_commerce = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Registre de commerce",
        help_text="Numéro du registre de commerce",
    )
    identifiant_fiscal = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Identifiant fiscal",
        help_text="Identifiant fiscal de l'entreprise",
    )
    tax_professionnelle = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="Taxe professionnelle",
        help_text="Numéro / référence de la taxe professionnelle",
    )
    CNSS = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name="CNSS",
        help_text="Numéro CNSS de l'entreprise",
    )

    # DATES
    date_created = models.DateTimeField(
        verbose_name="Date de création",
        help_text="Horodatage de la création de l'enregistrement",
        default=timezone.now,
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Horodatage de la dernière modification",
        db_index=True,
    )

    # Suspension status
    suspended = models.BooleanField(
        default=False,
        verbose_name="Suspendu",
        help_text="Indique si l'entreprise est suspendue",
        db_index=True,
    )

    # Foreign currency
    uses_foreign_currency = models.BooleanField(
        default=False,
        verbose_name="Utilise une devise étrangère",
        help_text="Si activé, les sélecteurs de devise sont affichés dans les articles et les documents",
    )

    history = HistoricalRecords(
        verbose_name="Historique Société", verbose_name_plural="Historiques Sociétés"
    )

    class Meta:
        verbose_name = "Société"
        verbose_name_plural = "Sociétés"
        ordering = ("-date_created",)

    def __str__(self):
        return self.raison_sociale
