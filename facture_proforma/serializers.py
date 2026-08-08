from re import match

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
from .models import FactureProForma, FactureProFormaLine


class FactureProformaListSerializer(BaseListSerializer):
    """List serializer for FactureProForma with totals as decimals."""

    converted_facture_client = serializers.SerializerMethodField()
    converted_facture_client_numero = serializers.SerializerMethodField()
    source_devis = serializers.IntegerField(source="source_devis_id", read_only=True)
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    @staticmethod
    def _get_converted_facture(obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get(
            "converted_factures"
        )
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return obj.converted_factures.only("id", "numero_facture").first()

    def get_converted_facture_client(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.id if facture else None

    def get_converted_facture_client_numero(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.numero_facture if facture else None

    class Meta:
        model = FactureProForma
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
            "source_devis",
            "source_devis_numero",
            "converted_facture_client",
            "converted_facture_client_numero",
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
            "devise_prix_vente",
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

    def validate(self, attrs):
        """Validate that line currency matches parent document currency."""
        validate_line_currency(attrs, self.instance, "facture_pro_forma")
        return attrs

    def create(self, validated_data):
        """Create line and set document devise if it's the first line."""
        facture_pro_forma = validated_data.get("facture_pro_forma")
        devise_prix_vente = validated_data.get("devise_prix_vente", "MAD")

        update_document_devise_on_first_line(facture_pro_forma, devise_prix_vente)

        return super().create(validated_data)

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
            "devise_prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureProformaSerializer(BaseCreateSerializer):
    """Base serializer for FactureProForma create operations."""

    lignes = FactureProformaLineWriteSerializer(
        many=True, write_only=True, required=False
    )
    converted_facture_client = serializers.SerializerMethodField()
    converted_facture_client_numero = serializers.SerializerMethodField()
    source_devis = serializers.IntegerField(source="source_devis_id", read_only=True)
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    def _get_converted_facture(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get(
            "converted_factures"
        )
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return obj.converted_factures.only("id", "numero_facture").first()

    def get_converted_facture_client(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.id if facture else None

    def get_converted_facture_client_numero(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.numero_facture if facture else None

    def get_numero_field_name(self):
        return "numero_facture"

    @staticmethod
    def validate_numero_facture(value):
        if not match(r"^(?:P\d{3,}|\d{4,})/\d{2}$", value):
            raise serializers.ValidationError(
                _("Format de numero facture invalide. Format attendu: P001/25")
            )
        return value

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
            "company",
            "client",
            "client_name",
            "date_facture",
            "date_echeance",
            "numero_bon_commande_client",
            "termes_paiement",
            "source_devis",
            "source_devis_numero",
            "converted_facture_client",
            "converted_facture_client_numero",
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
            "source_devis",
            "source_devis_numero",
            "statut",
            "converted_facture_client",
            "converted_facture_client_numero",
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
    converted_facture_client = serializers.SerializerMethodField()
    converted_facture_client_numero = serializers.SerializerMethodField()
    source_devis = serializers.IntegerField(source="source_devis_id", read_only=True)
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )

    @staticmethod
    def _get_converted_facture(obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get(
            "converted_factures"
        )
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return obj.converted_factures.only("id", "numero_facture").first()

    def get_converted_facture_client(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.id if facture else None

    def get_converted_facture_client_numero(self, obj):
        facture = self._get_converted_facture(obj)
        return facture.numero_facture if facture else None

    def get_line_model_class(self):
        return FactureProFormaLine

    def get_line_relation_field(self):
        return "facture_pro_forma"

    def get_line_serializer_class(self):
        return FactureProFormaLineSerializer

    @staticmethod
    def validate_numero_facture(value):
        if not match(r"^(?:P\d{3,}|\d{4,})/\d{2}$", value):
            raise serializers.ValidationError(
                _("Format de numero facture invalide. Format attendu: P001/25")
            )
        return value

    class Meta(FactureProformaSerializer.Meta):
        read_only_fields = [
            "id",
            "company",
            "created_by_user",
            "converted_facture_client",
            "converted_facture_client_numero",
            "date_created",
            "date_updated",
        ]
