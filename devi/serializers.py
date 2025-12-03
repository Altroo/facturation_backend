from re import match

from django.db import transaction
from rest_framework import serializers

from .models import Devi, DeviLine


class DeviListSerializer(serializers.ModelSerializer):
    client_name = serializers.StringRelatedField(read_only=True)
    mode_paiement_name = serializers.ReadOnlyField(source="mode_paiement.nom")
    created_by_user_name = serializers.StringRelatedField(
        source="created_by_user", read_only=True
    )
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
    def get_lignes_count(obj):
        return obj.lignes.count()


class DeviLineWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer used when creating/updating Devi with nested lines.
    Accepts optional `id` for upsert on update; does NOT accept `devis` FK.
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
    Read / standalone serializer for DeviLine endpoints.
    Keeps `devis` as a PK field for the lines API.
    """

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
        devis = validated_data.pop("devis")
        return DeviLine.objects.create(devis=devis, **validated_data)


class DeviSerializer(serializers.ModelSerializer):
    """
    Serializer used for create (and lightweight responses).
    Accepts a write-only `lignes` array to create associated DeviLine rows.
    Returns `lignes` in representation (detailed) so POST responses include lines.
    """

    client_name = serializers.StringRelatedField(read_only=True)
    created_by_user_name = serializers.StringRelatedField(read_only=True)
    created_by_user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    created_by_user_id = serializers.ReadOnlyField(source="created_by_user.id")
    mode_paiement_name = serializers.ReadOnlyField(source="mode_paiement.nom")

    # nested write-only input (uses write serializer which now accepts optional id)
    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

    @staticmethod
    def validate_numero_devis(value):
        # e.g. 0001/25
        if not match(r"^\d{4}/\d{2}$", value):
            raise serializers.ValidationError(
                "Invalid numero_devis format. Expected `0001/25`."
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
            "mode_paiement_name",
            "remarque",
            "created_by_user",
            "created_by_user_id",
            "created_by_user_name",
            "lignes",
        ]

    def create(self, validated_data):
        lines_data = validated_data.pop("lignes", None)
        instance = super().create(validated_data)
        if lines_data:
            for line in lines_data:
                # ignore provided id on create
                line.pop("id", None)
                DeviLine.objects.create(devis=instance, **line)
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # attach detailed lignes for read responses
        representation["lignes"] = DeviLineSerializer(
            instance.lignes.all(), many=True, context=self.context
        ).data
        return representation


class DeviDetailSerializer(DeviSerializer):
    """
    Detailed serializer used for retrieve/update/delete.
    On update: performs upsert semantics for `lignes`:
      - If an incoming line has `id` matching an existing line -> update that line.
      - If an incoming line has no `id` -> create a new line.
      - Any existing DB lines not present in incoming payload are deleted.
    """

    lignes = DeviLineWriteSerializer(many=True, write_only=True, required=False)

    class Meta(DeviSerializer.Meta):
        pass

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lignes", None)
        instance = super().update(instance, validated_data)

        if lines_data is not None:
            # atomic to avoid partial modifications
            with transaction.atomic():
                existing = {ligne.id: ligne for ligne in instance.lignes.all()}
                incoming_ids = set()

                for line in lines_data:
                    line_id = line.get("id")
                    # update existing
                    if line_id and line_id in existing:
                        obj = existing[line_id]
                        # update allowed fields
                        for attr, val in line.items():
                            if attr == "id":
                                continue
                            setattr(obj, attr, val)
                        obj.save()
                        incoming_ids.add(line_id)
                    else:
                        # create new line (ignore any id passed)
                        data_for_create = {k: v for k, v in line.items() if k != "id"}
                        DeviLine.objects.create(devis=instance, **data_for_create)

                # delete lines that exist in DB but were not included in incoming payload
                ids_to_keep = incoming_ids
                ids_existing = set(existing.keys())
                ids_to_delete = list(ids_existing - ids_to_keep)
                if ids_to_delete:
                    DeviLine.objects.filter(id__in=ids_to_delete).delete()

        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["lignes"] = DeviLineSerializer(
            instance.lignes.all(), many=True, context=self.context
        ).data
        return representation
