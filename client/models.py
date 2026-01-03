from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

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
        max_length=50, unique=True, verbose_name="Code client"
    )
    client_type = models.CharField(
        max_length=2, choices=TYPE_CHOICES, verbose_name="Type de client"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        verbose_name="Entreprise",
        blank=True,
        null=True,
        related_name="clients",
    )
    # Champs communs
    adresse = models.CharField(
        max_length=255, verbose_name="Adresse", blank=True, null=True
    )
    ville = models.ForeignKey(
        Ville, on_delete=models.SET_NULL, verbose_name="Ville", blank=True, null=True
    )
    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message="Tapez un numéro de téléphone valide",
    )
    tel = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name="Téléphone",
        blank=True,
        null=True,
    )
    email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="E‑mail",
    )
    delai_de_paiement = models.PositiveIntegerField(
        verbose_name="Délai de paiement", blank=True, null=True, default=60
    )
    remarque = models.TextField(verbose_name="Remarque", blank=True, null=True)

    # Champs spécifiques à la personne morale
    raison_sociale = models.CharField(
        max_length=255, verbose_name="Raison sociale", blank=True, null=True
    )
    numero_du_compte = models.CharField(
        max_length=100, verbose_name="Numéro du compte", blank=True, null=True
    )
    ICE = models.CharField(max_length=100, verbose_name="ICE", blank=True, null=True)
    registre_de_commerce = models.CharField(
        max_length=100, verbose_name="Registre de commerce", blank=True, null=True
    )
    identifiant_fiscal = models.CharField(
        max_length=100, verbose_name="Identifiant fiscal", blank=True, null=True
    )
    taxe_professionnelle = models.CharField(
        max_length=100, verbose_name="Taxe professionnelle", blank=True, null=True
    )
    CNSS = models.CharField(max_length=100, verbose_name="CNSS", blank=True, null=True)
    fax = models.CharField(
        max_length=20,
        validators=[phone_validator],
        verbose_name="Fax",
        blank=True,
        null=True,
    )
    # Champs spécifiques à la personne physique
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom",
        blank=True,
        null=True,
    )
    prenom = models.CharField(
        max_length=100,
        verbose_name="Prénom",
        blank=True,
        null=True,
    )
    # DATES
    date_created = models.DateTimeField(
        verbose_name="Date de création",
        default=timezone.now,
        db_index=True,
    )
    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de modification",
        db_index=True,
    )
    # Archive status
    archived = models.BooleanField(
        default=False,
        verbose_name="Archivé",
        db_index=True,
    )

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        ordering = ("-date_created",)
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
