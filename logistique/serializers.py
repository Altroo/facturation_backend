from decimal import Decimal
from pathlib import Path

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from account.models import Membership
from .models import (
    LogisticsOrder,
    LogisticsOrderEvent,
    LogisticsOrderLine,
    LogisticsPaymentInstallment,
)


ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
}
ALLOWED_DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
}
MAX_DOCUMENT_FILE_SIZE = 10 * 1024 * 1024

LOGISTICS_IMPORT_TITLE_FIELDS = frozenset(
    {
        "numero_domiciliation",
        "banque",
        "montant_titre_importation",
        "devise_titre_importation",
        "date_titre_importation",
        "date_validation_titre_importation",
        "statut_titre_importation",
        "titre_importation_file",
        "methode_paiement",
    }
)


def validate_logistics_document(file_obj):
    if file_obj.size > MAX_DOCUMENT_FILE_SIZE:
        raise serializers.ValidationError(_("Le fichier ne doit pas dépasser 10 Mo."))
    extension = Path(file_obj.name).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise serializers.ValidationError(_("Format de fichier non autorisé."))
    content_type = getattr(file_obj, "content_type", "")
    if content_type and content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
        raise serializers.ValidationError(_("Type de fichier non autorisé."))
    return file_obj


def _user_display_name(user):
    if not user:
        return None
    return f"{user.first_name} {user.last_name}".strip() or user.email


class LogisticsOrderLineSerializer(serializers.ModelSerializer):
    proforma_numero = serializers.CharField(
        source="proforma.numero_facture", read_only=True
    )
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsOrderLine
        fields = [
            "id",
            "proforma",
            "proforma_numero",
            "client",
            "client_name",
            "article",
            "article_reference",
            "designation",
            "marque_name",
            "project_reference",
            "quantity",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "devise_prix_vente",
            "total_achat",
        ]
        read_only_fields = fields

    @staticmethod
    def get_client_name(obj):
        return str(obj.client) if obj.client else None


class LogisticsOrderEventSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsOrderEvent
        fields = [
            "id",
            "action",
            "old_value",
            "new_value",
            "note",
            "user",
            "user_name",
            "date_created",
        ]
        read_only_fields = fields

    @staticmethod
    def get_user_name(obj):
        return _user_display_name(obj.user)


class LogisticsPaymentInstallmentSerializer(serializers.ModelSerializer):
    execution_enregistree_par_name = serializers.SerializerMethodField()
    paiement_valide_par_name = serializers.SerializerMethodField()
    reception_confirmee_par_name = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsPaymentInstallment
        fields = [
            "id",
            "date_echeance",
            "montant_prevu",
            "devise",
            "statut_traitement",
            "date_paiement",
            "montant_paye",
            "banque",
            "reference_bancaire",
            "methode_paiement",
            "commentaire",
            "justificatif_file",
            "execution_enregistree_le",
            "execution_enregistree_par",
            "execution_enregistree_par_name",
            "paiement_valide_le",
            "paiement_valide_par",
            "paiement_valide_par_name",
            "preuve_email_statut",
            "preuve_email_destinataire",
            "preuve_email_erreur",
            "preuve_email_tentatives",
            "preuve_email_relance_disponible",
            "preuve_email_demandee_par",
            "preuve_envoyee_fournisseur_le",
            "reception_confirmee_le",
            "reception_confirmee_par",
            "reception_confirmee_par_name",
        ]
        read_only_fields = fields

    @staticmethod
    def get_execution_enregistree_par_name(obj):
        return _user_display_name(obj.execution_enregistree_par)

    @staticmethod
    def get_paiement_valide_par_name(obj):
        return _user_display_name(obj.paiement_valide_par)

    @staticmethod
    def get_reception_confirmee_par_name(obj):
        return _user_display_name(obj.reception_confirmee_par)


