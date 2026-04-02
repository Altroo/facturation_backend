from os import path
from uuid import uuid4

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
        verbose_name=_("Raison sociale"),
        help_text=_("Raison sociale de l'entreprise"),
        db_index=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        default=None,
        verbose_name=_("E‑mail"),
        help_text=_("Adresse e‑mail de contact de l'entreprise"),
    )
    logo = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Logo"),
        help_text=_("Logo de l'entreprise (image)"),
        max_length=1000,
    )
    logo_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Logo recadré"),
        help_text=_("Version recadrée du logo"),
        max_length=1000,
    )

    cachet = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Cachet"),
        help_text=_("Image du cachet de l'entreprise"),
        max_length=1000,
    )

    cachet_cropped = models.ImageField(
        upload_to=get_company_image_path,
        blank=True,
        null=True,
        default=None,
        verbose_name=_("Cachet recadré"),
        help_text=_("Version recadrée du cachet"),
        max_length=1000,
    )

    # Number of employees (choice)
    NBR_EMPLOYE_CHOICES = [
        ("1 à 5", _("1 à 5")),
        ("5 à 10", _("5 à 10")),
        ("10 à 50", _("10 à 50")),
        ("50 à 100", _("50 à 100")),
        ("plus que 100", _("plus que 100")),
    ]
    nbr_employe = models.CharField(
        max_length=12,
        choices=NBR_EMPLOYE_CHOICES,
        default=1,
        verbose_name=_("Nombre d'employés"),
        help_text=_("Tranche du nombre d'employés"),
    )

    # Responsable details
    CIVILITE_CHOICES = [
        ("", ""),
        ("Mme", _("Mme")),
        ("Mlle", _("Mlle")),
        ("M.", _("M.")),
    ]
    civilite_responsable = models.CharField(
        max_length=4,
        choices=CIVILITE_CHOICES,
        default="",
        verbose_name=_("Civilité du responsable"),
        help_text=_("Civilité du responsable (Mme, M., ...)"),
    )
    nom_responsable = models.CharField(
        max_length=255,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Nom du responsable"),
        help_text=_("Nom complet du responsable"),
    )

    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message=_("Tapez un numéro de téléphone valide"),
    )
    gsm_responsable = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name=_("GSM du responsable"),
        help_text=_("Numéro mobile du responsable (format international recommandé)"),
    )
    adresse = models.TextField(
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Adresse"),
        help_text=_("Adresse postale complète de l'entreprise"),
    )
    telephone = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Téléphone"),
        help_text=_("Numéro de téléphone principal"),
    )
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Fax"),
        help_text=_("Numéro de fax (optionnel)"),
    )
    site_web = models.URLField(
        default="",
        blank=True,
        null=True,
        verbose_name=_("Site web"),
        help_text=_("URL du site web de l'entreprise"),
    )

    # Administrative identifiers
    numero_du_compte = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Numéro du compte"),
        help_text=_("Numéro de compte bancaire ou interne"),
    )
    ICE = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("ICE"),
        help_text=_("Identifiant Commun de l'Entreprise (ICE)"),
    )
    registre_de_commerce = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Registre de commerce"),
        help_text=_("Numéro du registre de commerce"),
    )
    identifiant_fiscal = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Identifiant fiscal"),
        help_text=_("Identifiant fiscal de l'entreprise"),
    )
    tax_professionnelle = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("Taxe professionnelle"),
        help_text=_("Numéro / référence de la taxe professionnelle"),
    )
    CNSS = models.CharField(
        max_length=100,
        default=None,
        blank=True,
        null=True,
        verbose_name=_("CNSS"),
        help_text=_("Numéro CNSS de l'entreprise"),
    )

    # DATES
    date_created = models.DateTimeField(
        verbose_name=_("Date de création"),
        help_text=_("Horodatage de la création de l'enregistrement"),
        default=timezone.now,
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification"),
        help_text=_("Horodatage de la dernière modification"),
        db_index=True,
    )

    # Suspension status
    suspended = models.BooleanField(
        default=False,
        verbose_name=_("Suspendu"),
        help_text=_("Indique si l'entreprise est suspendue"),
        db_index=True,
    )

    # Foreign currency
    uses_foreign_currency = models.BooleanField(
        default=False,
        verbose_name=_("Utilise une devise étrangère"),
        help_text=_("Si activé, les sélecteurs de devise sont affichés dans les articles et les documents"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Société"), verbose_name_plural=_("Historiques Sociétés")
    )

    class Meta:
        verbose_name = _("Société")
        verbose_name_plural = _("Sociétés")
        ordering = ("-date_created",)

    def __str__(self):
        return self.raison_sociale
