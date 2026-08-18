from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.serializers import (
    BaseCreateSerializer,
    BaseDetailUpdateSerializer,
    BaseLineWriteSerializer,
    BaseListSerializer,
    validate_line_currency,
    update_document_devise_on_first_line,
)
from .models import FactureClient, FactureClientLine
from facture_avoir.models import FactureAvoir
from reglement.models import Reglement


def _validate_inherited_supplier_snapshot(instance, data):
    if not instance or not (instance.source_proforma_id or instance.source_devis_id):
        return
    errors = {}
    for field in ("fournisseur", "fournisseur_email"):
        if field not in data:
            continue
        incoming = str(data.get(field) or "").strip()
        current = str(getattr(instance, field) or "").strip()
        if incoming != current:
            errors[field] = _(
                "Cette information est héritée du document source et n'est pas modifiable."
            )
    if errors:
        raise serializers.ValidationError(errors)


class FactureClientPaymentFieldsMixin:
    nombre_paiements = serializers.SerializerMethodField()
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    statut_paiement = serializers.SerializerMethodField()

    @staticmethod
    def _get_total_paye(obj):
        annotated = getattr(obj, "total_paid", None)
        if annotated is not None:
            return annotated
        return Reglement.get_total_reglements_for_facture(obj.id)

    @staticmethod
    def _get_total_avoirs(obj):
        annotated = getattr(obj, "total_avoirs", None)
        if annotated is not None:
            return annotated
        return FactureAvoir.get_total_avoirs_for_facture(obj.id)

    @staticmethod
    def get_nombre_paiements(obj):
        annotated = getattr(obj, "payment_count", None)
        if annotated is not None:
            return annotated
        return Reglement.objects.filter(
            facture_client_id=obj.id, statut="Valide"
        ).count()

    def get_total_paye(self, obj):
        return self._get_total_paye(obj)

    def get_reste_a_payer(self, obj):
        return (
            obj.total_ttc_apres_remise
            - self._get_total_avoirs(obj)
            - self._get_total_paye(obj)
        )

    def get_statut_paiement(self, obj):
        total_paye = self._get_total_paye(obj)
        reste_a_payer = self.get_reste_a_payer(obj)
        if reste_a_payer <= 0:
            return "Payée"
        if total_paye > 0:
            return "Partiellement payée"
        return "Non payée"


class FactureClientListSerializer(FactureClientPaymentFieldsMixin, BaseListSerializer):
    """List serializer for FactureClient with totals as decimals."""

    nombre_paiements = serializers.SerializerMethodField()
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    statut_paiement = serializers.SerializerMethodField()
    source_proforma_numero = serializers.CharField(
        source="source_proforma.numero_facture", read_only=True
    )
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    class Meta:
        model = FactureClient
        fields = [
            "id",
            "numero_facture",
            "company",
            "client",
            "client_name",
            "date_facture",
            "date_echeance",
            "mode_paiement",
            "mode_paiement_name",
            "numero_bon_commande_client",
            "termes_paiement",
            "fournisseur",
            "fournisseur_email",
            "source_proforma",
            "source_proforma_numero",
            "source_devis",
            "source_devis_numero",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_name",
            "lignes_count",
            "nombre_paiements",
            "total_paye",
            "reste_a_payer",
            "statut_paiement",
            "remise_type",
            "remise",
            # totals (read-only)
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "devise",
        ]
        read_only_fields = fields


class FactureClientLineWriteSerializer(BaseLineWriteSerializer):
    """Write serializer for nested lines in FactureClient create/update."""

    class Meta:
        model = FactureClientLine
        fields = [
            "id",
            "article",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "devise_prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureClientLineSerializer(serializers.ModelSerializer):
    """Standalone serializer for FactureClientLine CRUD endpoints."""

    facture_client = serializers.PrimaryKeyRelatedField(
        queryset=FactureClient.objects.all()
    )
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    def validate(self, attrs):
        """Validate that line currency matches parent document currency."""
        validate_line_currency(attrs, self.instance, "facture_client")
        return attrs

    def create(self, validated_data):
        """Create line and set document devise if it's the first line."""
        facture_client = validated_data.get("facture_client")
        devise_prix_vente = validated_data.get("devise_prix_vente", "MAD")

        update_document_devise_on_first_line(facture_client, devise_prix_vente)

        return super().create(validated_data)

    class Meta:
        model = FactureClientLine
        fields = [
            "id",
            "facture_client",
            "article",
            "designation",
            "reference",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "devise_prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureClientSerializer(FactureClientPaymentFieldsMixin, BaseCreateSerializer):
    """Base serializer for FactureClient create operations."""

    nombre_paiements = serializers.SerializerMethodField()
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    statut_paiement = serializers.SerializerMethodField()
    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )
    source_proforma_numero = serializers.CharField(
        source="source_proforma.numero_facture", read_only=True
    )
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    def validate(self, data):
        data = super().validate(data)
        _validate_inherited_supplier_snapshot(self.instance, data)
        return data

    def get_numero_field_name(self):
        return "numero_facture"

    def validate_numero_facture(self, value):
        return self.validate_numero(value)

    def get_line_model_class(self):
        return FactureClientLine

    def get_line_relation_field(self):
        return "facture_client"

    def get_line_serializer_class(self):
        return FactureClientLineSerializer

    class Meta:
        model = FactureClient
        fields = [
            "id",
            "numero_facture",
            "company",
            "client",
            "client_name",
            "date_facture",
            "date_echeance",
            "numero_bon_commande_client",
            "termes_paiement",
            "fournisseur",
            "fournisseur_email",
            "source_proforma",
            "source_proforma_numero",
            "source_devis",
            "source_devis_numero",
            "mode_paiement",
            "mode_paiement_name",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_id",
            "created_by_user_name",
            "nombre_paiements",
            "total_paye",
            "reste_a_payer",
            "statut_paiement",
            "lignes",
            "remise_type",
            "remise",
            # totals (read-only)
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "devise",
            "date_created",
            "date_updated",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_by_user",
            "source_proforma",
            "source_proforma_numero",
            "source_devis",
            "source_devis_numero",
            "statut",
            "nombre_paiements",
            "total_paye",
            "reste_a_payer",
            "statut_paiement",
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "date_created",
            "date_updated",
        ]


class FactureClientDetailSerializer(
    FactureClientPaymentFieldsMixin, BaseDetailUpdateSerializer
):
    """Detailed serializer for retrieve/update with upsert semantics."""

    nombre_paiements = serializers.SerializerMethodField()
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()
    statut_paiement = serializers.SerializerMethodField()
    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )
    source_proforma_numero = serializers.CharField(
        source="source_proforma.numero_facture", read_only=True
    )
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    def validate(self, data):
        data = super().validate(data)
        _validate_inherited_supplier_snapshot(self.instance, data)
        return data

    def get_line_model_class(self):
        return FactureClientLine

    def get_line_relation_field(self):
        return "facture_client"

    def get_line_serializer_class(self):
        return FactureClientLineSerializer

    class Meta(FactureClientSerializer.Meta):
        read_only_fields = [
            "id",
            "company",
            "created_by_user",
            "source_proforma",
            "source_proforma_numero",
            "source_devis",
            "source_devis_numero",
            "date_created",
            "date_updated",
        ]
