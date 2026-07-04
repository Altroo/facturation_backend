from decimal import Decimal
from os import path
from uuid import uuid4

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from account.models import CustomUser
from core.constants import CURRENCY_CHOICES


def get_logistique_document_path(_, filename):
    _, ext = path.splitext(filename)
    return path.join("logistique_documents", f"{uuid4()}{ext}")


class LogisticsOrder(models.Model):
    """Supplier-side logistics order created from one or more proformas."""

    STATUT_CHOICES = [
        ("Réception commande", _("Réception commande")),
        ("Commande fournisseur", _("Commande fournisseur")),
        ("Proforma", _("Proforma")),
        ("Titre d'Importation", _("Titre d'Importation")),
        ("Validation", _("Validation")),
        ("Paiement demandé", _("Paiement demandé")),
        ("Paiement effectué", _("Paiement effectué")),
        ("SWIFT / Draft LC", _("SWIFT / Draft LC")),
        ("Envoi SWIFT / Draft LC", _("Envoi SWIFT / Draft LC")),
        ("Production", _("Production")),
        ("Expédition", _("Expédition")),
        ("Documents originaux", _("Documents originaux")),
        ("Transit", _("Transit")),
        ("Dédouanement", _("Dédouanement")),
        ("Réception locale", _("Réception locale")),
        ("Livraison client", _("Livraison client")),
        ("Clôture", _("Clôture")),
        ("Annulé", _("Annulé")),
    ]

    TI_STATUT_CHOICES = [
        ("À ouvrir", _("À ouvrir")),
        ("Déposé", _("Déposé")),
        ("En attente", _("En attente")),
        ("Validé", _("Validé")),
        ("Refusé", _("Refusé")),
        ("Expiré", _("Expiré")),
        ("Clôturé", _("Clôturé")),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("LC", _("LC")),
        ("Virement", _("Virement")),
        ("Remise documentaire", _("Remise documentaire")),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("Non demandé", _("Non demandé")),
        ("En attente", _("En attente")),
        ("Validé", _("Validé")),
        ("Rejeté", _("Rejeté")),
    ]

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="commandes_logistiques",
        verbose_name=_("Société"),
    )
    numero_commande = models.CharField(
        max_length=24,
        verbose_name=_("Numéro commande logistique"),
    )
    fournisseur = models.CharField(
        max_length=255,
        verbose_name=_("Fournisseur"),
        blank=True,
        default="",
    )
    marque = models.ForeignKey(
        "parameter.Marque",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_logistiques",
        verbose_name=_("Marque"),
    )
    devise = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default="MAD",
        verbose_name=_("Devise"),
        db_index=True,
    )
    incoterm = models.CharField(max_length=50, blank=True, default="")
    transport = models.CharField(max_length=100, blank=True, default="")
    conditions_paiement = models.TextField(blank=True, default="")
    responsable = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_logistiques_responsable",
        verbose_name=_("Responsable logistique"),
    )
    date_prevue = models.DateField(null=True, blank=True, db_index=True)
    date_reelle = models.DateField(null=True, blank=True, db_index=True)
    statut = models.CharField(
        max_length=32,
        choices=STATUT_CHOICES,
        default="Réception commande",
        db_index=True,
    )
    poids_net = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    poids_brut = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    volume = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    origine_marchandise = models.CharField(max_length=255, blank=True, default="")
    nature_marchandise = models.CharField(max_length=255, blank=True, default="")

    numero_domiciliation = models.CharField(max_length=100, blank=True, default="")
    banque = models.CharField(max_length=255, blank=True, default="")
    montant_titre_importation = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    devise_titre_importation = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="MAD"
    )
    date_titre_importation = models.DateField(null=True, blank=True)
    date_validation_titre_importation = models.DateField(null=True, blank=True)
    statut_titre_importation = models.CharField(
        max_length=16,
        choices=TI_STATUT_CHOICES,
        default="À ouvrir",
        db_index=True,
    )

    methode_paiement = models.CharField(
        max_length=24,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default="",
    )
    statut_paiement = models.CharField(
        max_length=16,
        choices=PAYMENT_STATUS_CHOICES,
        default="Non demandé",
        db_index=True,
    )
    demande_paiement_envoyee_le = models.DateTimeField(null=True, blank=True)
    demande_paiement_envoyee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_paiement_logistique_envoyees",
    )
    paiement_valide_le = models.DateTimeField(null=True, blank=True)
    paiement_valide_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paiements_logistique_valides",
    )
    date_paiement = models.DateField(null=True, blank=True)
    montant_paiement = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference_paiement = models.CharField(max_length=120, blank=True, default="")
    date_upload_swift = models.DateTimeField(null=True, blank=True)
    swift_envoye_fournisseur_le = models.DateTimeField(null=True, blank=True)

    cout_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cout_transport = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_transit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frais_douane = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    livraison_locale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    autres_frais = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cout_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    titre_importation_file = models.FileField(
        upload_to=get_logistique_document_path, null=True, blank=True, max_length=1000
    )
    proforma_fournisseur_file = models.FileField(
        upload_to=get_logistique_document_path, null=True, blank=True, max_length=1000
    )
    justificatifs_file = models.FileField(
        upload_to=get_logistique_document_path, null=True, blank=True, max_length=1000
    )
    swift_file = models.FileField(
        upload_to=get_logistique_document_path, null=True, blank=True, max_length=1000
    )
    documents_originaux_file = models.FileField(
        upload_to=get_logistique_document_path, null=True, blank=True, max_length=1000
    )

    proformas = models.ManyToManyField(
        "facture_proforma.FactureProForma",
        through="LogisticsOrderProforma",
        related_name="commandes_logistiques",
        blank=True,
    )
    created_by_user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commandes_logistiques_creees",
    )
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(
        verbose_name=_("Historique Commande Logistique"),
        verbose_name_plural=_("Historiques Commandes Logistiques"),
    )

    class Meta:
        verbose_name = _("Commande logistique")
        verbose_name_plural = _("Commandes logistiques")
        ordering = ("-date_created",)
        constraints = [
            models.UniqueConstraint(
                fields=["company", "numero_commande"],
                name="unique_logistics_order_number_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "statut"]),
            models.Index(fields=["company", "marque"]),
            models.Index(fields=["company", "statut_paiement"]),
        ]

    def __str__(self):
        return self.numero_commande

    @property
    def is_payment_overdue(self):
        return self.statut_paiement == "En attente" and self.demande_paiement_envoyee_le

    @property
    def has_missing_swift(self):
        return self.statut_paiement == "Validé" and not self.swift_file

    @property
    def is_delivery_overdue(self):
        return bool(
            self.date_prevue
            and self.date_prevue < timezone.localdate()
            and self.statut not in {"Livraison client", "Clôture", "Annulé"}
        )

    def recalc_costs(self):
        lines_total = sum(
            (line.total_achat for line in self.lignes.all()), Decimal("0")
        )
        self.cout_achat = lines_total
        self.cout_total = (
            self.cout_achat
            + self.cout_transport
            + self.frais_transit
            + self.frais_douane
            + self.tva
            + self.livraison_locale
            + self.autres_frais
        )

    def save(self, *args, **kwargs):
        cost_fields = {
            "cout_transport",
            "frais_transit",
            "frais_douane",
            "tva",
            "livraison_locale",
            "autres_frais",
        }
        update_fields = kwargs.get("update_fields")
        if self.pk and (update_fields is None or cost_fields & set(update_fields)):
            self.recalc_costs()
            if update_fields is not None:
                kwargs["update_fields"] = list(
                    set(update_fields) | {"cout_achat", "cout_total"}
                )
        super().save(*args, **kwargs)

    def add_event(self, *, user=None, action, old_value="", new_value="", note=""):
        return LogisticsOrderEvent.objects.create(
            commande=self,
            user=user,
            action=action,
            old_value=old_value or "",
            new_value=new_value or "",
            note=note or "",
        )

    @transaction.atomic
    def set_status(self, new_status, *, user=None):
        old_status = self.statut
        self.statut = new_status
        self.save(update_fields=["statut", "date_updated"])
        if old_status != new_status:
            self.add_event(
                user=user,
                action="Changement de statut",
                old_value=old_status,
                new_value=new_status,
            )
        return self


class LogisticsOrderProforma(models.Model):
    commande = models.ForeignKey(
        LogisticsOrder,
        on_delete=models.CASCADE,
        related_name="commande_proformas",
    )
    proforma = models.ForeignKey(
        "facture_proforma.FactureProForma",
        on_delete=models.PROTECT,
        related_name="logistique_links",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("commande", "proforma")]

    def __str__(self):
        return f"{self.commande} - {self.proforma}"


class LogisticsOrderLine(models.Model):
    commande = models.ForeignKey(
        LogisticsOrder,
        on_delete=models.CASCADE,
        related_name="lignes",
    )
    proforma = models.ForeignKey(
        "facture_proforma.FactureProForma",
        on_delete=models.PROTECT,
        related_name="lignes_logistiques",
    )
    source_line = models.ForeignKey(
        "facture_proforma.FactureProFormaLine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lignes_logistiques",
    )
    client = models.ForeignKey(
        "client.Client",
        on_delete=models.PROTECT,
        related_name="lignes_logistiques",
    )
    article = models.ForeignKey(
        "article.Article",
        on_delete=models.PROTECT,
        related_name="lignes_logistiques",
    )
    article_reference = models.CharField(max_length=100, blank=True, default="")
    designation = models.TextField(blank=True, default="")
    marque_name = models.CharField(max_length=255, blank=True, default="")
    project_reference = models.CharField(max_length=100, blank=True, default="")
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    prix_achat = models.DecimalField(max_digits=10, decimal_places=2)
    devise_prix_achat = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="MAD"
    )
    prix_vente = models.DecimalField(max_digits=10, decimal_places=2)
    devise_prix_vente = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="MAD"
    )
    total_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("Ligne commande logistique")
        verbose_name_plural = _("Lignes commandes logistiques")
        indexes = [
            models.Index(fields=["commande", "proforma"]),
            models.Index(fields=["article"]),
        ]

    def save(self, *args, **kwargs):
        self.total_achat = (self.prix_achat or Decimal("0")) * (
            self.quantity or Decimal("0")
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.commande} - {self.article_reference}"


class LogisticsOrderEvent(models.Model):
    commande = models.ForeignKey(
        LogisticsOrder,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evenements_logistiques",
    )
    action = models.CharField(max_length=120)
    old_value = models.CharField(max_length=255, blank=True, default="")
    new_value = models.CharField(max_length=255, blank=True, default="")
    note = models.TextField(blank=True, default="")
    date_created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Événement logistique")
        verbose_name_plural = _("Événements logistiques")
        ordering = ("-date_created",)

    def __str__(self):
        return f"{self.commande} - {self.action}"
