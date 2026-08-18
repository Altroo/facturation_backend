from re import match

from django.db import transaction
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


def _fill_blank_supplier_snapshot(document, supplier, supplier_email):
    """Fill only missing snapshot values on an already converted document."""
    updated_fields = []
    if supplier and not (document.fournisseur or "").strip():
        document.fournisseur = supplier
        updated_fields.append("fournisseur")
    if supplier_email and not (document.fournisseur_email or "").strip():
        document.fournisseur_email = supplier_email
        updated_fields.append("fournisseur_email")
    if updated_fields:
        document.save(update_fields=[*updated_fields, "date_updated"])


def _backfill_blank_descendant_supplier_snapshots(
    proforma, supplier, supplier_email
):
    """Remediate legacy conversions made before supplier data was entered."""
    from bon_de_livraison.models import BonDeLivraison
    from facture_avoir.models import FactureAvoir
    from facture_client.models import FactureClient

    factures = FactureClient.objects.select_for_update().filter(
        source_proforma=proforma
    )
    for facture in factures:
        _fill_blank_supplier_snapshot(facture, supplier, supplier_email)
        for bon_livraison in BonDeLivraison.objects.select_for_update().filter(
            source_facture_client=facture
        ):
            _fill_blank_supplier_snapshot(
                bon_livraison, supplier, supplier_email
            )
        for avoir in FactureAvoir.objects.select_for_update().filter(
            facture_origine=facture
        ):
            _fill_blank_supplier_snapshot(avoir, supplier, supplier_email)


class FactureProformaListSerializer(BaseListSerializer):
    """List serializer for FactureProForma with totals as decimals."""

    converted_facture_client = serializers.SerializerMethodField()
    converted_facture_client_numero = serializers.SerializerMethodField()
    source_devis = serializers.IntegerField(source="source_devis_id", read_only=True)
    source_devis_numero = serializers.CharField(
        source="source_devis.numero_devis", read_only=True
    )
    has_logistics_dossier = serializers.SerializerMethodField()

    @staticmethod
    def get_has_logistics_dossier(obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get(
            "logistique_links"
        )
        if prefetched is not None:
            return bool(prefetched)
        return obj.logistique_links.exists()

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
            "fournisseur",
            "fournisseur_email",
            "has_logistics_dossier",
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
            "fournisseur",
            "fournisseur_email",
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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        supplier = str(attrs.get("fournisseur", self.instance.fournisseur) or "").strip()
        supplier_email = str(
            attrs.get("fournisseur_email", self.instance.fournisseur_email) or ""
        ).strip()
        effective_status = attrs.get("statut", self.instance.statut)
        if effective_status == "Accepté" and not supplier:
            raise serializers.ValidationError(
                {
                    "fournisseur": _(
                        "Renseignez le fournisseur de la commande client validée."
                    )
                }
            )
        if (
            self.instance.logistique_links.exists()
            and "fournisseur" in attrs
            and (self.instance.fournisseur or "").strip()
            and supplier != (self.instance.fournisseur or "").strip()
        ):
            raise serializers.ValidationError(
                {
                    "fournisseur": _(
                        "Le fournisseur ne peut plus être modifié après la création du dossier logistique."
                    )
                }
            )
        attrs["fournisseur"] = supplier
        attrs["fournisseur_email"] = supplier_email
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        previous_supplier = (instance.fournisseur or "").strip()
        previous_supplier_email = (instance.fournisseur_email or "").strip()
        supplier = str(validated_data.get("fournisseur", previous_supplier) or "").strip()
        supplier_email = str(
            validated_data.get("fournisseur_email", previous_supplier_email) or ""
        ).strip()
        linked_order_ids = []
        if (not previous_supplier and supplier) or supplier_email != previous_supplier_email:
            linked_order_ids = list(
                instance.logistique_links.values_list("commande_id", flat=True)
            )

        instance = super().update(instance, validated_data)

        if (not previous_supplier and supplier) or (
            not previous_supplier_email and supplier_email
        ):
            _backfill_blank_descendant_supplier_snapshots(
                instance, supplier, supplier_email
            )

        if linked_order_ids:
            from logistique.models import LogisticsOrder

            request = self.context.get("request")
            for order in LogisticsOrder.objects.filter(id__in=linked_order_ids):
                old_supplier = order.fournisseur
                old_supplier_email = order.fournisseur_email
                updated_fields = []
                if old_supplier != supplier:
                    order.fournisseur = supplier
                    updated_fields.append("fournisseur")
                if old_supplier_email != supplier_email:
                    order.fournisseur_email = supplier_email
                    updated_fields.append("fournisseur_email")
                if updated_fields:
                    order.save(update_fields=[*updated_fields, "date_updated"])
                if old_supplier != supplier:
                    order.add_event(
                        user=getattr(request, "user", None),
                        action="Correction fournisseur source",
                        old_value=old_supplier,
                        new_value=supplier,
                        note=_(
                            "Fournisseur repris depuis la commande client source régularisée."
                        ),
                    )
                if old_supplier_email != supplier_email:
                    order.add_event(
                        user=getattr(request, "user", None),
                        action="Correction e-mail fournisseur source",
                        old_value=old_supplier_email,
                        new_value=supplier_email,
                        note=_(
                            "Adresse de livraison des justificatifs reprise depuis la commande client source."
                        ),
                    )

        return instance

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
