from re import match

from django.db import transaction
from rest_framework import serializers

from .models import Devi, DeviLine


class DeviListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    client_name = serializers.CharField(source="client.nom", read_only=True)
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )
    created_by_user_name = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()

    class Meta:
        model = Devi
        fields = [
            "id",
            "numero_devis",
            "client",
            "client_name",
            "date_devis",
            "mode_paiement",
            "mode_paiement_name",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_name",
            "lignes_count",
        ]
        read_only_fields = fields

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.username
            )
        return None

    @staticmethod
    def get_lignes_count(obj):
        return obj.lignes.count()


class DeviLineWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for nested lines in Devi create/update.
    Accepts optional `id` for upsert; does NOT accept `devis` FK.
    """

    id = serializers.IntegerField(required=False)

    class Meta:
        model = DeviLine
        fields = [
            "id",
            "article",
            "prix_achat",
            "prix_vente",
            "quantity",
            "pourcentage_remise",
        ]


class DeviLineSerializer(serializers.ModelSerializer):
    """
    Standalone serializer for DeviLine CRUD endpoints.
    Includes `devis` as PK field for independent line operations.
    """

    devis = serializers.PrimaryKeyRelatedField(queryset=Devi.objects.all())
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

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


class DeviSerializer(serializers.ModelSerializer):
    """
    Base serializer for Devi create operations.
    Accepts write-only `lignes` array for creating associated lines.
    """

    client_name = serializers.CharField(source="client.nom", read_only=True)
    created_by_user_name = serializers.SerializerMethodField()
    created_by_user_id = serializers.IntegerField(
        source="created_by_user.id", read_only=True
    )
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )

    # Nested write-only input for creating lines
    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

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
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_id",
            "created_by_user_name",
            "lignes",
        ]
        read_only_fields = ["id", "created_by_user", "statut"]

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.username
            )
        return None

    @staticmethod
    def validate_numero_devis(value):
        """Validate format: 0001/25"""
        if not match(r"^\d{4}/\d{2}$", value):
            raise serializers.ValidationError(
                "Format de numéro de devis invalide. Format attendu: 0001/25"
            )
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop("lignes", [])
        instance = super().create(validated_data)

        # Create associated lines
        for line_data in lines_data:
            line_data.pop("id", None)  # Ignore any id on create
            DeviLine.objects.create(devis=instance, **line_data)

        return instance

    def to_representation(self, instance):
        """Include detailed lignes in response."""
        representation = super().to_representation(instance)
        representation["lignes"] = DeviLineSerializer(
            instance.lignes.all(), many=True, context=self.context
        ).data
        return representation


class DeviDetailSerializer(DeviSerializer):
    """
    Detailed serializer for retrieve/update operations.

    Update performs upsert semantics:
    - Lines with matching `id` are updated
    - Lines without `id` are created
    - Existing lines not in payload are deleted
    """

    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

    class Meta(DeviSerializer.Meta):
        read_only_fields = ["id", "created_by_user"]

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lignes", None)

        # Update Devi fields
        instance = super(DeviSerializer, self).update(instance, validated_data)

        # Handle nested lines update
        if lines_data is not None:
            # atomic to avoid partial modifications
            with transaction.atomic():
                existing_lines = {line.id: line for line in instance.lignes.all()}
                incoming_ids = set()

                for line_data in lines_data:
                    line_id = line_data.get("id")

                    if line_id and line_id in existing_lines:
                        # Update existing line
                        line_obj = existing_lines[line_id]
                        for field, value in line_data.items():
                            if field != "id":
                                setattr(line_obj, field, value)
                        line_obj.save()
                        incoming_ids.add(line_id)
                    else:
                        # Create new line (ignore any provided id)
                        create_data = {k: v for k, v in line_data.items() if k != "id"}
                        DeviLine.objects.create(devis=instance, **create_data)

                # Delete lines not included in payload
                ids_to_delete = set(existing_lines.keys()) - incoming_ids
                if ids_to_delete:
                    DeviLine.objects.filter(id__in=ids_to_delete).delete()

        return instance
