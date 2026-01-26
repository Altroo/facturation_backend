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


class Devi(BaseDeviFactureDocument):
    numero_devis = models.CharField(
        max_length=20,
        verbose_name="Numéro du devis",
        unique=True,
        help_text="Format ex: 0001/25",
    )

    date_devis = models.DateField(
        verbose_name="Date du devis",
        db_index=True,
        help_text="Date d'émission du devis",
    )

    numero_demande_prix_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de la demande de prix du client",
        blank=True,
        null=True,
        help_text="Numéro de la demande de prix du client (optionnel)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Devis",
        verbose_name_plural="Historiques Devis"
    )

    class Meta:
        verbose_name = "Devis"
        verbose_name_plural = "Devis"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_devis

    def convert_to_facture_proforma(self, numero_facture, created_by_user: CustomUser):
        """Convert this Devis to a FactureProForma."""
        from facture_proforma.models import FactureProForma, FactureProFormaLine

        # Validate document has lines
        if not self.get_lines().exists():
            raise ValueError("Impossible de convertir un document sans lignes")

        # Validate document is in convertible state
        if self.statut not in ["Envoyé", "Accepté"]:
            raise ValueError(
                f"Impossible de convertir un document avec le statut '{self.statut}'"
            )

        facture_pro_forma = FactureProForma.objects.create(
            numero_facture=numero_facture,
            client=self.client,
            date_facture=self.date_devis,
            numero_bon_commande_client=self.numero_demande_prix_client,
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
            FactureProFormaLine.objects.create(
                facture_pro_forma=facture_pro_forma,
                article=line.article,
                prix_achat=line.prix_achat,
                prix_vente=line.prix_vente,
                quantity=line.quantity,
                remise_type=line.remise_type,
                remise=line.remise,
            )

        return facture_pro_forma

    def convert_to_facture_client(self, numero_facture, created_by_user: CustomUser):
        """Convert this Devis to a FactureClient."""
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
            date_facture=self.date_devis,
            numero_bon_commande_client=self.numero_demande_prix_client,
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
                prix_vente=line.prix_vente,
                quantity=line.quantity,
                remise_type=line.remise_type,
                remise=line.remise,
            )

        return facture_client


class DeviLine(BaseDeviFactureLine):
    devis = models.ForeignKey(
        Devi,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Devis",
        help_text="Document Devis parent associé à cette ligne",
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name="Article",
        help_text="Article associé à cette ligne de devis",
    )

    history = HistoricalRecords(
        verbose_name="Historique Ligne de devis",
        verbose_name_plural="Historiques Lignes de devis"
    )

    class Meta:
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"

    def __str__(self):
        return f"{self.devis} - {self.article}"


@receiver([post_save, post_delete], sender=DeviLine)
def _recalc_devi_on_line_change(sender, instance, **kwargs):
    """Recalculate parent devi totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("devis")
    handler(sender, instance, **kwargs)
