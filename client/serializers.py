from rest_framework import serializers

from .models import Client, Ville


class ClientBaseSerializer(serializers.ModelSerializer):
    """Common fields and validation for all client serializers."""

    class Meta:
        model = Client
        fields = [
            "id",
            "code_client",
            "client_type",
            "company",
            "adresse",
            "ville",
            "tel",
            "email",
            "delai_de_paiement",
            "remarque",
            "date_created",
            "archived",
            # personne morale
            "raison_sociale",
            "numero_du_compte",
            "ICE",
            "registre_de_commerce",
            "identifiant_fiscal",
            "taxe_professionnelle",
            "CNSS",
            "fax",
            # personne physique
            "nom",
            "prenom",
        ]
        read_only_fields = ["id", "date_created"]

    def validate(self, attrs):
        """Enforce required fields depending on `client_type`."""
        client_type = attrs.get("client_type") or getattr(
            self.instance, "client_type", None
        )
        errors = {}

        if client_type == Client.PERSONNE_MORALE:
            required = {
                "raison_sociale": "Raison sociale",
                "ville": "Ville",
                "ICE": "ICE",
                "registre_de_commerce": "Registre de commerce",
                "delai_de_paiement": "Délai de paiement",
            }
        else:  # PERSONNE_PHYSIQUE
            required = {
                "nom": "Nom",
                "prenom": "Prénom",
                "adresse": "Adresse",
                "ville": "Ville",
                "tel": "Téléphone",
                "delai_de_paiement": "Délai de paiement",
            }

        for field, label in required.items():
            if not attrs.get(field) and not (
                self.instance and getattr(self.instance, field)
            ):
                errors[field] = f"{label} est obligatoire pour ce type de client."

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ClientSerializer(ClientBaseSerializer):
    """Used for creation (POST) and full update (PUT)."""

    ville = serializers.PrimaryKeyRelatedField(
        queryset=Ville.objects.all(), required=False, allow_null=True
    )
    company = serializers.PrimaryKeyRelatedField(
        queryset=Client._meta.get_field("company").related_model.objects.all(),
        required=False,
        allow_null=True,
    )


class ClientDetailSerializer(ClientSerializer):
    """Read‑only view for retrieve (GET)."""

    ville_name = serializers.ReadOnlyField(source="ville.nom", read_only=True)

    class Meta(ClientSerializer.Meta):
        fields = ClientSerializer.Meta.fields + ["ville_name"]
        read_only_fields = ClientSerializer.Meta.read_only_fields + [
            "ville_name",
            "archived",
        ]


class ClientListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view."""

    company_name = serializers.ReadOnlyField(
        source="company.raison_sociale", read_only=True
    )
    ville_name = serializers.ReadOnlyField(source="ville.nom", read_only=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "code_client",
            "client_type",
            "raison_sociale",
            "nom",
            "prenom",
            "ville",
            "ville_name",
            "company",
            "company_name",
            "date_created",
            "archived",
        ]
        read_only_fields = ["company_name", "ville_name"]
