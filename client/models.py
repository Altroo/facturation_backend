from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from company.models import Company
from parameter.models import Ville


class Client(models.Model):
    PERSONNE_MORALE = "PM"
    PERSONNE_PHYSIQUE = "PP"
    TYPE_CHOICES = [
        (PERSONNE_MORALE, "Personne morale"),
        (PERSONNE_PHYSIQUE, "Personne physique"),
    ]

    code_client = models.CharField(
        max_length=50,
        verbose_name="Code client",
        help_text="Code unique identifiant le client par société",
    )
    client_type = models.CharField(
        max_length=2,
        choices=TYPE_CHOICES,
        verbose_name="Type de client",
        help_text="Type : Personne morale (PM) ou physique (PP)",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        verbose_name="Société",
        help_text="Société propriétaire du client",
        related_name="clients",
        null=True,
        blank=True,
    )
    # Champs communs
    adresse = models.CharField(
        max_length=255,
        verbose_name="Adresse",
        help_text="Adresse postale du client",
        blank=True,
        null=True,
    )
    ville = models.ForeignKey(
        Ville,
        on_delete=models.SET_NULL,
        verbose_name="Ville",
        help_text="Ville du client",
        blank=True,
        null=True,
    )
    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message="Tapez un numéro de téléphone valide",
    )
    tel = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name="Téléphone",
        help_text="Numéro de téléphone principal",
        blank=True,
        null=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="E‑mail",
        help_text="Adresse e‑mail du client",
    )
    delai_de_paiement = models.PositiveIntegerField(
        verbose_name="Délai de paiement",
        help_text="Délai de paiement en jours",
        blank=True,
        null=True,
        default=60,
    )
    remarque = models.TextField(
        verbose_name="Remarque",
        help_text="Remarque ou note concernant le client",
        blank=True,
        null=True,
    )

    # Champs spécifiques à la personne morale
    raison_sociale = models.CharField(
        max_length=255,
        verbose_name="Raison sociale",
        help_text="Raison sociale pour les personnes morales",
        blank=True,
        null=True,
    )
    numero_du_compte = models.CharField(
        max_length=100,
        verbose_name="Numéro du compte",
        help_text="Numéro de compte bancaire du client",
        blank=True,
        null=True,
    )
    ICE = models.CharField(
        max_length=100,
        verbose_name="ICE",
        help_text="Identifiant Commun de l'Entreprise (ICE)",
        blank=True,
        null=True,
    )
    registre_de_commerce = models.CharField(
        max_length=100,
        verbose_name="Registre de commerce",
        help_text="Numéro du registre de commerce",
        blank=True,
        null=True,
    )
    identifiant_fiscal = models.CharField(
        max_length=100,
        verbose_name="Identifiant fiscal",
        help_text="Identifiant fiscal (IF)",
        blank=True,
        null=True,
    )
    taxe_professionnelle = models.CharField(
        max_length=100,
        verbose_name="Taxe professionnelle",
        help_text="Référence de la taxe professionnelle",
        blank=True,
        null=True,
    )
    CNSS = models.CharField(
        max_length=100,
        verbose_name="CNSS",
        help_text="Numéro CNSS",
        blank=True,
        null=True,
    )
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name="Fax",
        help_text="Numéro de fax (optionnel)",
        blank=True,
        null=True,
    )
    # Champs spécifiques à la personne physique
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom",
        help_text="Nom (pour personne physique)",
        blank=True,
        null=True,
    )
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom",
        help_text="Prénom (pour personne physique)",
        blank=True,
        null=True,
    )
    # DATES
    date_created = models.DateTimeField(
        verbose_name="Date de création",
        help_text="Horodatage de la création du client",
        default=timezone.now,
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        help_text="Horodatage de la dernière modification",
        db_index=True,
    )
    # Archive status
    archived = models.BooleanField(
        default=False,
        verbose_name="Archivé",
        help_text="Indique si le client est archivé",
        db_index=True,
    )

    history = HistoricalRecords(
        verbose_name="Historique Client",
        verbose_name_plural="Historiques Clients"
    )

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ("-date_created",)
        unique_together = [('code_client', 'company')]
        indexes = [
            models.Index(fields=["company", "archived"]),
        ]

    def __str__(self):
        if self.client_type == self.PERSONNE_MORALE and self.raison_sociale:
            name = self.raison_sociale
        elif self.client_type == self.PERSONNE_PHYSIQUE:
            name = f"{self.nom or ''} {self.prenom or ''}".strip()
        else:
            name = self.code_client
        return f"{name}"
