from django.db import models

from account.models import CustomUser
from article.models import Article
from client.models import Client
from parameter.models import ModePaiement


class Devi(models.Model):
    STATUT_CHOICES = [
        ("Brouillon", "Brouillon"),
        ("Envoyé", "Envoyé"),
        ("Accepté", "Accepté"),
        ("Refusé", "Refusé"),
        ("Annulé", "Annulé"),
        ("Expiré", "Expiré"),
    ]
    numero_devis = models.CharField(
        max_length=20,
        verbose_name="Numéro du devis",
        unique=True,
        help_text="Format ex: 0001/25",
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Client")
    date_devis = models.DateField(verbose_name="Date du devis", db_index=True)
    numero_demande_prix_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de la demande de prix du client",
        blank=True,
        null=True,
    )
    mode_paiement = models.ForeignKey(
        ModePaiement,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Mode de paiement",
    )
    remarque = models.TextField(verbose_name="Remarque", blank=True, null=True)
    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="Brouillon",
        verbose_name="Statut",
    )

    REMISE_TYPE_CHOICES = [
        ("pourcentage", "Pourcentage"),
        ("fixe", "Fixe"),
    ]

    total_ht = models.PositiveIntegerField(
        default=0,
        verbose_name="Total HT",
        help_text="Somme des totaux des lignes avant TVA",
        editable=False,
    )

    total_tva = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TVA",
        help_text="Montant total de la TVA",
        editable=False,
    )

    total_ttc = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TTC",
        help_text="Total toutes taxes comprises (TTC)",
        editable=False,
    )

    remise_type = models.CharField(
        max_length=12,
        choices=REMISE_TYPE_CHOICES,
        default="pourcentage",
        verbose_name="Type de remise",
        help_text="Type de remise appliquée : 'pourcentage' ou 'fixe'",
    )

    remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Valeur remise",
        help_text="Valeur de la remise appliquée",
    )

    total_ttc_apres_remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TTC après remise",
        help_text="Total TTC après application de la remise",
        editable=False,
    )

    date_created = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )
    date_updated = models.DateTimeField(
        auto_now=True, verbose_name="Date de mise à jour"
    )
    created_by_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Créé par l'utilisateur",
    )

    class Meta:
        verbose_name = "Devis"
        verbose_name_plural = "Devis"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_devis


class DeviLine(models.Model):
    devis = models.ForeignKey(
        Devi, on_delete=models.CASCADE, related_name="lignes", verbose_name="Devis"
    )
    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, verbose_name="Article"
    )
    prix_achat = models.PositiveIntegerField(
        verbose_name="Prix d'achat",
        help_text="Prix d'achat unitaire (entier positif, ex: en MAD)",
    )
    prix_vente = models.PositiveIntegerField(
        verbose_name="Prix de vente",
        help_text="Prix de vente unitaire (entier positif, ex: en MAD)",
    )
    quantity = models.PositiveIntegerField(
        default=1, verbose_name="Quantité", help_text="Quantité (entier positif)"
    )

    REMISE_TYPE_CHOICES = [
        ("pourcentage", "Pourcentage"),
        ("fixe", "Fixe"),
    ]

    remise_type = models.CharField(
        max_length=12,
        choices=REMISE_TYPE_CHOICES,
        default="pourcentage",
        verbose_name="Type de remise",
        help_text="Type de remise appliquée : 'Pourcentage' ou 'Fixe'",
    )

    remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Valeur remise",
        help_text="Valeur après application de la remise",
    )

    class Meta:
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"

    def __str__(self):
        return f"{self.devis} - {self.article}"
