from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from article.models import Article
from core.models import (
    BaseDeviFactureDocument,
    BaseDeviFactureLine,
    create_line_signal_receiver,
)
from parameter.models import LivrePar


class BonDeLivraison(BaseDeviFactureDocument):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="bons_de_livraison",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire du bon de livraison"),
    )

    STATUT_CHOICES = [
        ("Brouillon", _("Brouillon")),
        ("Envoyé", _("Envoyé")),
        ("Accepté", _("Accepté")),
        ("Refusé", _("Refusé")),
        ("Annulé", _("Annulé")),
        ("Expiré", _("Expiré")),
        ("Facturé", _("Facturé")),
    ]
    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="Brouillon",
        verbose_name=_("Statut"),
        help_text=_("Statut du bon de livraison"),
    )

    numero_bon_livraison = models.CharField(
        max_length=20,
        verbose_name=_("Numéro du bon de livraison"),
        help_text=_("Format ex: 0001/25"),
    )

    date_bon_livraison = models.DateField(
        verbose_name=_("Date du bon de livraison"),
        help_text=_("Date d'émission du bon de livraison"),
        db_index=True,
    )

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name=_("Numéro de bon de commande client"),
        blank=True,
        null=True,
        help_text=_("Numéro du bon de commande client (optionnel)"),
    )

    livre_par = models.ForeignKey(
        LivrePar,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Livré par"),
        help_text=_("Livreur ayant effectué la livraison"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Bon de Livraison"),
        verbose_name_plural=_("Historiques Bons de Livraison"),
    )

    class Meta:
        verbose_name = _("Bon de Livraison")
        verbose_name_plural = _("Bons de Livraison")
        ordering = ("-date_created",)
        unique_together = [("numero_bon_livraison", "company")]
        indexes = [
            models.Index(fields=["company", "date_bon_livraison"]),
            models.Index(fields=["client", "company"]),
        ]

    def __str__(self):
        return self.numero_bon_livraison

    def save(self, *args, **kwargs):
        """Auto-populate company from client before saving."""
        if self.client_id:
            self.company = self.client.company
        super().save(*args, **kwargs)


class BonDeLivraisonLine(BaseDeviFactureLine):
    bon_de_livraison = models.ForeignKey(
        BonDeLivraison,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("Bon de Livraison"),
        help_text=_("Bon de livraison parent associé à cette ligne"),
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name=_("Article"),
        help_text=_("Article livré"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Ligne de bon de livraison"),
        verbose_name_plural=_("Historiques Lignes de bons de livraison"),
    )

    class Meta:
        verbose_name = _("Ligne de bon de livraison")
        verbose_name_plural = _("Lignes de bons de livraison")

    def __str__(self):
        return f"{self.bon_de_livraison} - {self.article}"


@receiver([post_save, post_delete], sender=BonDeLivraisonLine)
def _recalc_bon_de_livraison_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("bon_de_livraison")
    handler(sender, instance, **kwargs)
