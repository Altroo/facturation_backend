from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from account.models import CustomUser, Membership
from parameter.models import Marque

from .models import LogisticsOrder, LogisticsOrderEvent, LogisticsOrderLine


REQUIRED_ORDER_FIELDS = (
    "fournisseur",
    "devise",
    "incoterm",
    "transport",
    "conditions_paiement",
    "responsable",
    "date_prevue",
    "statut",
    "origine_marchandise",
    "nature_marchandise",
)
REQUIRED_POSITIVE_ORDER_FIELDS = ("poids_net", "poids_brut", "volume")


def _user_display_name(user):
    if not user:
        return None
    return f"{user.first_name} {user.last_name}".strip() or user.email


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def validate_required_order_fields(attrs):
    errors = {}
    for field in REQUIRED_ORDER_FIELDS:
        if _is_blank(attrs.get(field)):
            errors[field] = _("Ce champ est obligatoire.")

    for field in REQUIRED_POSITIVE_ORDER_FIELDS:
        value = attrs.get(field)
        if value is None or value <= 0:
            errors[field] = _("Ce champ doit être supérieur à zéro.")

    if errors:
        raise serializers.ValidationError(errors)


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
    fournisseur = serializers.CharField(required=False, allow_blank=True, default="")
    devise = serializers.ChoiceField(
        choices=[
            choice[0] for choice in LogisticsOrder._meta.get_field("devise").choices
        ],
        required=False,
    )
    incoterm = serializers.CharField(required=False, allow_blank=True, default="")
    transport = serializers.CharField(required=False, allow_blank=True, default="")
    conditions_paiement = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    responsable = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(), required=False, allow_null=True
    )
    date_prevue = serializers.DateField(required=False, allow_null=True)
    date_reelle = serializers.DateField(required=False, allow_null=True)
    statut = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.STATUT_CHOICES],
        required=False,
    )
    poids_net = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal("0")
    )
    poids_brut = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal("0")
    )
    volume = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, default=Decimal("0")
    )
    origine_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    nature_marchandise = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    numero_domiciliation = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    banque = serializers.CharField(required=False, allow_blank=True, default="")
    montant_titre_importation = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    devise_titre_importation = serializers.ChoiceField(
        choices=[
            choice[0] for choice in LogisticsOrder._meta.get_field("devise").choices
        ],
        required=False,
        default="MAD",
    )
    date_titre_importation = serializers.DateField(required=False, allow_null=True)
    date_validation_titre_importation = serializers.DateField(
        required=False, allow_null=True
    )
    statut_titre_importation = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.TI_STATUT_CHOICES],
        required=False,
    )
    methode_paiement = serializers.ChoiceField(
        choices=[choice[0] for choice in LogisticsOrder.PAYMENT_METHOD_CHOICES],
        required=False,
        allow_blank=True,
    )
    cout_transport = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    frais_transit = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    frais_douane = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    tva = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    livraison_locale = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    autres_frais = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    titre_importation_file = serializers.FileField(required=False, allow_null=True)
    proforma_fournisseur_file = serializers.FileField(required=False, allow_null=True)
    justificatifs_file = serializers.FileField(required=False, allow_null=True)
    swift_file = serializers.FileField(required=False, allow_null=True)
    documents_originaux_file = serializers.FileField(required=False, allow_null=True)

    def validate_responsable(self, value):
        company_id = self.context.get("company_id")
        if (
            value
            and company_id
            and not Membership.objects.filter(
                user=value, company_id=company_id
            ).exists()
        ):
            raise serializers.ValidationError(
                _("Ce responsable n'appartient pas à cette société.")
            )
        return value

    def validate(self, attrs):
        validate_required_order_fields(attrs)
        date_prevue = attrs.get("date_prevue")
        date_reelle = attrs.get("date_reelle")
        if date_prevue and date_reelle and date_reelle < date_prevue:
            return attrs
        return attrs


class LogisticsOrderUpdateSerializer(serializers.ModelSerializer):
    marque = serializers.PrimaryKeyRelatedField(
        queryset=Marque.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = LogisticsOrder
        fields = [
            "fournisseur",
            "marque",
            "devise",
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
        validate_required_order_fields(attrs)
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
