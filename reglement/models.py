from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone
from simple_history.models import HistoricalRecords

from facture_client.models import FactureClient
from parameter.models import ModePaiement


class Reglement(models.Model):
    """Model for tracking payments (règlements) on client invoices."""

    STATUT_CHOICES = [
        ("Valide", "Valide"),
        ("Annulé", "Annulé"),
    ]

    facture_client = models.ForeignKey(
        FactureClient,
        on_delete=models.PROTECT,
        related_name="reglements",
        verbose_name="Facture Client",
        help_text="Facture client associée au règlement",
        db_index=True,
    )

    mode_reglement = models.ForeignKey(
        ModePaiement,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Mode de règlement",
        help_text="Mode de paiement utilisé pour ce règlement",
    )

    libelle = models.CharField(
        max_length=255,
        verbose_name="Libellé",
        help_text="Libellé ou description du règlement",
        blank=True,
        default="",
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant",
        help_text="Montant du règlement (devise héritée de la facture client)",
    )

    date_reglement = models.DateField(
        verbose_name="Date de règlement",
        help_text="Date à laquelle le règlement a été effectué",
        default=timezone.now,
        db_index=True,
    )

    date_echeance = models.DateField(
        verbose_name="Date d'échéance",
        help_text="Date d'échéance du paiement",
        default=timezone.now,
        db_index=True,
    )

    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="Valide",
        verbose_name="Statut",
        help_text="Statut du règlement (ex: Valide, Annulé)",
    )

    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
        help_text="Horodatage de la création du règlement",
    )

    date_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Date de mise à jour",
        help_text="Horodatage de la dernière modification du règlement",
    )

    history = HistoricalRecords(
        verbose_name="Historique Règlement",
        verbose_name_plural="Historiques Règlements",
    )

    class Meta:
        verbose_name = "Règlement"
        verbose_name_plural = "Règlements"
        ordering = ("-date_created",)

    def __str__(self):
        return f"Règlement {self.id} - {self.facture_client.numero_facture}"

    @staticmethod
    def get_total_reglements_for_facture(
        facture_client_id: int, exclude_reglement_id: int = None
    ) -> Decimal:
        """
        Get the total of all valid règlements for a specific facture client.
        Optionally exclude a specific reglement (useful for updates).
        """
        queryset = Reglement.objects.filter(
            facture_client_id=facture_client_id, statut="Valide"
        )
        if exclude_reglement_id:
            queryset = queryset.exclude(pk=exclude_reglement_id)

        total = queryset.aggregate(total=Sum("montant"))["total"]
        return total or Decimal("0.00")

    @staticmethod
    def get_reste_a_payer(
        facture_client: FactureClient, exclude_reglement_id: int = None
    ) -> Decimal:
        """
        Calculate the remaining amount to pay for a facture client.
        """
        montant_facture = facture_client.total_ttc_apres_remise
        total_reglements = Reglement.get_total_reglements_for_facture(
            facture_client.id, exclude_reglement_id
        )
        return montant_facture - total_reglements