class LogisticsOrderBaseSerializer(serializers.ModelSerializer):
    marque_name = serializers.CharField(source="marque.nom", read_only=True)
    responsable_name = serializers.SerializerMethodField()
    demande_paiement_envoyee_par_name = serializers.SerializerMethodField()
    proforma_demandee_par_name = serializers.SerializerMethodField()
    proforma_controlee_par_name = serializers.SerializerMethodField()
    proforma_validee_par_name = serializers.SerializerMethodField()
    paiement_valide_par_name = serializers.SerializerMethodField()
    paiement_assigne_a_name = serializers.SerializerMethodField()
    created_by_user_name = serializers.SerializerMethodField()
    proformas_count = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()
    clients_display = serializers.SerializerMethodField()
    projects_display = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()
    is_launch_step_complete = serializers.BooleanField(read_only=True)
    is_proforma_step_complete = serializers.BooleanField(read_only=True)
    statut_global = serializers.SerializerMethodField()
    statut_proforma_conformite = serializers.SerializerMethodField()
    solde_restant = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = LogisticsOrder
        fields = [
            "id",
            "company",
            "numero_commande",
            "fournisseur",
            "fournisseur_email",
            "marque",
            "marque_name",
            "devise",
            "incoterm",
            "transport",
            "conditions_paiement",
            "responsable",
            "responsable_name",
            "date_prevue",
            "date_reelle",
            "statut",
            "statut_global",
            "statut_commande_lancement",
            "proforma_demandee_le",
            "proforma_demandee_par",
            "proforma_demandee_par_name",
            "prochaine_relance_proforma",
            "is_launch_step_complete",
            "statut_proforma_conformite",
            "numero_proforma_fournisseur",
            "date_proforma_fournisseur",
            "montant_proforma_fournisseur",
            "devise_proforma_fournisseur",
            "delai_proforma_jours",
            "ecart_prix_proforma",
            "ecart_quantite_proforma",
            "notes_ecarts_proforma",
            "proforma_controlee_le",
            "proforma_controlee_par",
            "proforma_controlee_par_name",
            "proforma_validee_le",
            "proforma_validee_par",
            "proforma_validee_par_name",
            "is_proforma_step_complete",
            "poids_net",
            "poids_brut",
            "volume",
            "origine_marchandise",
            "nature_marchandise",
            "numero_domiciliation",
            "banque",
            "montant_titre_importation",
            "devise_titre_importation",
            "date_titre_importation",
            "date_validation_titre_importation",
            "statut_titre_importation",
            "methode_paiement",
            "statut_paiement",
            "statut_banque_paiement",
            "statut_traitement_paiement",
            "paiement_assigne_a",
            "paiement_assigne_a_name",
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "demande_paiement_envoyee_par_name",
            "demande_paiement_email_statut",
            "demande_paiement_email_destinataires",
            "demande_paiement_email_erreur",
            "demande_paiement_email_tentatives",
            "demande_paiement_email_relance_disponible",
            "paiement_valide_le",
            "paiement_valide_par",
            "paiement_valide_par_name",
            "date_paiement",
            "montant_paiement",
            "devise_paiement",
            "banque_paiement",
            "reference_paiement",
            "commentaire_paiement",
            "date_upload_swift",
            "swift_envoye_fournisseur_le",
            "paiement_confirme_reception_le",
            "paiement_confirme_reception_par",
            "solde_restant",
            "cout_achat",
            "cout_transport",
            "frais_transit",
            "frais_douane",
            "tva",
            "livraison_locale",
            "autres_frais",
            "cout_total",
            "titre_importation_file",
            "proforma_fournisseur_file",
            "justificatifs_file",
            "swift_file",
            "documents_originaux_file",
            "created_by_user",
            "created_by_user_name",
            "date_created",
            "date_updated",
            "proformas_count",
            "lignes_count",
            "clients_display",
            "projects_display",
            "alerts",
        ]
        read_only_fields = [
            "id",
            "company",
            "numero_commande",
            "fournisseur",
            "fournisseur_email",
            "marque_name",
            "responsable_name",
            "statut_global",
            "statut_commande_lancement",
            "proforma_demandee_le",
            "proforma_demandee_par",
            "proforma_demandee_par_name",
            "prochaine_relance_proforma",
            "is_launch_step_complete",
            "statut_proforma_conformite",
            "numero_proforma_fournisseur",
            "date_proforma_fournisseur",
            "montant_proforma_fournisseur",
            "devise_proforma_fournisseur",
            "delai_proforma_jours",
            "ecart_prix_proforma",
            "ecart_quantite_proforma",
            "notes_ecarts_proforma",
            "proforma_controlee_le",
            "proforma_controlee_par",
            "proforma_controlee_par_name",
            "proforma_validee_le",
            "proforma_validee_par",
            "proforma_validee_par_name",
            "is_proforma_step_complete",
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "demande_paiement_envoyee_par_name",
            "demande_paiement_email_statut",
            "demande_paiement_email_destinataires",
            "demande_paiement_email_erreur",
            "demande_paiement_email_tentatives",
            "demande_paiement_email_relance_disponible",
            "paiement_valide_le",
            "paiement_valide_par",
            "paiement_valide_par_name",
            "date_upload_swift",
            "swift_envoye_fournisseur_le",
            "cout_achat",
            "cout_total",
            "created_by_user",
            "created_by_user_name",
            "date_created",
            "date_updated",
            "proformas_count",
            "lignes_count",
            "clients_display",
            "projects_display",
            "alerts",
        ]

    @staticmethod
    def get_responsable_name(obj):
        return _user_display_name(obj.responsable)

    @staticmethod
    def get_demande_paiement_envoyee_par_name(obj):
        return _user_display_name(obj.demande_paiement_envoyee_par)

    @staticmethod
    def get_proforma_demandee_par_name(obj):
        return _user_display_name(obj.proforma_demandee_par)

    @staticmethod
    def get_proforma_controlee_par_name(obj):
        return _user_display_name(obj.proforma_controlee_par)

    @staticmethod
    def get_proforma_validee_par_name(obj):
        return _user_display_name(obj.proforma_validee_par)

    @staticmethod
    def get_statut_proforma_conformite(obj):
        return obj.effective_proforma_status

    @staticmethod
    def get_statut_global(obj):
        return obj.calculate_global_status()

    @staticmethod
    def get_paiement_valide_par_name(obj):
        return _user_display_name(obj.paiement_valide_par)

    @staticmethod
    def get_paiement_assigne_a_name(obj):
        return _user_display_name(obj.paiement_assigne_a)

    @staticmethod
    def get_created_by_user_name(obj):
        return _user_display_name(obj.created_by_user)

    @staticmethod
    def get_proformas_count(obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("proformas")
        if prefetched is not None:
            return len(prefetched)
        return obj.proformas.count()

    @staticmethod
    def get_lignes_count(obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("lignes")
        if prefetched is not None:
            return len(prefetched)
        return obj.lignes.count()

    @staticmethod
    def get_clients_display(obj):
        lines = getattr(obj, "_prefetched_objects_cache", {}).get("lignes")
        if lines is None:
            lines = obj.lignes.select_related("client").all()
        names = []
        seen = set()
        for line in lines:
            name = str(line.client)
            if name not in seen:
                names.append(name)
                seen.add(name)
        return ", ".join(names)

    @staticmethod
    def get_projects_display(obj):
        lines = getattr(obj, "_prefetched_objects_cache", {}).get("lignes")
        if lines is None:
            lines = obj.lignes.all()
        refs = []
        seen = set()
        for line in lines:
            ref = (line.project_reference or "").strip()
            if ref and ref not in seen:
                refs.append(ref)
                seen.add(ref)
        return ", ".join(refs)

    @staticmethod
    def get_alerts(obj):
        alerts = []
        if obj.statut_paiement == "En attente":
            alerts.append("Retard paiement en attente")
        if obj.has_missing_swift:
            alerts.append("SWIFT manquant")
        if (
            obj.statut in {"Documents originaux", "Transit"}
            and not obj.documents_originaux_file
        ):
            alerts.append("Documents non reçus")
        if obj.statut in {"Expédition", "Documents originaux"}:
            alerts.append("Transit non lancé")
        if obj.is_delivery_overdue:
            alerts.append("Livraison dépassée")
        return alerts


class LogisticsOrderListSerializer(LogisticsOrderBaseSerializer):
    class Meta(LogisticsOrderBaseSerializer.Meta):
        fields = [
            "id",
            "company",
            "numero_commande",
            "fournisseur",
            "marque",
            "marque_name",
            "devise",
            "transport",
            "date_prevue",
            "date_reelle",
            "statut",
            "statut_global",
            "statut_commande_lancement",
            "proforma_demandee_le",
            "prochaine_relance_proforma",
            "is_launch_step_complete",
            "statut_proforma_conformite",
            "is_proforma_step_complete",
            "statut_paiement",
            "statut_banque_paiement",
            "statut_traitement_paiement",
            "solde_restant",
            "methode_paiement",
            "responsable",
            "responsable_name",
            "cout_total",
            "created_by_user_name",
            "date_created",
            "date_updated",
            "proformas_count",
            "lignes_count",
            "clients_display",
            "projects_display",
            "alerts",
        ]
        read_only_fields = fields


class LogisticsOrderDetailSerializer(LogisticsOrderBaseSerializer):
    lignes = LogisticsOrderLineSerializer(many=True, read_only=True)
    events = LogisticsOrderEventSerializer(many=True, read_only=True)
    proformas_detail = serializers.SerializerMethodField()
    echeancier_paiement = LogisticsPaymentInstallmentSerializer(
        source="echeances_paiement", many=True, read_only=True
    )

    class Meta(LogisticsOrderBaseSerializer.Meta):
        fields = LogisticsOrderBaseSerializer.Meta.fields + [
            "lignes",
            "events",
            "proformas_detail",
            "echeancier_paiement",
        ]
        read_only_fields = LogisticsOrderBaseSerializer.Meta.read_only_fields + [
            "lignes",
            "events",
            "proformas_detail",
            "echeancier_paiement",
        ]

    @staticmethod
    def get_proformas_detail(obj):
        return [
            {
                "id": proforma.id,
                "numero_facture": proforma.numero_facture,
                "client_name": str(proforma.client) if proforma.client else None,
                "fournisseur": proforma.fournisseur,
                "fournisseur_email": proforma.fournisseur_email,
                "project_reference": proforma.numero_bon_commande_client or "",
                "date_facture": proforma.date_facture,
                "total_ttc_apres_remise": proforma.total_ttc_apres_remise,
                "devise": proforma.devise,
            }
            for proforma in obj.proformas.all()
        ]


class LogisticsOrderCreateSerializer(serializers.Serializer):
    proformas = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=1,
    )
    date_prevue = serializers.DateField(required=True)
    date_reelle = serializers.DateField(required=False, allow_null=True)
    origine_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    nature_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    responsable = serializers.IntegerField(required=True, allow_null=False, min_value=1)

    def validate(self, attrs):
        responsable = attrs.get("responsable")
        company_id = self.context.get("company_id")
        if (
            responsable is not None
            and not Membership.objects.filter(
                user_id=responsable,
                company_id=company_id,
                user__is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError(
                {"responsable": _("Ce responsable n'appartient pas à cette société.")}
            )

        return attrs


class LogisticsOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogisticsOrder
        fields = [
            "transport",
            "statut",
            "responsable",
            "date_prevue",
            "date_reelle",
            "poids_net",
            "poids_brut",
            "volume",
            "origine_marchandise",
            "nature_marchandise",
            "numero_domiciliation",
            "banque",
            "montant_titre_importation",
            "devise_titre_importation",
            "date_titre_importation",
            "date_validation_titre_importation",
            "statut_titre_importation",
            "methode_paiement",
            "date_paiement",
            "montant_paiement",
            "devise_paiement",
            "banque_paiement",
            "reference_paiement",
            "commentaire_paiement",
            "cout_transport",
            "frais_transit",
            "frais_douane",
            "tva",
            "livraison_locale",
            "autres_frais",
            "titre_importation_file",
            "justificatifs_file",
            "swift_file",
            "documents_originaux_file",
        ]

    def validate_responsable(self, value):
        if (
            value
            and not Membership.objects.filter(
                user=value,
                company_id=self.instance.company_id,
                user__is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError(
                _("Ce responsable n'appartient pas à cette société.")
            )
        return value

    def validate_titre_importation_file(self, value):
        return validate_logistics_document(value)

    def validate_justificatifs_file(self, value):
        return validate_logistics_document(value)

    def validate_documents_originaux_file(self, value):
        return validate_logistics_document(value)

    def validate_statut(self, value):
        if value == "Annulé":
            raise serializers.ValidationError(
                _("Utilisez l'action dédiée pour annuler ce dossier.")
            )
        if (
            value in LogisticsOrder.LEGACY_PROFORMA_COMPLETE_STATUSES
            and not self.instance.is_proforma_step_complete
        ):
            raise serializers.ValidationError(
                _("Validez d'abord la proforma fournisseur.")
            )
        if (
            value in LogisticsOrder.PAYMENT_COMPLETE_REQUIRED_STATUSES
            and not self.instance.is_payment_step_complete
        ):
            raise serializers.ValidationError(
                _("Validez d'abord la totalité du paiement requis.")
            )
        return value

    def validate(self, attrs):
        part_two_message = _(
            "Utilisez l'étape Proforma & conformité pour modifier ce champ."
        )
        restricted_fields = {
            "marque": _(
                "La marque article n'est pas une donnée modifiable du dossier logistique."
            ),
            "incoterm": part_two_message,
            "conditions_paiement": part_two_message,
            "proforma_fournisseur_file": part_two_message,
            "date_validation_titre_importation": _(
                "Ce champ est calculé lors de la transmission au Service Comptable."
            ),
            "statut_titre_importation": _(
                "Ce statut est géré par l'étape Banque & paiement."
            ),
        }
        payment_fields = {
            "date_paiement",
            "montant_paiement",
            "devise_paiement",
            "banque_paiement",
            "reference_paiement",
            "commentaire_paiement",
            "swift_file",
        }
        if self.instance.statut_paiement != "Non demandé":
            restricted_fields.update(
                {
                    field: _(
                        "Le titre d'importation est verrouillé après sa transmission au Service Comptable."
                    )
                    for field in LOGISTICS_IMPORT_TITLE_FIELDS
                }
            )
        restricted_fields.update(
            {
                field: _(
                    "Utilisez l'action de validation du paiement pour modifier ce champ."
                )
                for field in payment_fields
            }
        )
        errors = {
            field: message
            for field, message in restricted_fields.items()
            if field in self.initial_data
        }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def update(self, instance, validated_data):
        old_status = instance.statut
        old_swift = bool(instance.swift_file)
        instance = super().update(instance, validated_data)
        if old_status != instance.statut:
            request = self.context.get("request")
            instance.add_event(
                user=getattr(request, "user", None),
                action="Changement de statut",
                old_value=old_status,
                new_value=instance.statut,
            )
        if not old_swift and instance.swift_file:
            instance.date_upload_swift = (
                instance.date_upload_swift or instance.date_updated
            )
            instance.save(update_fields=["date_upload_swift", "date_updated"])
            request = self.context.get("request")
            instance.add_event(
                user=getattr(request, "user", None),
                action="Upload SWIFT",
                new_value="SWIFT joint",
            )
        return instance


class LogisticsStatusSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.STATUT_CHOICES]
    )


class LogisticsGlobalStatusSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.GLOBAL_STATUS_CHOICES]
    )


class LogisticsLaunchStatusSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.LAUNCH_STATUS_CHOICES]
    )


