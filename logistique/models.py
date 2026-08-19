from datetime import timedelta
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
    """Supplier-side logistics order created from one accepted client proforma."""

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

    GLOBAL_STATUS_CHOICES = [
        ("Brouillon", _("Brouillon")),
        ("À lancer", _("À lancer")),
        ("En cours", _("En cours")),
        ("En attente externe", _("En attente externe")),
        ("Bloqué", _("Bloqué")),
        ("En retard", _("En retard")),
        ("À clôturer", _("À clôturer")),
        ("Clôturé", _("Clôturé")),
        ("Annulé", _("Annulé")),
        ("Rouvert", _("Rouvert")),
    ]

    LAUNCH_STATUS_CHOICES = [
        ("À lancer", _("À lancer")),
        ("En cours", _("En cours")),
        ("En attente proforma", _("En attente proforma")),
        ("Bloquée", _("Bloquée")),
        ("Terminée", _("Terminée")),
    ]

    PROFORMA_STATUS_CHOICES = [
        ("En attente", _("En attente")),
        ("En contrôle", _("En contrôle")),
        ("Correction demandée", _("Correction demandée")),
        ("Validée", _("Validée")),
        ("Refusée", _("Refusée")),
    ]

    LEGACY_PROFORMA_COMPLETE_STATUSES = {
        "Titre d'Importation",
        "Validation",
        "Paiement demandé",
        "Paiement effectué",
        "SWIFT / Draft LC",
        "Envoi SWIFT / Draft LC",
        "Production",
        "Expédition",
        "Documents originaux",
        "Transit",
        "Dédouanement",
        "Réception locale",
        "Livraison client",
        "Clôture",
    }

    PAYMENT_COMPLETE_REQUIRED_STATUSES = {
        "Production",
        "Expédition",
        "Documents originaux",
        "Transit",
        "Dédouanement",
        "Réception locale",
        "Livraison client",
        "Clôture",
    }

    LEGACY_PAYMENT_COMPLETE_STATUSES = {
        "Paiement effectué",
        "SWIFT / Draft LC",
        "Envoi SWIFT / Draft LC",
        *PAYMENT_COMPLETE_REQUIRED_STATUSES,
    }

    TI_STATUT_CHOICES = [
        ("À préparer", _("À préparer")),
        (
            "Titre d'import validé – En attente de paiement",
            _("Titre d'import validé – En attente de paiement"),
        ),
    ]

    BANK_PAYMENT_STATUS_CHOICES = [
        ("À préparer", _("À préparer")),
        ("En validation", _("En validation")),
        ("Banque en cours", _("Banque en cours")),
        ("Exécuté", _("Exécuté")),
        ("Confirmé", _("Confirmé")),
        ("Partiel", _("Partiel")),
        ("Bloqué", _("Bloqué")),
    ]

    ACCOUNTING_PAYMENT_STATUS_CHOICES = [
        ("Paiement à traiter", _("Paiement à traiter")),
        ("Paiement en cours", _("Paiement en cours")),
        (
            "Paiement effectué – Justificatif à joindre",
            _("Paiement effectué – Justificatif à joindre"),
        ),
        ("Paiement validé", _("Paiement validé")),
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
    ]

    EMAIL_DELIVERY_STATUS_CHOICES = [
        ("Non demandé", _("Non demandé")),
        ("Historique non vérifié", _("Historique non vérifié")),
        ("En attente", _("En attente")),
        ("Envoi en cours", _("Envoi en cours")),
        ("Envoyé", _("Envoyé")),
        ("Échec", _("Échec")),
    ]
    EMAIL_DELIVERY_CLAIM_TIMEOUT = timedelta(minutes=10)

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.PROTECT,
        related_name="commandes_logistiques",
        verbose_name=_("Société"),
    )
    numero_commande = models.CharField(
        max_length=24,
        verbose_name=_("Référence dossier logistique"),
    )
    fournisseur = models.CharField(
        max_length=255,
        verbose_name=_("Fournisseur"),
        blank=True,
        default="",
    )
    fournisseur_email = models.EmailField(
        verbose_name=_("E-mail fournisseur"),
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
    statut_global = models.CharField(
        max_length=24,
        choices=GLOBAL_STATUS_CHOICES,
        default="À lancer",
        db_index=True,
        verbose_name=_("Statut global"),
    )
    statut_commande_lancement = models.CharField(
        max_length=24,
        choices=LAUNCH_STATUS_CHOICES,
        default="À lancer",
        db_index=True,
        verbose_name=_("Statut commande et lancement"),
    )
    proforma_demandee_le = models.DateTimeField(null=True, blank=True)
    proforma_demandee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_proforma_logistique_enregistrees",
    )
    prochaine_relance_proforma = models.DateField(null=True, blank=True)
    statut_proforma_conformite = models.CharField(
        max_length=24,
        choices=PROFORMA_STATUS_CHOICES,
        default="En attente",
        db_index=True,
        verbose_name=_("Statut proforma et conformité"),
    )
    numero_proforma_fournisseur = models.CharField(
        max_length=120, blank=True, default=""
    )
    date_proforma_fournisseur = models.DateField(null=True, blank=True)
    montant_proforma_fournisseur = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    devise_proforma_fournisseur = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="MAD"
    )
    delai_proforma_jours = models.PositiveIntegerField(null=True, blank=True)
    ecart_prix_proforma = models.BooleanField(default=False)
    ecart_quantite_proforma = models.BooleanField(default=False)
    notes_ecarts_proforma = models.TextField(blank=True, default="")
    proforma_controlee_le = models.DateTimeField(null=True, blank=True)
    proforma_controlee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proformas_logistique_controlees",
    )
    proforma_validee_le = models.DateTimeField(null=True, blank=True)
    proforma_validee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proformas_logistique_validees",
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
        max_length=64,
        choices=TI_STATUT_CHOICES,
        default="À préparer",
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
    statut_banque_paiement = models.CharField(
        max_length=24,
        choices=BANK_PAYMENT_STATUS_CHOICES,
        default="À préparer",
        db_index=True,
    )
    statut_traitement_paiement = models.CharField(
        max_length=64,
        choices=ACCOUNTING_PAYMENT_STATUS_CHOICES,
        default="Paiement à traiter",
        db_index=True,
    )
    paiement_assigne_a = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paiements_logistique_assignes",
    )
    demande_paiement_envoyee_le = models.DateTimeField(null=True, blank=True)
    demande_paiement_envoyee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demandes_paiement_logistique_envoyees",
    )
    demande_paiement_email_statut = models.CharField(
        max_length=24,
        choices=EMAIL_DELIVERY_STATUS_CHOICES,
        default="Non demandé",
        db_index=True,
    )
    demande_paiement_email_destinataires = models.JSONField(default=list, blank=True)
    demande_paiement_email_erreur = models.TextField(blank=True, default="")
    demande_paiement_email_tentatives = models.PositiveSmallIntegerField(default=0)
    demande_paiement_email_task_id = models.CharField(
        max_length=255, blank=True, default=""
    )
    demande_paiement_email_file_token = models.CharField(
        max_length=32, blank=True, default=""
    )
    demande_paiement_email_mis_en_file_le = models.DateTimeField(
        null=True, blank=True
    )
    demande_paiement_email_prise_en_charge_le = models.DateTimeField(
        null=True, blank=True
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
    devise_paiement = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default="MAD"
    )
    banque_paiement = models.CharField(max_length=255, blank=True, default="")
    reference_paiement = models.CharField(max_length=120, blank=True, default="")
    commentaire_paiement = models.TextField(blank=True, default="")
    date_upload_swift = models.DateTimeField(null=True, blank=True)
    swift_envoye_fournisseur_le = models.DateTimeField(null=True, blank=True)
    paiement_confirme_reception_le = models.DateTimeField(null=True, blank=True)
    paiement_confirme_reception_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paiements_logistique_reception_confirmes",
    )

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
        verbose_name=_("Historique dossier logistique"),
        verbose_name_plural=_("Historiques dossiers logistiques"),
    )

    class Meta:
        verbose_name = _("Dossier logistique")
        verbose_name_plural = _("Dossiers logistiques")
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
    def demande_paiement_email_relance_disponible(self):
        if self.demande_paiement_email_statut in {
            "Échec",
            "Historique non vérifié",
        }:
            return True
        return bool(
            (
                self.demande_paiement_email_statut == "En attente"
                and self.demande_paiement_email_mis_en_file_le
                and self.demande_paiement_email_mis_en_file_le
                <= timezone.now() - self.EMAIL_DELIVERY_CLAIM_TIMEOUT
            )
            or (
                self.demande_paiement_email_statut == "Envoi en cours"
                and self.demande_paiement_email_prise_en_charge_le
                and self.demande_paiement_email_prise_en_charge_le
                <= timezone.now() - self.EMAIL_DELIVERY_CLAIM_TIMEOUT
            )
        )

    @property
    def has_missing_swift(self):
        return self.statut_paiement == "Validé" and not self.swift_file

    @property
    def solde_restant(self):
        paid = sum(
            (
                installment.montant_paye
                for installment in self.echeances_paiement.all()
                if installment.paiement_valide_le
            ),
            Decimal("0"),
        )
        return max(self.montant_titre_importation - paid, Decimal("0"))

    @property
    def is_payment_step_complete(self):
        return self.statut_paiement == "Validé" and (
            self.solde_restant == 0
            or self.statut in self.LEGACY_PAYMENT_COMPLETE_STATUSES
        )

    @property
    def is_delivery_overdue(self):
        return bool(
            self.date_prevue
            and self.date_prevue < timezone.localdate()
            and self.statut not in {"Livraison client", "Clôture", "Annulé"}
            and self.statut_global != "Annulé"
        )

    @property
    def is_proforma_follow_up_overdue(self):
        return bool(
            self.prochaine_relance_proforma
            and self.prochaine_relance_proforma < timezone.localdate()
            and self.effective_proforma_status == "En attente"
            and self.statut_global != "Annulé"
        )

    @property
    def is_launch_step_complete(self):
        return self.statut_commande_lancement == "Terminée"

    @property
    def is_proforma_step_complete(self):
        if (
            self.statut_proforma_conformite in {None, "En attente"}
            and self.statut in self.LEGACY_PROFORMA_COMPLETE_STATUSES
        ):
            return True
        return bool(
            self.statut_proforma_conformite == "Validée"
            and self.proforma_fournisseur_file
            and self.proforma_validee_le
        )

    @property
    def effective_proforma_status(self):
        if self.is_proforma_step_complete:
            return "Validée"
        return self.statut_proforma_conformite or "En attente"

    def calculate_global_status(self, *, preserve_manual=True):
        if self.statut_global == "Annulé":
            return "Annulé"
        if preserve_manual and self.statut_global == "Rouvert":
            return "Rouvert"
        if self.statut == "Clôture":
            return "Clôturé"
        if self.statut == "Livraison client":
            return "À clôturer"

        proforma_status = self.effective_proforma_status
        if (
            self.statut_commande_lancement == "Bloquée"
            or proforma_status == "Refusée"
            or self.statut_banque_paiement == "Bloqué"
        ):
            return "Bloqué"
        if self.is_delivery_overdue or self.is_proforma_follow_up_overdue:
            return "En retard"
        if self.statut_commande_lancement == "À lancer":
            return "À lancer"
        if self.statut_commande_lancement == "En cours":
            return "En cours"
        if self.statut_commande_lancement == "En attente proforma":
            return "En attente externe"
        if not self.is_launch_step_complete:
            return "À lancer"
        if proforma_status in {"En attente", "Correction demandée"}:
            return "En attente externe"
        if proforma_status == "En contrôle":
            return "En cours"
        if self.statut_paiement == "En attente":
            return "En attente externe"
        if self.statut in {"Production", "Documents originaux"}:
            return "En attente externe"
        return "En cours"

    def sync_global_status(self, *, preserve_manual=True, commit=True):
        calculated_status = self.calculate_global_status(
            preserve_manual=preserve_manual
        )
        if calculated_status != self.statut_global:
            self.statut_global = calculated_status
            if commit:
                self.save(update_fields=["statut_global", "date_updated"])
        return calculated_status

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


