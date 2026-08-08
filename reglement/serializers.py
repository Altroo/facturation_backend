from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Reglement

# Facture statuses that allow règlement creation
ALLOWED_FACTURE_STATUSES = ["Envoyé", "Accepté"]


class ReglementClientNameMixin:
    @staticmethod
    def get_client_name(obj):
        client = obj.facture_client.client
        return str(client) if client else None


class ReglementListSerializer(ReglementClientNameMixin, serializers.ModelSerializer):
    """Serializer for listing règlements."""

    client_name = serializers.SerializerMethodField()
    facture_client_numero = serializers.CharField(
        source="facture_client.numero_facture",
        read_only=True,
    )
    client = serializers.IntegerField(
        source="facture_client.client.id",
        read_only=True,
    )
    mode_reglement_name = serializers.CharField(
        source="mode_reglement.nom",
        read_only=True,
    )
    devise = serializers.CharField(
        source="facture_client.devise",
        read_only=True,
    )

    class Meta:
        model = Reglement
        fields = [
            "id",
            "facture_client",
            "facture_client_numero",
            "client",
            "client_name",
            "mode_reglement",
            "mode_reglement_name",
            "libelle",
            "observations",
            "montant",
            "devise",
            "date_reglement",
            "date_echeance",
            "statut",
            "date_created",
            "date_updated",
        ]
        read_only_fields = fields


# NOTE: This serializer is designed for single-object retrieval only.
# Using it in a list context will cause N+1 queries (one per SerializerMethodField).
# For lists, use ReglementListSerializer.
class ReglementDetailSerializer(ReglementClientNameMixin, serializers.ModelSerializer):
    """Serializer for règlement detail with invoice-specific financial info."""

    client_name = serializers.SerializerMethodField()
    facture_client_numero = serializers.CharField(
        source="facture_client.numero_facture",
        read_only=True,
    )
    client = serializers.IntegerField(
        source="facture_client.client.id",
        read_only=True,
    )
    mode_reglement_name = serializers.CharField(
        source="mode_reglement.nom",
        read_only=True,
    )
    devise = serializers.CharField(
        source="facture_client.devise",
        read_only=True,
    )

    # Invoice-specific financial fields
    montant_facture = serializers.SerializerMethodField()
    total_reglements_facture = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()

    class Meta:
        model = Reglement
        fields = [
            "id",
            "facture_client",
            "facture_client_numero",
            "client",
            "client_name",
            "mode_reglement",
            "mode_reglement_name",
            "libelle",
            "observations",
            "montant",
            "devise",
            "date_reglement",
            "date_echeance",
            "statut",
            "date_created",
            "date_updated",
            # Financial fields
            "montant_facture",
            "total_reglements_facture",
            "reste_a_payer",
        ]
        read_only_fields = fields

    @staticmethod
    def get_montant_facture(obj) -> Decimal:
        """Return the total amount of the associated invoice."""
        return obj.facture_client.total_ttc_apres_remise

    @staticmethod
    def get_total_reglements_facture(obj) -> Decimal:
        """Return the total of all valid règlements for the associated invoice."""
        return Reglement.get_total_reglements_for_facture(obj.facture_client_id)

    @staticmethod
    def get_reste_a_payer(obj) -> Decimal:
        """Return the remaining amount to pay for the associated invoice."""
        return Reglement.get_reste_a_payer(obj.facture_client)


class ReglementCreateSerializer(ReglementClientNameMixin, serializers.ModelSerializer):
    """Serializer for creating règlements with montant validation."""

    client_name = serializers.SerializerMethodField()
    facture_client_numero = serializers.CharField(
        source="facture_client.numero_facture",
        read_only=True,
    )
    mode_reglement_name = serializers.CharField(
        source="mode_reglement.nom",
        read_only=True,
    )

    class Meta:
        model = Reglement
        fields = [
            "id",
            "facture_client",
            "facture_client_numero",
            "client_name",
            "mode_reglement",
            "mode_reglement_name",
            "libelle",
            "observations",
            "montant",
            "date_reglement",
            "date_echeance",
            "statut",
            "date_created",
            "date_updated",
        ]
        read_only_fields = [
            "id",
            "statut",
            "date_created",
            "date_updated",
        ]

    @staticmethod
    def validate_montant(value):
        """Validate that montant is positive."""
        if value <= 0:
            raise serializers.ValidationError(_("Le montant doit être supérieur à 0."))
        return value

    def validate(self, attrs):
        """
        Validate that the montant doesn't exceed the remaining amount to pay.
        Also validate that facture_client has an allowed status.
        """
        facture_client = attrs.get("facture_client")
        montant = attrs.get("montant")

        if facture_client:
            # Validate facture status
            if facture_client.statut not in ALLOWED_FACTURE_STATUSES:
                raise serializers.ValidationError(
                    {
                        "facture_client": _(
                            "Impossible d'ajouter un règlement pour une facture avec le statut '%(status)s'. "
                            "Statuts autorisés: %(allowed)s."
                        )
                        % {
                            "status": facture_client.statut,
                            "allowed": ", ".join(ALLOWED_FACTURE_STATUSES),
                        }
                    }
                )

            if montant:
                reste_a_payer = Reglement.get_reste_a_payer(facture_client)

                if montant > reste_a_payer:
                    devise = facture_client.devise
                    raise serializers.ValidationError(
                        {
                            "montant": _(
                                "Le montant (%(montant)s %(devise)s) dépasse le reste à payer (%(reste)s %(devise)s) "
                                "pour cette facture."
                            )
                            % {
                                "montant": montant,
                                "devise": devise,
                                "reste": reste_a_payer,
                            }
                        }
                    )

        return attrs


