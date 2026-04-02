from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from company.models import Company


class MonthlyObjectives(models.Model):
    """
    Monthly objectives for a company.
    Stores target values for revenue (CA), invoices count, and conversion rate.
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="monthly_objectives",
        verbose_name=_("Société"),
        help_text=_("Société concernée par ces objectifs"),
    )

    # Target values
    objectif_ca = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Objectif CA (MAD)"),
        help_text=_("Objectif de chiffre d'affaires mensuel (MAD)"),
    )

    objectif_ca_eur = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Objectif CA (EUR)"),
        help_text=_("Objectif de chiffre d'affaires mensuel (EUR)"),
        blank=True,
        null=True,
    )

    objectif_ca_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name=_("Objectif CA (USD)"),
        help_text=_("Objectif de chiffre d'affaires mensuel (USD)"),
        blank=True,
        null=True,
    )

    objectif_factures = models.IntegerField(
        default=0,
        verbose_name=_("Objectif Factures"),
        help_text=_("Objectif de nombre de factures mensuelles"),
    )

    objectif_conversion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("Objectif Conversion"),
        help_text=_("Objectif de taux de conversion des devis (%)"),
    )

    # Metadata
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

    history = HistoricalRecords(
        verbose_name=_("Historique Objectifs Mensuels"),
        verbose_name_plural=_("Historiques Objectifs Mensuels"),
    )

    class Meta:
        verbose_name = _("Objectifs Mensuels")
        verbose_name_plural = _("Objectifs Mensuels")
        ordering = ("-date_created",)

    def __str__(self):
        return f"Objectifs mensuels - {self.company.raison_sociale}"