class LogisticsPaymentInstallment(models.Model):
    commande = models.ForeignKey(
        LogisticsOrder,
        on_delete=models.CASCADE,
        related_name="echeances_paiement",
    )
    date_echeance = models.DateField()
    montant_prevu = models.DecimalField(max_digits=12, decimal_places=2)
    devise = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    statut_traitement = models.CharField(
        max_length=64,
        choices=LogisticsOrder.ACCOUNTING_PAYMENT_STATUS_CHOICES,
        default="Paiement à traiter",
        db_index=True,
    )
    date_paiement = models.DateField(null=True, blank=True)
    montant_paye = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    banque = models.CharField(max_length=255, blank=True, default="")
    reference_bancaire = models.CharField(max_length=120, blank=True, default="")
    methode_paiement = models.CharField(
        max_length=24,
        choices=LogisticsOrder.PAYMENT_METHOD_CHOICES,
        blank=True,
        default="",
    )
    commentaire = models.TextField(blank=True, default="")
    justificatif_file = models.FileField(
        upload_to=get_logistique_document_path,
        null=True,
        blank=True,
        max_length=1000,
    )
    execution_enregistree_le = models.DateTimeField(null=True, blank=True)
    execution_enregistree_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions_paiement_logistique_enregistrees",
    )
    paiement_valide_le = models.DateTimeField(null=True, blank=True)
    paiement_valide_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="echeances_paiement_logistique_validees",
    )
    preuve_email_statut = models.CharField(
        max_length=24,
        choices=LogisticsOrder.EMAIL_DELIVERY_STATUS_CHOICES,
        default="Non demandé",
        db_index=True,
    )
    preuve_email_destinataire = models.EmailField(blank=True, default="")
    preuve_email_erreur = models.TextField(blank=True, default="")
    preuve_email_tentatives = models.PositiveSmallIntegerField(default=0)
    preuve_email_task_id = models.CharField(max_length=255, blank=True, default="")
    preuve_email_file_token = models.CharField(max_length=32, blank=True, default="")
    preuve_email_mise_en_file_le = models.DateTimeField(null=True, blank=True)
    preuve_email_prise_en_charge_le = models.DateTimeField(null=True, blank=True)
    preuve_email_demandee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preuves_paiement_fournisseur_demandees",
    )
    preuve_envoyee_fournisseur_le = models.DateTimeField(null=True, blank=True)
    reception_confirmee_le = models.DateTimeField(null=True, blank=True)
    reception_confirmee_par = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receptions_paiement_fournisseur_confirmees",
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(
        verbose_name=_("Historique échéance paiement logistique"),
        verbose_name_plural=_("Historiques échéances paiement logistique"),
    )

    class Meta:
        verbose_name = _("Échéance paiement logistique")
        verbose_name_plural = _("Échéances paiement logistique")
        ordering = ("date_echeance", "id")
        indexes = [
            models.Index(fields=["commande", "date_echeance"]),
            models.Index(fields=["commande", "statut_traitement"]),
        ]

    def __str__(self):
        return f"{self.commande} - {self.date_echeance} - {self.montant_prevu} {self.devise}"

    @property
    def preuve_email_relance_disponible(self):
        if self.preuve_email_statut in {"Échec", "Historique non vérifié"}:
            return True
        return bool(
            (
                self.preuve_email_statut == "En attente"
                and self.preuve_email_mise_en_file_le
                and self.preuve_email_mise_en_file_le
                <= timezone.now() - LogisticsOrder.EMAIL_DELIVERY_CLAIM_TIMEOUT
            )
            or (
                self.preuve_email_statut == "Envoi en cours"
                and self.preuve_email_prise_en_charge_le
                and self.preuve_email_prise_en_charge_le
                <= timezone.now() - LogisticsOrder.EMAIL_DELIVERY_CLAIM_TIMEOUT
            )
        )


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
        verbose_name = _("Ligne de dossier logistique")
        verbose_name_plural = _("Lignes de dossiers logistiques")
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
