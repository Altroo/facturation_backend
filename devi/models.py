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
        max_length=50, verbose_name="Numéro de la demande de prix du client"
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
    prix_achat = models.PositiveIntegerField(verbose_name="Prix d'achat")
    prix_vente = models.PositiveIntegerField(verbose_name="Prix de vente")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantité")
    pourcentage_remise = models.PositiveIntegerField(
        default=0, verbose_name="Pourcentage de remise"
    )

    class Meta:
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"

    def __str__(self):
        return f"{self.devis} - {self.article}"
