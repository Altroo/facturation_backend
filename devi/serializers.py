from re import match

from rest_framework import serializers

from .models import Devi, DeviLine


class DeviLineSerializer(serializers.ModelSerializer):
    devis = serializers.PrimaryKeyRelatedField(queryset=Devi.objects.all())
    designation = serializers.ReadOnlyField(source="article.designation")
    reference = serializers.ReadOnlyField(source="article.reference")

    class Meta:
        model = DeviLine
        fields = [
            "id",
            "devis",
            "article",
            "designation",
            "reference",
            "prix_achat",
            "prix_vente",
            "quantity",
            "pourcentage_remise",
        ]

    def create(self, validated_data):
        # ensure the FK is applied when saving
        devis = validated_data.pop("devis")
        return DeviLine.objects.create(devis=devis, **validated_data)


class DeviListSerializer(serializers.ModelSerializer):
    # get's from __str__ in client model
    client_name = serializers.StringRelatedField()

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "client",
            "client_name",
            "date_devis",
            "statut",
            "date_created",
        ]


class DeviDetailSerializer(serializers.ModelSerializer):
    lignes = DeviLineSerializer(many=True, read_only=True)
    client_name = serializers.StringRelatedField(read_only=True)
    mode_paiement_name = serializers.ReadOnlyField(
        source="mode_paiement.nom",
    )
    created_by_user_name = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "client",
            "client_name",
            "date_devis",
            "numero_demande_prix_client",
            "mode_paiement",
            "mode_paiement_name",
            "remarque",
            "created_by_user",
            "created_by_user_name",
            "statut",
            "date_created",
            "date_updated",
            "lignes",
        ]


class DeviSerializer(serializers.ModelSerializer):
    client_name = serializers.StringRelatedField(read_only=True)
    created_by_user_name = serializers.StringRelatedField(read_only=True)
    created_by_user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    created_by_user_id = serializers.ReadOnlyField(source="created_by_user.id")

    @staticmethod
    def validate_numero_devis(value):
        if not match(r"^\d{4}/\d{2}$", value):
            raise serializers.ValidationError(
                "Invalid numero_devis format. Expected '0001/25'."
            )
        return value

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "client",
            "client_name",
            "date_devis",
            "numero_demande_prix_client",
            "mode_paiement",
            "remarque",
            "created_by_user",
            "created_by_user_id",
            "created_by_user_name",
        ]
