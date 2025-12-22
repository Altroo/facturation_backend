from decimal import Decimal, ROUND_HALF_UP
from re import match

from django.db import transaction
from rest_framework import serializers

from .models import FactureClient, FactureClientLine


class FactureClientListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    client_name = serializers.StringRelatedField(source="client", read_only=True)
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )
    created_by_user_name = serializers.SerializerMethodField()
    lignes_count = serializers.SerializerMethodField()

    # Present totals as decimals (instead of raw centimes)
    total_ht = serializers.SerializerMethodField()
    total_tva = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    total_ttc_apres_remise = serializers.SerializerMethodField()

    @staticmethod
    def _cents_to_decimal(cents):
        return (Decimal(cents or 0) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def get_total_ht(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ht", 0))

    def get_total_tva(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_tva", 0))

    def get_total_ttc(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ttc", 0))

    def get_total_ttc_apres_remise(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ttc_apres_remise", 0))

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

    class Meta:
        model = FactureClient
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


class FactureClientLineWriteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    def validate(self, data):
        # prix_vente must be >= prix_achat
        if data["prix_vente"] < data["prix_achat"]:
            raise serializers.ValidationError(
                "Le prix de vente doit être supérieur ou égal au prix d'achat."
            )

        remise = data.get("remise", 0)
        # Treat empty/null remise_type as default "Pourcentage"
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
        model = FactureClientLine
        fields = [
            "id",
            "article",
            "prix_achat",
            "prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureClientLineSerializer(serializers.ModelSerializer):
    facture_client = serializers.PrimaryKeyRelatedField(
        queryset=FactureClient.objects.all()
    )
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    class Meta:
        model = FactureClientLine
        fields = [
            "id",
            "facture_client",
            "article",
            "designation",
            "reference",
            "prix_achat",
            "prix_vente",
            "quantity",
            "remise_type",
            "remise",
        ]


class FactureClientSerializer(serializers.ModelSerializer):
    client_name = serializers.StringRelatedField(source="client", read_only=True)
    created_by_user_name = serializers.SerializerMethodField()
    created_by_user_id = serializers.IntegerField(
        source="created_by_user.id", read_only=True
    )
    mode_paiement_name = serializers.CharField(
        source="mode_paiement.nom", read_only=True
    )
    # Nested write-only input for creating lines (updated serializer)
    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    # Present totals as decimals
    total_ht = serializers.SerializerMethodField()
    total_tva = serializers.SerializerMethodField()
    total_ttc = serializers.SerializerMethodField()
    total_ttc_apres_remise = serializers.SerializerMethodField()

    @staticmethod
    def _cents_to_decimal(cents):
        return (Decimal(cents or 0) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def get_total_ht(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ht", 0))

    def get_total_tva(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_tva", 0))

    def get_total_ttc(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ttc", 0))

    def get_total_ttc_apres_remise(self, obj):
        return self._cents_to_decimal(getattr(obj, "total_ttc_apres_remise", 0))

    @staticmethod
    def get_created_by_user_name(obj):
        if obj.created_by_user:
            return (
                f"{obj.created_by_user.first_name} {obj.created_by_user.last_name}".strip()
                or obj.created_by_user.username
            )
        return None

    @staticmethod
    def validate_numero_facture(value):
        """Validate format: 0001/25"""
        if not match(r"^\d{4}/\d{2}$", value):
            raise serializers.ValidationError(
                "Format de numéro de facture invalide. Format attendu: 0001/25"
            )
        return value

    def validate(self, data):
        """
        Validate high level remise fields:
        - remise must be >= 0
        - if remise_type == 'pourcentage' then 0 <= remise <= 100
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
            remise_val = int(remise)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"remise": "Valeur de remise invalide."})

        if remise_val < 0:
            raise serializers.ValidationError(
                {"remise": "La remise doit être positive ou nulle."}
            )
        # if remise_type is not provided, skip further validation
        if remise_type == "":
            return data

        if remise_type == "Pourcentage":
            if not 0 <= remise_val <= 100:
                raise serializers.ValidationError(
                    {"remise": "La remise en pourcentage doit être entre 0 et 100."}
                )
        elif remise_type == "Fixe":
            # For fixe we only ensure non-negative here. Full validation against totals
            # can be performed elsewhere where totals are available.
            pass
        else:
            raise serializers.ValidationError(
                {"remise_type": "Type de remise invalide."}
            )

        return data

    def create(self, validated_data):
        lines_data = validated_data.pop("lignes", [])
        instance = super().create(validated_data)

        # Create associated lines
        for line_data in lines_data:
            line_data.pop("id", None)  # Ignore any id on create
            FactureClientLine.objects.create(facture_client=instance, **line_data)

        return instance

    def to_representation(self, instance):
        """Include detailed lignes in response."""
        representation = super().to_representation(instance)
        representation["lignes"] = FactureClientLineSerializer(
            instance.lignes.all(), many=True, context=self.context
        ).data
        return representation

    class Meta:
        model = FactureClient
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


class FactureClientDetailSerializer(FactureClientSerializer):
    """
    Detailed serializer for retrieve/update operations.

    Update performs upsert semantics:
    - Lines with matching `id` are updated
    - Lines without `id` are created
    - Existing lines not in payload are deleted
    """

    lignes = FactureClientLineWriteSerializer(
        many=True, write_only=True, required=False
    )

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lignes", None)

        instance = super(FactureClientSerializer, self).update(instance, validated_data)

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
                        FactureClientLine.objects.create(
                            facture_client=instance, **create_data
                        )

                # Delete lines not included in payload
                ids_to_delete = set(existing_lines.keys()) - incoming_ids
                if ids_to_delete:
                    FactureClientLine.objects.filter(id__in=ids_to_delete).delete()

        return instance

    class Meta(FactureClientSerializer.Meta):
        read_only_fields = ["id", "created_by_user", "date_created", "date_updated"]
