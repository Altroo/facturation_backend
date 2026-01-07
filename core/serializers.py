from re import match

from django.db import transaction
from rest_framework import serializers


class BaseListSerializer(serializers.ModelSerializer):
    """Abstract list serializer with common total fields and helpers."""

    client_name = serializers.StringRelatedField(source="client", read_only=True)
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )
    created_by_user_name = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()

    total_ht = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_tva = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc_apres_remise = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.email
            )
        return None

    @staticmethod
    def get_lignes_count(obj):
        return obj.lignes.count()

    class Meta:
        abstract = True


class BaseDetailSerializer(serializers.ModelSerializer):
    """Abstract detail serializer with common fields, validation, and totals."""

    client_name = serializers.StringRelatedField(source="client", read_only=True)
    created_by_user_name = serializers.SerializerMethodField()
    created_by_user_id = serializers.IntegerField(
        source="created_by_user.id", read_only=True
    )
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )

    total_ht = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_tva = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_ttc_apres_remise = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.email
            )
        return None

    def validate(self, data):
        """
        Validate document-level remise fields:
        - remise must be >= 0
        - if remise_type == 'Pourcentage' then 0 <= remise <= 100
        """
        remise = data.get("remise")
        remise_type = data.get(
            "remise_type",
            (
                getattr(self.instance, "remise_type", "")
                if getattr(self, "instance", None)
                else ""
            ),
        )

        if remise is None:
            return data

        try:
            remise_val = float(remise)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"remise": "Valeur de remise invalide."})

        if remise_val < 0:
            raise serializers.ValidationError(
                {"remise": "La remise doit être positive ou nulle."}
            )

        if remise_type == "":
            return data

        if remise_type == "Pourcentage":
            if not 0 <= remise_val <= 100:
                raise serializers.ValidationError(
                    {"remise": "La remise en pourcentage doit être entre 0 et 100."}
                )
        elif remise_type == "Fixe":
            pass
        else:
            raise serializers.ValidationError(
                {"remise_type": "Type de remise invalide."}
            )

        return data

    def get_numero_field_name(self):
        """Return the numero field name (e.g., 'numero_devis', 'numero_facture'). Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_numero_field_name()")

    def validate_numero(self, value):
        """Validate numero format: 0001/25"""
        if not match(r"^\d{4}/\d{2}$", value):
            field_name = self.get_numero_field_name()
            raise serializers.ValidationError(
                f"Format de {field_name.replace('_', ' ')} invalide. Format attendu: 0001/25"
            )
        return value

    class Meta:
        abstract = True


class BaseLineWriteSerializer(serializers.ModelSerializer):
    """Abstract write serializer for nested lines."""

    id = serializers.IntegerField(required=False)

    def validate(self, data):
        if data["prix_vente"] < data["prix_achat"]:
            raise serializers.ValidationError(
                "Le prix de vente doit être supérieur ou égal au prix d'achat."
            )

        remise = data.get("remise", 0)
        remise_type = data.get("remise_type") or "Pourcentage"
        quantity = data.get("quantity", 1)
        line_total = data["prix_vente"] * quantity

        if remise < 0:
            raise serializers.ValidationError("La remise doit être positive ou nulle.")

        if remise_type == "Pourcentage":
            if not 0 <= remise <= 100:
                raise serializers.ValidationError(
                    "La remise en pourcentage doit être entre 0 et 100."
                )
        elif remise_type == "Fixe":
            if remise > line_total:
                raise serializers.ValidationError(
                    "La remise fixe ne peut pas dépasser le total de la ligne."
                )
        else:
            raise serializers.ValidationError("Type de remise invalide.")

        return data

    class Meta:
        abstract = True


class BaseCreateSerializer(BaseDetailSerializer):
    """Abstract create serializer with create and to_representation logic."""

    def get_line_model_class(self):
        """Return the line model class. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_line_model_class()")

    def get_line_relation_field(self):
        """Return the foreign key field name (e.g., 'devis', 'facture_client'). Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_line_relation_field()")

    def get_line_serializer_class(self):
        """Return the line serializer class for representation. Override in subclasses."""
        raise NotImplementedError(
            "Subclasses must implement get_line_serializer_class()"
        )

    def create(self, validated_data):
        lines_data = validated_data.pop("lignes", [])
        instance = super().create(validated_data)

        line_model = self.get_line_model_class()
        relation_field = self.get_line_relation_field()

        for line_data in lines_data:
            line_data.pop("id", None)
            line_model.objects.create(**{relation_field: instance}, **line_data)

        return instance

    def to_representation(self, instance):
        """Include detailed lignes in response."""
        representation = super().to_representation(instance)
        line_serializer_class = self.get_line_serializer_class()
        representation["lignes"] = line_serializer_class(
            instance.lignes.all(), many=True, context=self.context
        ).data
        return representation

    class Meta:
        abstract = True


class BaseDetailUpdateSerializer(BaseCreateSerializer):
    """Abstract detail serializer with upsert update logic for nested lines."""

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lignes", None)

        instance = super(BaseCreateSerializer, self).update(instance, validated_data)

        if lines_data is not None:
            with transaction.atomic():
                existing_lines = {line.id: line for line in instance.lignes.all()}
                incoming_ids = set()
                line_model = self.get_line_model_class()
                relation_field = self.get_line_relation_field()

                for line_data in lines_data:
                    line_id = line_data.get("id")

                    if line_id and line_id in existing_lines:
                        line_obj = existing_lines[line_id]
                        for field, value in line_data.items():
                            if field != "id":
                                setattr(line_obj, field, value)
                        line_obj.save()
                        incoming_ids.add(line_id)
                    else:
                        create_data = {k: v for k, v in line_data.items() if k != "id"}
                        line_model.objects.create(
                            **{relation_field: instance}, **create_data
                        )

                ids_to_delete = set(existing_lines.keys()) - incoming_ids
                if ids_to_delete:
                    line_model.objects.filter(id__in=ids_to_delete).delete()

        return instance

    class Meta:
        abstract = True
