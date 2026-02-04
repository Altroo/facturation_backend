from rest_framework import serializers

from core.serializers import (
    BaseCreateSerializer,
    BaseDetailUpdateSerializer,
    BaseLineWriteSerializer,
    BaseListSerializer,
)
from .models import FactureProForma, FactureProFormaLine


class FactureProformaListSerializer(BaseListSerializer):
    """List serializer for FactureProForma with totals as decimals."""

    class Meta:
        model = FactureProForma
        fields = [
            "id",
            "numero_facture",
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
        ]
        read_only_fields = fields


class FactureProformaLineWriteSerializer(BaseLineWriteSerializer):
    """Write serializer for nested lines in FactureProForma create/update."""

    class Meta:
        model = FactureProFormaLine
        fields = [
            "id",
            "article",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureProFormaLineSerializer(serializers.ModelSerializer):
    """Standalone serializer for FactureProFormaLine CRUD endpoints."""

    facture_pro_forma = serializers.PrimaryKeyRelatedField(
        queryset=FactureProForma.objects.all()
    )
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    class Meta:
        model = FactureProFormaLine
        fields = [
            "id",
            "facture_pro_forma",
            "article",
            "designation",
            "reference",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureProformaSerializer(BaseCreateSerializer):
    """Base serializer for FactureProForma create operations."""

    lignes = FactureProformaLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def get_numero_field_name(self):
        return "numero_facture"

    def validate_numero_facture(self, value):
        return self.validate_numero(value)

    def get_line_model_class(self):
        return FactureProFormaLine

    def get_line_relation_field(self):
        return "facture_pro_forma"

    def get_line_serializer_class(self):
        return FactureProFormaLineSerializer

    class Meta:
        model = FactureProForma
        fields = [
            "id",
            "numero_facture",
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
            "date_created",
            "date_updated",
        ]
        read_only_fields = [
            "id",
            "created_by_user",
            "statut",
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "date_created",
            "date_updated",
        ]


class FactureProformaDetailSerializer(BaseDetailUpdateSerializer):
    """Detailed serializer for retrieve/update with upsert semantics."""

    lignes = FactureProformaLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def get_line_model_class(self):
        return FactureProFormaLine

    def get_line_relation_field(self):
        return "facture_pro_forma"

    def get_line_serializer_class(self):
        return FactureProFormaLineSerializer

    class Meta(FactureProformaSerializer.Meta):
        read_only_fields = ["id", "created_by_user", "date_created", "date_updated"]