class LogisticsPaymentScheduleItemSerializer(serializers.Serializer):
    date_echeance = serializers.DateField()
    montant_prevu = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    devise = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder._meta.get_field("devise").choices]
    )


class LogisticsPaymentRequestSerializer(serializers.Serializer):
    echeancier = LogisticsPaymentScheduleItemSerializer(many=True, allow_empty=False)

    def validate_echeancier(self, value):
        order = self.context["order"]
        expected_currency = order.devise_titre_importation
        invalid_currencies = {
            item["devise"] for item in value if item["devise"] != expected_currency
        }
        if invalid_currencies:
            raise serializers.ValidationError(
                _("Toutes les échéances doivent utiliser la devise du titre d'importation.")
            )
        total = sum((item["montant_prevu"] for item in value), Decimal("0"))
        if total != order.montant_titre_importation:
            raise serializers.ValidationError(
                _("Le total de l'échéancier doit correspondre au montant du titre d'importation.")
            )
        return value


class LogisticsPaymentInstallmentActionSerializer(serializers.Serializer):
    echeance_id = serializers.IntegerField(min_value=1)


class LogisticsPaymentExecutionSerializer(LogisticsPaymentInstallmentActionSerializer):
    date_paiement = serializers.DateField(required=True, allow_null=False)
    montant_paye = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        min_value=Decimal("0.01"),
    )
    devise_paiement = serializers.ChoiceField(
        choices=[
            choice[0]
            for choice in LogisticsOrder._meta.get_field("devise_paiement").choices
        ]
    )
    banque_paiement = serializers.CharField(required=True, allow_blank=False)
    reference_paiement = serializers.CharField(required=True, allow_blank=False)
    methode_paiement = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.PAYMENT_METHOD_CHOICES],
        required=True,
    )
    commentaire_paiement = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class LogisticsPaymentValidationSerializer(LogisticsPaymentInstallmentActionSerializer):
    swift_file = serializers.FileField(required=True, allow_null=False)

    def validate_swift_file(self, value):
        return validate_logistics_document(value)


class LogisticsPaymentRejectSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class LogisticsProformaRequestSerializer(serializers.Serializer):
    prochaine_relance_proforma = serializers.DateField()

    def validate_prochaine_relance_proforma(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                _("La prochaine relance ne peut pas être antérieure à aujourd'hui.")
            )
        return value


class LogisticsSupplierProformaReviewSerializer(serializers.Serializer):
    ALLOWED_EXTENSIONS = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
    }
    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/jpeg",
        "image/png",
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024

    action = serializers.ChoiceField(
        choices=["control", "request_correction", "validate", "reject"]
    )
    numero_proforma_fournisseur = serializers.CharField(
        required=False, allow_blank=True, max_length=120
    )
    date_proforma_fournisseur = serializers.DateField(required=False, allow_null=True)
    montant_proforma_fournisseur = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
    )
    devise_proforma_fournisseur = serializers.ChoiceField(
        choices=[
            choice[0] for choice in LogisticsOrder._meta.get_field("devise").choices
        ],
        required=False,
    )
    incoterm = serializers.CharField(required=False, allow_blank=True, max_length=50)
    conditions_paiement = serializers.CharField(required=False, allow_blank=True)
    delai_proforma_jours = serializers.IntegerField(required=False, min_value=0)
    ecart_prix_proforma = serializers.BooleanField(required=False)
    ecart_quantite_proforma = serializers.BooleanField(required=False)
    notes_ecarts_proforma = serializers.CharField(required=False, allow_blank=True)
    proforma_fournisseur_file = serializers.FileField(required=False, allow_null=True)

    def validate_proforma_fournisseur_file(self, value):
        if value is None:
            return value
        extension = Path(value.name).suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                _("Format non autorisé. Utilisez PDF, Word, Excel, JPG ou PNG.")
            )
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(_("Type de fichier non autorisé."))
        if value.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                _("Le fichier ne doit pas dépasser 10 Mo.")
            )
        return value

    def validate(self, attrs):
        order = self.context["order"]

        def effective(field):
            return attrs[field] if field in attrs else getattr(order, field)

        required_fields = {
            "numero_proforma_fournisseur": _("Le numéro de proforma est obligatoire."),
            "date_proforma_fournisseur": _("La date de proforma est obligatoire."),
            "montant_proforma_fournisseur": _(
                "Le montant de proforma est obligatoire."
            ),
            "devise_proforma_fournisseur": _("La devise de proforma est obligatoire."),
            "incoterm": _("L'Incoterm est obligatoire."),
            "conditions_paiement": _("Les conditions de paiement sont obligatoires."),
            "delai_proforma_jours": _("Le délai fournisseur est obligatoire."),
            "proforma_fournisseur_file": _(
                "Le fichier de proforma fournisseur est obligatoire."
            ),
        }
        errors = {}
        for field, message in required_fields.items():
            value = effective(field)
            is_missing = value is None or (isinstance(value, str) and not value.strip())
            if field == "proforma_fournisseur_file":
                is_missing = not bool(value)
            elif field == "montant_proforma_fournisseur":
                is_missing = value is None or value <= 0
            if is_missing:
                errors[field] = message

        has_price_variance = bool(effective("ecart_prix_proforma"))
        has_quantity_variance = bool(effective("ecart_quantite_proforma"))
        notes = (effective("notes_ecarts_proforma") or "").strip()
        action = attrs["action"]

        if action == "request_correction":
            if not (has_price_variance or has_quantity_variance):
                errors["variances"] = _(
                    "Signalez au moins un écart de prix ou de quantité."
                )
            if not notes:
                errors["notes_ecarts_proforma"] = _(
                    "Décrivez les écarts avant de demander une correction."
                )
        elif action == "validate" and (has_price_variance or has_quantity_variance):
            errors["variances"] = _(
                "Une proforma comportant des écarts ne peut pas être validée."
            )
        elif action == "reject" and not notes:
            errors["notes_ecarts_proforma"] = _(
                "Indiquez le motif du refus de la proforma."
            )

        if errors:
            raise serializers.ValidationError(errors)
        return attrs
