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


class FactureClientListSerializer(BaseListSerializer):
    """List serializer for FactureClient with totals as decimals."""

    class Meta:
        model = FactureClient
        fields = [
            "id",
            "numero_facture",
            "company",
            "client",
            "client_name",
            "date_facture",
            "mode_paiement",
            "mode_paiement_name",
            "numero_bon_commande_client",
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

    def validate(self, data):
        """Validate that line currency matches parent document currency."""
        validate_line_currency(data, self.instance, "facture_client")
        return data

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


class FactureClientSerializer(BaseCreateSerializer):
    """Base serializer for FactureClient create operations."""

    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )

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
            "numero_bon_commande_client",
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


class FactureClientDetailSerializer(BaseDetailUpdateSerializer):
    """Detailed serializer for retrieve/update with upsert semantics."""

    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def get_line_model_class(self):
        return FactureClientLine

    def get_line_relation_field(self):
        return "facture_client"

    def get_line_serializer_class(self):
        return FactureClientLineSerializer

    class Meta(FactureClientSerializer.Meta):
        read_only_fields = ["id", "created_by_user", "date_created", "date_updated"]
