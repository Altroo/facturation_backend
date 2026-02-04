from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from simple_history.models import HistoricalRecords

from account.models import CustomUser
from article.models import Article
from core.models import (
    BaseDeviFactureDocument,
    BaseDeviFactureLine,
    create_line_signal_receiver,
)


class FactureProForma(BaseDeviFactureDocument):
    numero_facture = models.CharField(
        max_length=20,
        verbose_name="Numéro de la facture pro forma",
        unique=True,
        help_text="Format ex: 0001/25",
    )

    date_facture = models.DateField(
        verbose_name="Date de facture",
        help_text="Date d'émission de la facture pro forma",
        db_index=True,
    )

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de bon de commande client",
        blank=True,
        null=True,
        help_text="Numéro du bon de commande client (optionnel)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Facture Pro-Forma",
        verbose_name_plural="Historiques Factures Pro-Forma"
    )

    class Meta:
        verbose_name = "Facture Pro-Forma"
        verbose_name_plural = "Factures Pro-Forma"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_facture

    def convert_to_facture_client(self, numero_facture, created_by_user: CustomUser):
        """Convert this FactureProForma to a FactureClient."""
        from facture_client.models import FactureClient, FactureClientLine

        # Validate document has lines
        if not self.get_lines().exists():
            raise ValueError("Impossible de convertir un document sans lignes")

        # Validate document is in convertible state
        if self.statut not in ["Envoyé", "Accepté"]:
            raise ValueError(
                f"Impossible de convertir un document avec le statut '{self.statut}'"
            )

        facture_client = FactureClient.objects.create(
            numero_facture=numero_facture,
            client=self.client,
            date_facture=self.date_facture,
            numero_bon_commande_client=self.numero_bon_commande_client,
            mode_paiement=self.mode_paiement,
            remarque=self.remarque,
            statut="Brouillon",
            total_ht=self.total_ht,
            total_tva=self.total_tva,
            total_ttc=self.total_ttc,
            remise_type=self.remise_type,
            remise=self.remise,
            total_ttc_apres_remise=self.total_ttc_apres_remise,
            created_by_user=created_by_user,
        )

        for line in self.get_lines():
            FactureClientLine.objects.create(
                facture_client=facture_client,
                article=line.article,
                prix_achat=line.prix_achat,
                devise_prix_achat=line.devise_prix_achat,
                prix_vente=line.prix_vente,
                quantity=line.quantity,
                remise_type=line.remise_type,
                remise=line.remise,
            )

        return facture_client


class FactureProFormaLine(BaseDeviFactureLine):
    facture_pro_forma = models.ForeignKey(
        FactureProForma,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Facture Pro Forma",
        help_text="Facture pro forma associée à cette ligne",
    )

    article = models.ForeignKey(
        Article, on_delete=models.PROTECT, verbose_name="Article",
        help_text="Article associé à cette ligne de facture pro forma",
    )

    history = HistoricalRecords(
        verbose_name="Historique Facture Pro-Forma",
        verbose_name_plural="Historiques Factures Pro-Forma"
    )

    class Meta:
        verbose_name = "Ligne de facture Pro-forma"
        verbose_name_plural = "Lignes de factures Pro-forma"

    def __str__(self):
        return f"{self.facture_pro_forma} - {self.article}"


@receiver([post_save, post_delete], sender=FactureProFormaLine)
def _recalc_facture_pro_forma_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("facture_pro_forma")
    handler(sender, instance, **kwargs)
