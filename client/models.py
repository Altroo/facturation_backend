from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from company.models import Company
from parameter.models import Ville


class Client(models.Model):
    PERSONNE_MORALE = "PM"
    PERSONNE_PHYSIQUE = "PP"
    TYPE_CHOICES = [
        (PERSONNE_MORALE, _("Personne morale")),
        (PERSONNE_PHYSIQUE, _("Personne physique")),
    ]

    code_client = models.CharField(
        max_length=50,
        verbose_name=_("Code client"),
        help_text=_("Code unique identifiant le client par société"),
    )
    client_type = models.CharField(
        max_length=2,
        choices=TYPE_CHOICES,
        verbose_name=_("Type de client"),
        help_text=_("Type : Personne morale (PM) ou physique (PP)"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        verbose_name=_("Société"),
        help_text=_("Société propriétaire du client"),
        related_name="clients",
    )
    # Champs communs
    adresse = models.CharField(
        max_length=255,
        verbose_name=_("Adresse"),
        help_text=_("Adresse postale du client"),
        blank=True,
        null=True,
    )
    ville = models.ForeignKey(
        Ville,
        on_delete=models.SET_NULL,
        verbose_name=_("Ville"),
        help_text=_("Ville du client"),
        blank=True,
        null=True,
    )
    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message=_("Tapez un numéro de téléphone valide"),
    )
    tel = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name=_("Téléphone"),
        help_text=_("Numéro de téléphone principal"),
        blank=True,
        null=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("E‑mail"),
        help_text=_("Adresse e‑mail du client"),
    )
    delai_de_paiement = models.PositiveIntegerField(
        verbose_name=_("Délai de paiement"),
        help_text=_("Délai de paiement en jours"),
        blank=True,
        null=True,
        default=60,
    )
    remarque = models.TextField(
        verbose_name=_("Remarque"),
        help_text=_("Remarque ou note concernant le client"),
        blank=True,
        null=True,
    )

    # Champs spécifiques à la personne morale
    raison_sociale = models.CharField(
        max_length=255,
        verbose_name=_("Raison sociale"),
        help_text=_("Raison sociale pour les personnes morales"),
        blank=True,
        null=True,
    )
    numero_du_compte = models.CharField(
        max_length=100,
        verbose_name=_("Numéro du compte"),
        help_text=_("Numéro de compte bancaire du client"),
        blank=True,
        null=True,
    )
    ICE = models.CharField(
        max_length=100,
        verbose_name=_("ICE"),
        help_text=_("Identifiant Commun de l'Entreprise (ICE)"),
        blank=True,
        null=True,
    )
    registre_de_commerce = models.CharField(
        max_length=100,
        verbose_name=_("Registre de commerce"),
        help_text=_("Numéro du registre de commerce"),
        blank=True,
        null=True,
    )
    identifiant_fiscal = models.CharField(
        max_length=100,
        verbose_name=_("Identifiant fiscal"),
        help_text=_("Identifiant fiscal (IF)"),
        blank=True,
        null=True,
    )
    taxe_professionnelle = models.CharField(
        max_length=100,
        verbose_name=_("Taxe professionnelle"),
        help_text=_("Référence de la taxe professionnelle"),
        blank=True,
        null=True,
    )
    CNSS = models.CharField(
        max_length=100,
        verbose_name=_("CNSS"),
        help_text=_("Numéro CNSS"),
        blank=True,
        null=True,
    )
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name=_("Fax"),
        help_text=_("Numéro de fax (optionnel)"),
        blank=True,
        null=True,
    )
    # Champs spécifiques à la personne physique
    nom = models.CharField(
        max_length=100,
        verbose_name=_("Nom"),
        help_text=_("Nom (pour personne physique)"),
        blank=True,
        null=True,
    )
    prenom = models.CharField(
        max_length=100,
        verbose_name=_("Prénom"),
        help_text=_("Prénom (pour personne physique)"),
        blank=True,
        null=True,
    )
    # DATES
    date_created = models.DateTimeField(
        verbose_name=_("Date de création"),
        help_text=_("Horodatage de la création du client"),
        default=timezone.now,
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification"),
        help_text=_("Horodatage de la dernière modification"),
        db_index=True,
    )
    # Archive status
    archived = models.BooleanField(
        default=False,
        verbose_name=_("Archivé"),
        help_text=_("Indique si le client est archivé"),
        db_index=True,
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Client"), verbose_name_plural=_("Historiques Clients")
    )

    class Meta:
        verbose_name = _("Client")
        verbose_name_plural = _("Clients")
        ordering = ("-date_created",)
        unique_together = [("code_client", "company")]
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
