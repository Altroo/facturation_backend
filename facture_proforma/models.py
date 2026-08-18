from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from account.models import CustomUser
from article.models import Article
from core.models import (
    BaseDeviFactureDocument,
    BaseDeviFactureLine,
    create_line_signal_receiver,
)


class FactureProForma(BaseDeviFactureDocument):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="factures_proforma",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de la facture pro forma"),
    )

    numero_facture = models.CharField(
        max_length=20,
        verbose_name=_("Numéro de la facture pro forma"),
        help_text=_("Format ex: 0001/25"),
    )

    date_facture = models.DateField(
        verbose_name=_("Date de facture"),
        help_text=_("Date d'émission de la facture pro forma"),
        db_index=True,
    )

    date_echeance = models.DateField(
        verbose_name=_("Date d'échéance"),
        help_text=_("Date limite de paiement de la facture pro forma"),
        blank=True,
        null=True,
        db_index=True,
    )

    numero_bon_commande_client = models.CharField(
        max_length=50,
        verbose_name=_("Numéro de bon de commande client"),
        blank=True,
        null=True,
        help_text=_("Numéro du bon de commande client (optionnel)"),
    )

    termes_paiement = models.TextField(
        verbose_name=_("Termes de paiement"),
        blank=True,
        null=True,
        help_text=_("Conditions ou termes de paiement de la facture pro forma"),
    )
    fournisseur = models.CharField(
        max_length=255,
        verbose_name=_("Fournisseur"),
        blank=True,
        default="",
        help_text=_("Fournisseur repris par le dossier logistique"),
    )
    fournisseur_email = models.EmailField(
        verbose_name=_("E-mail fournisseur"),
        blank=True,
        default="",
        help_text=_("Adresse utilisée pour envoyer les justificatifs de paiement"),
    )
    source_devis = models.ForeignKey(
        "devi.Devi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_proformas",
        verbose_name=_("Devis source"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Facture Pro-Forma"),
        verbose_name_plural=_("Historiques Factures Pro-Forma"),
    )

    class Meta:
        verbose_name = _("Facture Pro-Forma")
        verbose_name_plural = _("Factures Pro-Forma")
        ordering = ("-date_created",)
        unique_together = [("numero_facture", "company")]
        indexes = [
            models.Index(fields=["company", "date_facture"]),
            models.Index(fields=["client", "company"]),
        ]

    def __str__(self):
        return self.numero_facture

    def clean(self):
        super().clean()
        self.fournisseur = (self.fournisseur or "").strip()
        self.fournisseur_email = (self.fournisseur_email or "").strip()
        errors = {}
        if self.statut == "Accepté" and not self.fournisseur:
            errors["fournisseur"] = _(
                "Renseignez le fournisseur de la commande client validée."
            )

        if self.pk:
            previous_supplier = (
                type(self).objects.filter(pk=self.pk)
                .values_list("fournisseur", flat=True)
                .first()
                or ""
            ).strip()
            if (
                previous_supplier
                and self.fournisseur != previous_supplier
                and self.logistique_links.exists()
            ):
                errors["fournisseur"] = _(
                    "Le fournisseur ne peut plus être modifié après la création du dossier logistique."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Autopopulate company from client before saving."""
        if self.client_id:
            self.company = self.client.company
        super().save(*args, **kwargs)

    @transaction.atomic()
    def convert_to_facture_client(self, numero_facture, created_by_user: CustomUser):
        """Convert this FactureProForma to a FactureClient.

        This method is wrapped in a transaction to ensure atomicity.
        If any part of the conversion fails, all changes will be rolled back.
        """
        from facture_client.models import FactureClient, FactureClientLine

        # Validate document has lines
        if not self.get_lines().exists():
            raise ValueError(_("Impossible de convertir un document sans lignes"))

        # Validate document is in convertible state
        if self.statut not in ["Envoyé", "Accepté"]:
            raise ValueError(
                _(
                    "Impossible de convertir un document avec le statut '{statut}'"
                ).format(statut=self.statut)
            )
        if self.converted_factures.exists():
            raise ValueError(_("Cette proforma a déjà été convertie en facture."))

        facture_client = FactureClient.objects.create(
            numero_facture=numero_facture,
            company=self.company,
            client=self.client,
            source_proforma=self,
            date_facture=self.date_facture,
            date_echeance=self.date_echeance,
            numero_bon_commande_client=self.numero_bon_commande_client,
            termes_paiement=self.termes_paiement,
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
            FactureClientLine.objects.create(
                facture_client=facture_client,
                article=line.article,
                prix_achat=line.prix_achat,
                devise_prix_achat=line.devise_prix_achat,
                prix_vente=line.prix_vente,
                devise_prix_vente=line.devise_prix_vente,
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
        verbose_name=_("Facture Pro Forma"),
        help_text=_("Facture pro forma associée à cette ligne"),
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name=_("Article"),
        help_text=_("Article associé à cette ligne de facture pro forma"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Facture Pro-Forma"),
        verbose_name_plural=_("Historiques Factures Pro-Forma"),
    )

    class Meta:
        verbose_name = _("Ligne de facture Pro-forma")
        verbose_name_plural = _("Lignes de factures Pro-forma")

    def __str__(self):
        return f"{self.facture_pro_forma} - {self.article}"


@receiver([post_save, post_delete], sender=FactureProFormaLine)
def _recalc_facture_pro_forma_on_line_change(sender, instance, **kwargs):
    """Recalculate parent totals when a line is created/updated/deleted."""
    handler = create_line_signal_receiver("facture_pro_forma")
    handler(sender, instance, **kwargs)
