from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from simple_history.models import HistoricalRecords

from article.models import Article
from core.models import (
    BaseDeviFactureDocument,
    BaseDeviFactureLine,
    create_line_signal_receiver,
)
from parameter.models import LivrePar


class BonDeLivraison(BaseDeviFactureDocument):
    STATUT_CHOICES = [
        ("Brouillon", "Brouillon"),
        ("Envoyé", "Envoyé"),
        ("Accepté", "Accepté"),
        ("Refusé", "Refusé"),
        ("Annulé", "Annulé"),
        ("Expiré", "Expiré"),
        ("Facturé", "Facturé"),
    ]
    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="Brouillon",
        verbose_name="Statut",
        help_text="Statut du bon de livraison",
    )

    numero_bon_livraison = models.CharField(
        max_length=20,
        verbose_name="Numéro du bon de livraison",
        unique=True,
        help_text="Format ex: 0001/25",
    )

    date_bon_livraison = models.DateField(
        verbose_name="Date du bon de livraison",
        help_text="Date d'émission du bon de livraison",
        db_index=True,
    )

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de bon de commande client",
        blank=True,
        null=True,
        help_text="Numéro du bon de commande client (optionnel)",
    )

    livre_par = models.ForeignKey(
        LivrePar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Livré par",
        help_text="Livreur ayant effectué la livraison",
    )

    history = HistoricalRecords(
        verbose_name="Historique Bon de Livraison",
        verbose_name_plural="Historiques Bons de Livraison"
    )

    class Meta:
        verbose_name = "Bon de Livraison"
        verbose_name_plural = "Bons de Livraison"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_bon_livraison


class BonDeLivraisonLine(BaseDeviFactureLine):
    bon_de_livraison = models.ForeignKey(
        BonDeLivraison,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Bon de Livraison",
        help_text="Bon de livraison parent associé à cette ligne",
    )

    article = models.ForeignKey(
        Article, on_delete=models.PROTECT, verbose_name="Article",
        help_text="Article livré",
    )

    history = HistoricalRecords(
        verbose_name="Historique Ligne de bon de livraison",
        verbose_name_plural="Historiques Lignes de bons de livraison"
    )

    class Meta:
        verbose_name = "Ligne de bon de livraison"
        verbose_name_plural = "Lignes de bons de livraison"

    def __str__(self):
        return f"{self.bon_de_livraison} - {self.article}"


@receiver([post_save, post_delete], sender=BonDeLivraisonLine)
def _recalc_bon_de_livraison_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("bon_de_livraison")
    handler(sender, instance, **kwargs)
