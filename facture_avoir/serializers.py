from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from client.models import Client
from core.serializers import (
    BaseCreateSerializer,
    BaseDetailUpdateSerializer,
    BaseLineWriteSerializer,
    BaseListSerializer,
    validate_line_currency,
    update_document_devise_on_first_line,
)
from facture_client.models import FactureClient
from .models import AVOIR_ACTIVE_STATUSES, FactureAvoir, FactureAvoirLine


class FactureAvoirListSerializer(BaseListSerializer):
    facture_origine_numero = serializers.CharField(
        source="facture_origine.numero_facture", read_only=True
    )
    facture_origine_date = serializers.DateField(
        source="facture_origine.date_facture", read_only=True
    )
    motif_avoir_label = serializers.CharField(
        source="get_motif_avoir_display", read_only=True
    )

    class Meta:
        model = FactureAvoir
        fields = [
            "id",
            "numero_avoir",
            "company",
            "client",
            "client_name",
            "date_avoir",
            "facture_origine",
            "facture_origine_numero",
            "facture_origine_date",
            "motif_avoir",
            "motif_avoir_label",
            "mode_paiement",
            "mode_paiement_name",
            "numero_bon_commande_client",
            "fournisseur",
            "fournisseur_email",
            "statut",
            "remarque",
            "created_by_user",
            "created_by_user_name",
            "lignes_count",
            "remise_type",
            "remise",
            "total_ht",
            "total_tva",
            "total_ttc",
            "total_ttc_apres_remise",
            "devise",
        ]
        read_only_fields = fields


class FactureAvoirLineWriteSerializer(BaseLineWriteSerializer):
    class Meta:
        model = FactureAvoirLine
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


