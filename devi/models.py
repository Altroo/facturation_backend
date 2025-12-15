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
        Compute totals based on related lines and remise.
        - Line remise applies on HT before TVA.
        - Document remise applies on aggregated HT, then TVA is scaled proportionally.
        - Store integer centimes (MAD * 100) in integer fields to preserve two decimals.
        """
        from decimal import Decimal, ROUND_HALF_UP

        raw_total_ht = Decimal("0")
        raw_total_tva = Decimal("0")

        for line in self.lignes.all():
            # use string constructor to avoid float imprecision
            prix_vente = Decimal(str(getattr(line, "prix_vente", 0) or 0))
            qty = Decimal(str(getattr(line, "quantity", 0) or 0))
            line_gross = prix_vente * qty

            remise = Decimal(str(getattr(line, "remise", 0) or 0))
            line_remise_type = getattr(line, "remise_type", "") or ""
            if remise > 0 and line_remise_type == "Pourcentage":
                line_discount = (line_gross * remise) / Decimal("100")
            elif remise > 0 and line_remise_type == "Fixe":
                line_discount = remise
            else:
                line_discount = Decimal("0")

            line_net_ht = max(Decimal("0"), line_gross - line_discount)
            raw_total_ht += line_net_ht

            tva_pct = Decimal(
                str(getattr(getattr(line, "article", None), "tva", 0) or 0)
            )
            raw_total_tva += (line_net_ht * tva_pct) / Decimal("100")

        # raw totals (before document-level remise)
        raw_total_ttc = raw_total_ht + raw_total_tva

        # document-level remise (applied on HT)
        doc_remise = Decimal(str(getattr(self, "remise", 0) or 0))
        doc_remise_type = getattr(self, "remise_type", "") or ""
        if doc_remise > 0 and doc_remise_type == "Pourcentage":
            final_total_ht = raw_total_ht * (Decimal("1") - doc_remise / Decimal("100"))
        elif doc_remise > 0 and doc_remise_type == "Fixe":
            final_total_ht = max(Decimal("0"), raw_total_ht - doc_remise)
        else:
            final_total_ht = raw_total_ht

        # scale TVA proportionally to the HT change
        ratio = (final_total_ht / raw_total_ht) if raw_total_ht > 0 else Decimal("0")
        final_total_tva = raw_total_tva * ratio
        final_total_ttc = final_total_ht + final_total_tva

        # Quantize to cents and store as integer centimes (MAD * 100)
        raw_total_ht_q = raw_total_ht.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        raw_total_tva_q = raw_total_tva.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        raw_total_ttc_q = raw_total_ttc.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        final_total_ttc_q = final_total_ttc.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # store integer centimes
        self.total_ht = int(
            (raw_total_ht_q * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        self.total_tva = int(
            (raw_total_tva_q * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        self.total_ttc = int(
            (raw_total_ttc_q * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        self.total_ttc_apres_remise = int(
            (final_total_ttc_q * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    def save(self, *args, **kwargs) -> None:
        if self.pk is None:
            # First save to get PK
            super().save(*args, **kwargs)
            # Now recalc and persist totals
            self.recalc_totals()
            super().save(
                update_fields=[
                    "total_ht",  # type: ignore[attr-defined]
                    "total_tva",  # type: ignore[attr-defined]
                    "total_ttc",  # type: ignore[attr-defined]
                    "total_ttc_apres_remise",  # type: ignore[attr-defined]
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