class ReglementUpdateSerializer(ReglementClientNameMixin, serializers.ModelSerializer):
    """Serializer for updating règlements with montant validation."""

    client_name = serializers.SerializerMethodField()
    facture_client_numero = serializers.CharField(
        source="facture_client.numero_facture",
        read_only=True,
    )
    mode_reglement_name = serializers.CharField(
        source="mode_reglement.nom",
        read_only=True,
    )

    # Financial fields for response
    montant_facture = serializers.SerializerMethodField()
    total_reglements_facture = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()

    class Meta:
        model = Reglement
        fields = [
            "id",
            "facture_client",
            "facture_client_numero",
            "client_name",
            "mode_reglement",
            "mode_reglement_name",
            "libelle",
            "observations",
            "montant",
            "date_reglement",
            "date_echeance",
            "statut",
            "date_created",
            "date_updated",
            # Financial fields
            "montant_facture",
            "total_reglements_facture",
            "reste_a_payer",
        ]
        read_only_fields = [
            "id",
            "statut",
            "date_created",
            "date_updated",
            "montant_facture",
            "total_reglements_facture",
            "reste_a_payer",
        ]

    @staticmethod
    def get_montant_facture(obj) -> Decimal:
        """Return the total amount of the associated invoice."""
        return obj.facture_client.total_ttc_apres_remise

    @staticmethod
    def get_total_reglements_facture(obj) -> Decimal:
        """Return the total of all valid règlements for the associated invoice."""
        return Reglement.get_total_reglements_for_facture(obj.facture_client_id)

    @staticmethod
    def get_reste_a_payer(obj) -> Decimal:
        """Return the remaining amount to pay for the associated invoice."""
        return Reglement.get_reste_a_payer(obj.facture_client)

    @staticmethod
    def validate_montant(value):
        """Validate that montant is positive."""
        if value <= 0:
            raise serializers.ValidationError(_("Le montant doit être supérieur à 0."))
        return value

    def validate(self, attrs):
        """
        Validate that the montant doesn't exceed the remaining amount to pay.
        When updating, we need to exclude the current reglement from the calculation.
        Also validate that facture_client has an allowed status.
        """
        # Get facture_client from data or instance
        facture_client = attrs.get(
            "facture_client", self.instance.facture_client if self.instance else None
        )
        montant = attrs.get("montant", self.instance.montant if self.instance else None)

        if facture_client:
            # Validate facture status
            if facture_client.statut not in ALLOWED_FACTURE_STATUSES:
                raise serializers.ValidationError(
                    {
                        "facture_client": _(
                            "Impossible de modifier un règlement pour une facture avec le statut '%(status)s'. "
                            "Statuts autorisés: %(allowed)s."
                        )
                        % {
                            "status": facture_client.statut,
                            "allowed": ", ".join(ALLOWED_FACTURE_STATUSES),
                        }
                    }
                )

            if montant:
                # Exclude current reglement from calculation when updating
                exclude_id = self.instance.id if self.instance else None
                reste_a_payer = Reglement.get_reste_a_payer(facture_client, exclude_id)

                if montant > reste_a_payer:
                    devise = facture_client.devise
                    raise serializers.ValidationError(
                        {
                            "montant": _(
                                "Le montant (%(montant)s %(devise)s) dépasse le reste à payer (%(reste)s %(devise)s) "
                                "pour cette facture."
                            )
                            % {
                                "montant": montant,
                                "devise": devise,
                                "reste": reste_a_payer,
                            }
                        }
                    )

        return attrs
