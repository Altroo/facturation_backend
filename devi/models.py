from decimal import Decimal

from django.db import models
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from account.models import CustomUser
from article.models import Article
from client.models import Client
from parameter.models import ModePaiement


class Devi(models.Model):
    STATUT_CHOICES = [
        ("Brouillon", "Brouillon"),
        ("Envoyé", "Envoyé"),
        ("Accepté", "Accepté"),
        ("Refusé", "Refusé"),
        ("Annulé", "Annulé"),
        ("Expiré", "Expiré"),
    ]
    numero_devis = models.CharField(
        max_length=20,
        verbose_name="Numéro du devis",
        unique=True,
        help_text="Format ex: 0001/25",
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Client")
    date_devis = models.DateField(verbose_name="Date du devis", db_index=True)
    numero_demande_prix_client = models.CharField(
        max_length=50,
        verbose_name="Numéro de la demande de prix du client",
        blank=True,
        null=True,
    )
    mode_paiement = models.ForeignKey(
        ModePaiement,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Mode de paiement",
    )
    remarque = models.TextField(verbose_name="Remarque", blank=True, null=True)
    statut = models.CharField(
        max_length=10,
        choices=STATUT_CHOICES,
        default="Brouillon",
        verbose_name="Statut",
    )

    total_ht = models.PositiveIntegerField(
        default=0,
        verbose_name="Total HT",
        help_text="Somme des totaux des lignes avant TVA",
        editable=False,
    )

    total_tva = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TVA",
        help_text="Montant total de la TVA",
        editable=False,
    )

    total_ttc = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TTC",
        help_text="Total toutes taxes comprises (TTC)",
        editable=False,
    )

    REMISE_TYPE_CHOICES = [
        ("", ""),
        ("Pourcentage", "Pourcentage"),
        ("Fixe", "Fixe"),
    ]

    remise_type = models.CharField(
        null=True,
        blank=True,
        max_length=12,
        choices=REMISE_TYPE_CHOICES,
        default="",
        verbose_name="Type de remise",
        help_text="Type de remise appliquée : 'Pourcentage' ou 'Fixe'",
    )

    remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Valeur remise",
        help_text="Valeur de la remise appliquée",
    )

    total_ttc_apres_remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Total TTC après remise",
        help_text="Total TTC après application de la remise",
        editable=False,
    )

    date_created = models.DateTimeField(
        auto_now_add=True, verbose_name="Date de création"
    )
    date_updated = models.DateTimeField(
        auto_now=True, verbose_name="Date de mise à jour"
    )
    created_by_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Créé par l'utilisateur",
    )

    class Meta:
        verbose_name = "Devis"
        verbose_name_plural = "Devis"
        ordering = ("-date_created",)

    def __str__(self):
        return self.numero_devis

    def recalc_totals(self):
        """
        Compute totals in cents based on related lines and remise.
        Uses Decimal for percentage math to avoid rounding surprises.
        """
        total_ht = Decimal(0)
        total_tva = Decimal(0)

        for line in self.lignes.all():
            prix_vente = Decimal(getattr(line, "prix_vente", 0) or 0)
            qty = Decimal(getattr(line, "quantity", 0) or 0)
            line_gross = prix_vente * qty

            # line discount
            remise = Decimal(getattr(line, "remise", 0) or 0)
            if getattr(line, "remise_type", "Pourcentage") == "Pourcentage":
                line_discount = (line_gross * remise) / Decimal(100)
            else:
                line_discount = remise

            line_net_ht = max(Decimal(0), line_gross - line_discount)
            total_ht += line_net_ht

            # VAT rate from article (percentage), fallback to 0
            tva_pct = Decimal(getattr(getattr(line, "article", None), "tva", 0) or 0)
            total_tva += (line_net_ht * tva_pct) / Decimal(100)

        # document-level remise
        doc_remise = Decimal(getattr(self, "remise", 0) or 0)
        if getattr(self, "remise_type", "Pourcentage") == "Pourcentage":
            doc_remise_amount = (total_ht * doc_remise) / Decimal(100)
        else:
            doc_remise_amount = doc_remise

        total_ttc = total_ht + total_tva
        total_ttc_apres_remise = max(Decimal(0), total_ttc - doc_remise_amount)

        # set integer-cent fields
        self.total_ht = int(total_ht)
        self.total_tva = int(total_tva)
        self.total_ttc = int(total_ttc)
        self.total_ttc_apres_remise = int(total_ttc_apres_remise)

    def save(self, *args, **kwargs):
        if self.pk is None:
            # First save to get PK
            super().save(*args, **kwargs)
            # Now recalc and persist totals
            self.recalc_totals()
            super().save(
                update_fields=[
                    "total_ht",
                    "total_tva",
                    "total_ttc",
                    "total_ttc_apres_remise",
                ]
            )
        else:
            # For updates, recalc then save normally
            self.recalc_totals()
            super().save(*args, **kwargs)


class DeviLine(models.Model):
    devis = models.ForeignKey(
        Devi, on_delete=models.CASCADE, related_name="lignes", verbose_name="Devis"
    )
    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, verbose_name="Article"
    )
    prix_achat = models.PositiveIntegerField(
        verbose_name="Prix d'achat",
        help_text="Prix d'achat unitaire (entier positif, ex: en MAD)",
    )
    prix_vente = models.PositiveIntegerField(
        verbose_name="Prix de vente",
        help_text="Prix de vente unitaire (entier positif, ex: en MAD)",
    )
    quantity = models.PositiveIntegerField(
        default=1, verbose_name="Quantité", help_text="Quantité (entier positif)"
    )

    REMISE_TYPE_CHOICES = [
        ("", ""),
        ("Pourcentage", "Pourcentage"),
        ("Fixe", "Fixe"),
    ]

    remise_type = models.CharField(
        null=True,
        blank=True,
        max_length=12,
        choices=REMISE_TYPE_CHOICES,
        default="",
        verbose_name="Type de remise",
        help_text="Type de remise appliquée : 'Pourcentage' ou 'Fixe'",
    )

    remise = models.PositiveIntegerField(
        default=0,
        verbose_name="Valeur remise",
        help_text="Valeur après application de la remise",
    )

    class Meta:
        verbose_name = "Ligne de devis"
        verbose_name_plural = "Lignes de devis"

    def __str__(self):
        return f"{self.devis} - {self.article}"


@receiver([post_save, post_delete], sender=DeviLine)
def _recalc_devi_on_line_change(sender, instance, **kwargs):
    """Recalculate parent devi totals when a line is created/updated/deleted."""
    devi = instance.devis
    if devi.pk:
        with transaction.atomic():
            devi.recalc_totals()
            devi.save(
                update_fields=[
                    "total_ht",
                    "total_tva",
                    "total_ttc",
                    "total_ttc_apres_remise",
                ]
            )
