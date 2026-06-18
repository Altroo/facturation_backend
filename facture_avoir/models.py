from decimal import Decimal

from django.db import models
from django.db.models import Sum
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
from facture_client.models import FactureClient
from .utils import get_next_numero_facture_avoir

AVOIR_ACTIVE_STATUSES = ("Envoyé", "Accepté")


class FactureAvoir(BaseDeviFactureDocument):
    MOTIF_CHOICES = [
        ("retour_marchandise", _("Retour marchandise")),
        ("erreur_facturation", _("Erreur de facturation")),
        ("remise", _("Remise")),
        ("annulation", _("Annulation")),
        ("autre", _("Autre")),
    ]

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="factures_avoir",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de la facture d'avoir"),
    )
    facture_origine = models.ForeignKey(
        FactureClient,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="avoirs",
        verbose_name=_("Facture d'origine"),
        help_text=_("Facture client créditée par cet avoir"),
    )
    numero_avoir = models.CharField(
        max_length=20,
        verbose_name=_("Numéro de la facture d'avoir"),
        help_text=_("Format ex: AV001/26"),
    )
    date_avoir = models.DateField(
        verbose_name=_("Date de l'avoir"),
        help_text=_("Date d'émission de la facture d'avoir"),
        db_index=True,
    )
    motif_avoir = models.CharField(
        max_length=30,
        choices=MOTIF_CHOICES,
        verbose_name=_("Motif de l'avoir"),
        help_text=_("Motif obligatoire de la facture d'avoir"),
    )
    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name=_("Référence client"),
        blank=True,
        null=True,
        help_text=_("Référence optionnelle pour les avoirs libres"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Facture d'avoir"),
        verbose_name_plural=_("Historiques Factures d'avoir"),
    )

    class Meta:
        verbose_name = _("Facture d'avoir")
        verbose_name_plural = _("Factures d'avoir")
        ordering = ("-date_created",)
        unique_together = [("numero_avoir", "company")]
        indexes = [
            models.Index(fields=["company", "date_avoir"]),
            models.Index(fields=["client", "company"]),
            models.Index(fields=["facture_origine", "company"]),
            models.Index(fields=["motif_avoir", "company"]),
        ]

    def __str__(self):
        return self.numero_avoir

    def save(self, *args, **kwargs):
        """Assign company and legal number server-side."""
        if self.facture_origine_id:
            self.client = self.facture_origine.client
            self.company = self.facture_origine.company
            if not self.mode_paiement_id:
                self.mode_paiement = self.facture_origine.mode_paiement
            if not self.devise:
                self.devise = self.facture_origine.devise
        elif self.client_id:
            self.company = self.client.company

        if not self.numero_avoir and self.company_id:
            self.numero_avoir = get_next_numero_facture_avoir(self.company_id)

        super().save(*args, **kwargs)

    @staticmethod
    def get_total_avoirs_for_facture(
        facture_client_id: int, exclude_avoir_id: int | None = None
    ) -> Decimal:
        queryset = FactureAvoir.objects.filter(
            facture_origine_id=facture_client_id,
            statut__in=AVOIR_ACTIVE_STATUSES,
        )
        if exclude_avoir_id:
            queryset = queryset.exclude(pk=exclude_avoir_id)
        return queryset.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")

    @staticmethod
    def get_total_avoirs_for_company(
        company_id: int, devise: str | None = None
    ) -> Decimal:
        queryset = FactureAvoir.objects.filter(
            company_id=company_id,
            statut__in=AVOIR_ACTIVE_STATUSES,
        )
        if devise:
            queryset = queryset.filter(devise=devise)
        return queryset.aggregate(total=Sum("total_ttc_apres_remise"))[
            "total"
        ] or Decimal("0.00")


class FactureAvoirLine(BaseDeviFactureLine):
    facture_avoir = models.ForeignKey(
        FactureAvoir,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("Facture d'avoir"),
        help_text=_("Facture d'avoir associée à cette ligne"),
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name=_("Article"),
        help_text=_("Article associé à cette ligne d'avoir"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Ligne de facture d'avoir"),
        verbose_name_plural=_("Historiques Lignes de factures d'avoir"),
    )

    class Meta:
        verbose_name = _("Ligne de facture d'avoir")
        verbose_name_plural = _("Lignes de factures d'avoir")

    def __str__(self):
        return f"{self.facture_avoir} - {self.article}"


@receiver([post_save, post_delete], sender=FactureAvoirLine)
def _recalc_facture_avoir_on_line_change(sender, instance, **kwargs):
    handler = create_line_signal_receiver("facture_avoir")
    handler(sender, instance, **kwargs)
