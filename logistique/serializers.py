from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from account.models import Membership
from parameter.models import Marque

from .models import LogisticsOrder, LogisticsOrderEvent, LogisticsOrderLine


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


class LogisticsOrderBaseSerializer(serializers.ModelSerializer):
    marque_name = serializers.CharField(source="marque.nom", read_only=True)
    responsable_name = serializers.SerializerMethodField()
    demande_paiement_envoyee_par_name = serializers.SerializerMethodField()
    paiement_valide_par_name = serializers.SerializerMethodField()
    created_by_user_name = serializers.SerializerMethodField()
    proformas_count = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()
    clients_display = serializers.SerializerMethodField()
    projects_display = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()

    class Meta:
        model = LogisticsOrder
        fields = [
            "id",
            "company",
            "numero_commande",
            "fournisseur",
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
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "demande_paiement_envoyee_par_name",
            "paiement_valide_le",
            "paiement_valide_par",
            "paiement_valide_par_name",
            "date_paiement",
            "montant_paiement",
            "reference_paiement",
            "date_upload_swift",
            "swift_envoye_fournisseur_le",
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
            "marque_name",
            "responsable_name",
            "demande_paiement_envoyee_le",
            "demande_paiement_envoyee_par",
            "demande_paiement_envoyee_par_name",
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
    def get_paiement_valide_par_name(obj):
        return _user_display_name(obj.paiement_valide_par)

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
            "statut_paiement",
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

    class Meta(LogisticsOrderBaseSerializer.Meta):
        fields = LogisticsOrderBaseSerializer.Meta.fields + [
            "lignes",
            "events",
            "proformas_detail",
        ]
        read_only_fields = LogisticsOrderBaseSerializer.Meta.read_only_fields + [
            "lignes",
            "events",
            "proformas_detail",
        ]

    @staticmethod
    def get_proformas_detail(obj):
        return [
            {
                "id": proforma.id,
                "numero_facture": proforma.numero_facture,
                "client_name": str(proforma.client) if proforma.client else None,
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
    )
    date_prevue = serializers.DateField(required=False)
    date_reelle = serializers.DateField(required=False, allow_null=True)
    origine_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    nature_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    brand_details = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        default=list,
    )

    def validate(self, attrs):
        details = []
        errors = {}
        for index, item in enumerate(attrs.get("brand_details", []) or []):
            detail_errors = {}
            try:
                marque = int(item.get("marque"))
            except (TypeError, ValueError):
                detail_errors["marque"] = _("Marque invalide.")
                marque = None

            normalized = {"marque": marque}
            for field in ("date_prevue", "date_reelle"):
                value = item.get(field)
                if value in (None, ""):
                    normalized[field] = None
                    continue
                field_serializer = serializers.DateField(required=field == "date_prevue")
                try:
                    normalized[field] = field_serializer.to_internal_value(value)
                except serializers.ValidationError:
                    detail_errors[field] = _("Date invalide.")

            for field in ("origine_marchandise", "nature_marchandise"):
                value = item.get(field, "")
                normalized[field] = str(value).strip()
                if not normalized[field]:
                    detail_errors[field] = _("Ce champ est obligatoire.")

            if not normalized.get("date_prevue"):
                detail_errors["date_prevue"] = _("Ce champ est obligatoire.")

            if detail_errors:
                errors[str(index)] = detail_errors
            details.append(normalized)

        if errors:
            raise serializers.ValidationError({"brand_details": errors})

        attrs["brand_details"] = details
        return attrs


class LogisticsOrderUpdateSerializer(serializers.ModelSerializer):
    marque = serializers.PrimaryKeyRelatedField(
        queryset=Marque.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = LogisticsOrder
        fields = [
            "marque",
            "incoterm",
            "transport",
            "conditions_paiement",
            "responsable",
            "date_prevue",
            "date_reelle",
            "statut",
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
            "reference_paiement",
            "cout_transport",
            "frais_transit",
            "frais_douane",
            "tva",
            "livraison_locale",
            "autres_frais",
            "titre_importation_file",
            "proforma_fournisseur_file",
            "justificatifs_file",
            "swift_file",
            "documents_originaux_file",
        ]

    def validate_marque(self, value):
        if value and value.company_id != self.instance.company_id:
            raise serializers.ValidationError(
                _("Cette marque appartient à une autre société.")
            )
        return value

    def validate_responsable(self, value):
        if (
            value
            and not Membership.objects.filter(
                user=value, company_id=self.instance.company_id
            ).exists()
        ):
            raise serializers.ValidationError(
                _("Ce responsable n'appartient pas à cette société.")
            )
        return value

    def validate(self, attrs):
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


class LogisticsPaymentValidationSerializer(serializers.Serializer):
    date_paiement = serializers.DateField(required=False, allow_null=True)
    montant_paiement = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    reference_paiement = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    methode_paiement = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.PAYMENT_METHOD_CHOICES],
        required=False,
        allow_blank=True,
    )
    swift_file = serializers.FileField(required=False, allow_null=True)


class LogisticsPaymentRejectSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
