from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from account.models import CustomUser
from article.models import Article
from client.models import Client
from core.models import (
    BaseDeviFactureDocument,
    BaseDeviFactureLine,
    create_line_signal_receiver,
)
from parameter.models import ModePaiement


class FactureClient(BaseDeviFactureDocument):
    numero_facture = models.CharField(
        max_length=20,
        verbose_name="Numéro de la facture client",
        unique=True,
        help_text="Format ex: 0001/25",
    )

    date_facture = models.DateField(verbose_name="Date de facture", db_index=True)

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de bon de commande client",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Facture Client"
        verbose_name_plural = "Factures Client"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_facture


class FactureClientLine(BaseDeviFactureLine):
    facture_client = models.ForeignKey(
        FactureClient,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Facture Client",
    )

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, verbose_name="Article"
    )

    class Meta:
        verbose_name = "Ligne de facture Client"
        verbose_name_plural = "Lignes de factures Client"

    def __str__(self):
        return f"{self.facture_client} - {self.article}"


@receiver([post_save, post_delete], sender=FactureClientLine)
def _recalc_facture_client_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("facture_client")
    handler(sender, instance, **kwargs)
