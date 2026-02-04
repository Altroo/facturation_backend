from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from simple_history.models import HistoricalRecords

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

    date_facture = models.DateField(
        verbose_name="Date de facture",
        help_text="Date d'émission de la facture",
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
        verbose_name="Historique Facture Client",
        verbose_name_plural="Historiques Factures Client"
    )

    class Meta:
        verbose_name = "Facture Client"
        verbose_name_plural = "Factures Client"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_facture

    def convert_to_bon_de_livraison(
        self, numero_bon_livraison, created_by_user: CustomUser
    ):
        """Convert this FactureClient to a BonDeLivraison."""
        from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine

        # Validate document has lines
        if not self.get_lines().exists():
            raise ValueError("Impossible de convertir un document sans lignes")

        # Validate document is in convertible state
        if self.statut not in ["Envoyé", "Accepté"]:
            raise ValueError(
                f"Impossible de convertir un document avec le statut '{self.statut}'"
            )

        bon_de_livraison = BonDeLivraison.objects.create(
            numero_bon_livraison=numero_bon_livraison,
            client=self.client,
            date_bon_livraison=self.date_facture,
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
            BonDeLivraisonLine.objects.create(
                bon_de_livraison=bon_de_livraison,
                article=line.article,
                prix_achat=line.prix_achat,
                devise_prix_achat=line.devise_prix_achat,
                prix_vente=line.prix_vente,
                quantity=line.quantity,
                remise_type=line.remise_type,
                remise=line.remise,
            )

        return bon_de_livraison


class FactureClientLine(BaseDeviFactureLine):
    facture_client = models.ForeignKey(
        FactureClient,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Facture Client",
        help_text="Facture client associée à cette ligne",
    )

    article = models.ForeignKey(
        Article, on_delete=models.PROTECT, verbose_name="Article",
        help_text="Article associé à cette ligne de facture",
    )

    history = HistoricalRecords(
        verbose_name="Historique Facture Client",
        verbose_name_plural="Historiques Factures Client"
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
