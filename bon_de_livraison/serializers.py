from rest_framework import serializers

from core.serializers import (
    BaseCreateSerializer,
    BaseDetailUpdateSerializer,
    BaseLineWriteSerializer,
    BaseListSerializer,
    validate_line_currency,
    update_document_devise_on_first_line,
)
from .models import BonDeLivraison, BonDeLivraisonLine


class BonDeLivraisonListSerializer(BaseListSerializer):
    """List serializer for BonDeLivraison with totals as decimals."""

    class Meta:
        model = BonDeLivraison
        fields = [
            "id",
            "numero_bon_livraison",
            "company",
            "client",
            "client_name",
            "date_bon_livraison",
            "mode_paiement",
            "mode_paiement_name",
            "numero_bon_commande_client",
            "livre_par",
            "livre_par_name",
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

    livre_par_name = serializers.CharField(source="livre_par.nom", read_only=True)


class BonDeLivraisonLineWriteSerializer(BaseLineWriteSerializer):
    """Write serializer for nested lines in BonDeLivraison create/update."""

    class Meta:
        model = BonDeLivraisonLine
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


class BonDeLivraisonLineSerializer(serializers.ModelSerializer):
    """Standalone serializer for BonDeLivraisonLine CRUD endpoints."""

    bon_de_livraison = serializers.PrimaryKeyRelatedField(
        queryset=BonDeLivraison.objects.all()
    )
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    def validate(self, data):
        """Validate that line currency matches parent document currency."""
        validate_line_currency(data, self.instance, "bon_de_livraison")
        return data

    def create(self, validated_data):
        """Create line and set document devise if it's the first line."""
        bon_de_livraison = validated_data.get("bon_de_livraison")
        devise_prix_vente = validated_data.get("devise_prix_vente", "MAD")

        update_document_devise_on_first_line(bon_de_livraison, devise_prix_vente)

        return super().create(validated_data)

    class Meta:
        model = BonDeLivraisonLine
        fields = [
            "id",
            "bon_de_livraison",
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


class BonDeLivraisonSerializer(BaseCreateSerializer):
    """Base serializer for BonDeLivraison create operations."""

    lignes = BonDeLivraisonLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def get_numero_field_name(self):
        return "numero_bon_livraison"

    def validate_numero_bon_livraison(self, value):
        return self.validate_numero(value)

    def get_line_model_class(self):
        return BonDeLivraisonLine

    def get_line_relation_field(self):
        return "bon_de_livraison"

    def get_line_serializer_class(self):
        return BonDeLivraisonLineSerializer

    class Meta:
        model = BonDeLivraison
        fields = [
            "id",
            "numero_bon_livraison",
            "company",
            "client",
            "client_name",
            "date_bon_livraison",
            "numero_bon_commande_client",
            "livre_par",
            "livre_par_name",
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

    livre_par_name = serializers.CharField(source="livre_par.nom", read_only=True)


class BonDeLivraisonDetailSerializer(BaseDetailUpdateSerializer):
    """Detailed serializer for retrieve/update with upsert semantics."""

    lignes = BonDeLivraisonLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def get_line_model_class(self):
        return BonDeLivraisonLine

    def get_line_relation_field(self):
        return "bon_de_livraison"

    def get_line_serializer_class(self):
        return BonDeLivraisonLineSerializer

    class Meta(BonDeLivraisonSerializer.Meta):
        read_only_fields = ["id", "created_by_user", "date_created", "date_updated"]

    livre_par_name = serializers.CharField(source="livre_par.nom", read_only=True)
