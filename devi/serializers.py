from rest_framework import serializers

from core.serializers import (
    BaseCreateSerializer,
    BaseDetailUpdateSerializer,
    BaseLineWriteSerializer,
    BaseListSerializer,
    validate_line_currency,
    update_document_devise_on_first_line,
)
from .models import Devi, DeviLine


class DeviListSerializer(BaseListSerializer):
    """List serializer for Devi with totals as decimals."""

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "company",
            "client",
            "client_name",
            "date_devis",
            "mode_paiement",
            "mode_paiement_name",
            "numero_demande_prix_client",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_name",
            "lignes_count",
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


class DeviLineWriteSerializer(BaseLineWriteSerializer):
    """Write serializer for nested lines in Devi create/update."""

    class Meta:
        model = DeviLine
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


class DeviLineSerializer(serializers.ModelSerializer):
    """Standalone serializer for DeviLine CRUD endpoints."""

    devis = serializers.PrimaryKeyRelatedField(queryset=Devi.objects.all())
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    def validate(self, data):
        """Validate that line currency matches parent document currency."""
        validate_line_currency(data, self.instance, "devis")
        return data

    def create(self, validated_data):
        """Create line and set document devise if it's the first line."""
        devis = validated_data.get("devis")
        devise_prix_vente = validated_data.get("devise_prix_vente", "MAD")

        update_document_devise_on_first_line(devis, devise_prix_vente)

        return super().create(validated_data)

    class Meta:
        model = DeviLine
        fields = [
            "id",
            "devis",
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


class DeviSerializer(BaseCreateSerializer):
    """Base serializer for Devi create operations."""

    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

    def get_numero_field_name(self):
        return "numero_devis"

    def validate_numero_devis(self, value):
        return self.validate_numero(value)

    def get_line_model_class(self):
        return DeviLine

    def get_line_relation_field(self):
        return "devis"

    def get_line_serializer_class(self):
        return DeviLineSerializer

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "company",
            "client",
            "client_name",
            "date_devis",
            "numero_demande_prix_client",
            "mode_paiement",
            "mode_paiement_name",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_id",
            "created_by_user_name",
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
            "statut",
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "date_created",
            "date_updated",
        ]


class DeviDetailSerializer(BaseDetailUpdateSerializer):
    """Detailed serializer for retrieve/update with upsert semantics."""

    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

    def get_line_model_class(self):
        return DeviLine

    def get_line_relation_field(self):
        return "devis"

    def get_line_serializer_class(self):
        return DeviLineSerializer

    class Meta(DeviSerializer.Meta):
        read_only_fields = [
            "id",
            "company",
            "created_by_user",
            "date_created",
            "date_updated",
        ]