class FactureAvoirLineSerializer(serializers.ModelSerializer):
    facture_avoir = serializers.PrimaryKeyRelatedField(
        queryset=FactureAvoir.objects.all()
    )
    designation = serializers.CharField(source="article.designation", read_only=True)
    reference = serializers.CharField(source="article.reference", read_only=True)

    def validate(self, attrs):
        validate_line_currency(attrs, self.instance, "facture_avoir")
        return attrs

    def create(self, validated_data):
        facture_avoir = validated_data.get("facture_avoir")
        devise_prix_vente = validated_data.get("devise_prix_vente", "MAD")
        update_document_devise_on_first_line(facture_avoir, devise_prix_vente)
        return super().create(validated_data)

    class Meta:
        model = FactureAvoirLine
        fields = [
            "id",
            "facture_avoir",
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


class FactureAvoirSerializer(BaseCreateSerializer):
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), required=False
    )
    facture_origine = serializers.PrimaryKeyRelatedField(
        queryset=FactureClient.objects.all(), required=False, allow_null=True
    )
    facture_origine_numero = serializers.CharField(
        source="facture_origine.numero_facture", read_only=True
    )
    facture_origine_date = serializers.DateField(
        source="facture_origine.date_facture", read_only=True
    )
    motif_avoir_label = serializers.CharField(
        source="get_motif_avoir_display", read_only=True
    )
    lignes = FactureAvoirLineWriteSerializer(many=True, write_only=True, required=False)

    def get_numero_field_name(self):
        return "numero_avoir"

    def get_line_model_class(self):
        return FactureAvoirLine

    def get_line_relation_field(self):
        return "facture_avoir"

    def get_line_serializer_class(self):
        return FactureAvoirLineSerializer

    def validate(self, data):
        data = super().validate(data)
        facture_origine = data.get("facture_origine")
        client = data.get("client")

        if facture_origine:
            if client and client.id != facture_origine.client_id:
                raise serializers.ValidationError(
                    {"client": _("Le client doit correspondre à la facture d'origine.")}
                )
            data["client"] = facture_origine.client
            data["mode_paiement"] = (
                data.get("mode_paiement") or facture_origine.mode_paiement
            )
            data["devise"] = data.get("devise") or facture_origine.devise
            if not self.instance:
                data["fournisseur"] = facture_origine.fournisseur
                data["fournisseur_email"] = facture_origine.fournisseur_email
        elif not self.instance:
            raise serializers.ValidationError(
                {"facture_origine": _("Une facture d'origine est requise.")}
            )
        elif not client:
            raise serializers.ValidationError(
                {"client": _("Un client est requis pour un avoir libre.")}
            )

        self._validate_origin_quantities(data)
        return data

    def _validate_origin_quantities(self, data):
        facture_origine = data.get("facture_origine") or getattr(
            self.instance, "facture_origine", None
        )
        if not facture_origine:
            return

        lines_data = data.get("lignes")
        if lines_data is None:
            return

        origin_quantities: dict[int, Decimal] = {}
        for line in facture_origine.lignes.all():
            origin_quantities[line.article_id] = (
                origin_quantities.get(line.article_id, Decimal("0")) + line.quantity
            )

        already_credited = (
            FactureAvoirLine.objects.filter(
                facture_avoir__facture_origine=facture_origine,
                facture_avoir__statut__in=AVOIR_ACTIVE_STATUSES,
            )
            .exclude(facture_avoir_id=getattr(self.instance, "id", None))
            .values("article_id")
            .annotate(quantity=Sum("quantity"))
        )
        credited_quantities = {
            item["article_id"]: item["quantity"] or Decimal("0")
            for item in already_credited
        }

        incoming_quantities: dict[int, Decimal] = {}
        for line in lines_data:
            article = line.get("article")
            article_id = getattr(article, "id", article)
            quantity = Decimal(str(line.get("quantity") or 0))
            incoming_quantities[article_id] = (
                incoming_quantities.get(article_id, Decimal("0")) + quantity
            )

        for article_id, incoming_quantity in incoming_quantities.items():
            allowed = origin_quantities.get(article_id, Decimal("0"))
            used = credited_quantities.get(article_id, Decimal("0"))
            if allowed <= 0:
                raise serializers.ValidationError(
                    {
                        "lignes": _(
                            "Une ligne d'avoir n'existe pas dans la facture d'origine."
                        )
                    }
                )
            if used + incoming_quantity > allowed:
                raise serializers.ValidationError(
                    {
                        "lignes": _(
                            "La quantité créditée dépasse la quantité de la facture d'origine."
                        )
                    }
                )

    class Meta:
        model = FactureAvoir
        fields = [
            "id",
            "numero_avoir",
            "company",
            "client",
            "client_name",
            "date_avoir",
            "facture_origine",
            "facture_origine_numero",
            "facture_origine_date",
            "motif_avoir",
            "motif_avoir_label",
            "numero_bon_commande_client",
            "fournisseur",
            "fournisseur_email",
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
            "numero_avoir",
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


class FactureAvoirDetailSerializer(BaseDetailUpdateSerializer, FactureAvoirSerializer):
    lignes = FactureAvoirLineWriteSerializer(many=True, write_only=True, required=False)

    def validate(self, data):
        if self.instance and self.instance.statut != "Brouillon":
            raise serializers.ValidationError(
                _("Seuls les avoirs en brouillon peuvent être modifiés.")
            )
        if self.instance and "facture_origine" in data:
            new_origin = data.get("facture_origine")
            current_origin_id = self.instance.facture_origine_id
            new_origin_id = getattr(new_origin, "id", None)
            if new_origin_id != current_origin_id:
                raise serializers.ValidationError(
                    {"facture_origine": _("La facture d'origine n'est pas modifiable.")}
                )
        if self.instance and self.instance.facture_origine_id:
            errors = {}
            for field in ("fournisseur", "fournisseur_email"):
                if field not in data:
                    continue
                incoming = str(data.get(field) or "").strip()
                current = str(getattr(self.instance, field) or "").strip()
                if incoming != current:
                    errors[field] = _(
                        "Cette information est héritée de la facture d'origine et n'est pas modifiable."
                    )
            if errors:
                raise serializers.ValidationError(errors)
        return super().validate(data)

    class Meta(FactureAvoirSerializer.Meta):
        read_only_fields = FactureAvoirSerializer.Meta.read_only_fields + [
            "facture_origine_numero",
            "facture_origine_date",
        ]
