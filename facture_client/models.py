from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
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
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="factures_client",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de la facture"),
    )

    numero_facture = models.CharField(
        max_length=20,
        verbose_name=_("Numéro de la facture client"),
        help_text=_("Format ex: 0001/25"),
    )

    date_facture = models.DateField(
        verbose_name=_("Date de facture"),
        help_text=_("Date d'émission de la facture"),
        db_index=True,
    )

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name=_("Numéro de bon de commande client"),
        blank=True,
        null=True,
        help_text=_("Numéro du bon de commande client (optionnel)"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Facture Client"),
        verbose_name_plural=_("Historiques Factures Client"),
    )

    class Meta:
        verbose_name = _("Facture Client")
        verbose_name_plural = _("Factures Client")
        ordering = ("-date_created",)
        unique_together = [("numero_facture", "company")]
        indexes = [
            models.Index(fields=["company", "date_facture"]),
            models.Index(fields=["client", "company"]),
        ]

    def __str__(self):
        return self.numero_facture

    def save(self, *args, **kwargs):
        """Autopopulate company from client before saving."""
        if self.client_id:
            self.company = self.client.company
        super().save(*args, **kwargs)

    @transaction.atomic()
    def convert_to_bon_de_livraison(
        self, numero_bon_livraison, created_by_user: CustomUser
    ):
        """Convert this FactureClient to a BonDeLivraison.

        This method is wrapped in a transaction to ensure atomicity.
        If any part of the conversion fails, all changes will be rolled back.
        """
        from bon_de_livraison.models import BonDeLivraison, BonDeLivraisonLine

        # Validate document has lines
        if not self.get_lines().exists():
            raise ValueError(_("Impossible de convertir un document sans lignes"))

        # Validate document is in convertible state
        if self.statut not in ["Envoyé", "Accepté"]:
            raise ValueError(
                _("Impossible de convertir un document avec le statut '%(statut)s'")
                % {"statut": self.statut}
            )

        bon_de_livraison = BonDeLivraison.objects.create(
            numero_bon_livraison=numero_bon_livraison,
            company=self.company,
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
            devise=self.devise,
            created_by_user=created_by_user,
        )

        for line in self.get_lines():
            BonDeLivraisonLine.objects.create(
                bon_de_livraison=bon_de_livraison,
                article=line.article,
                prix_achat=line.prix_achat,
                devise_prix_achat=line.devise_prix_achat,
                prix_vente=line.prix_vente,
                devise_prix_vente=line.devise_prix_vente,
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
        verbose_name=_("Facture Client"),
        help_text=_("Facture client associée à cette ligne"),
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name=_("Article"),
        help_text=_("Article associé à cette ligne de facture"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Facture Client"),
        verbose_name_plural=_("Historiques Factures Client"),
    )

    class Meta:
        verbose_name = _("Ligne de facture Client")
        verbose_name_plural = _("Lignes de factures Client")

    def __str__(self):
        return f"{self.facture_client} - {self.article}"


@receiver([post_save, post_delete], sender=FactureClientLine)
def _recalc_facture_client_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("facture_client")
    handler(sender, instance, **kwargs)
