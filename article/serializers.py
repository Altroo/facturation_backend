from base64 import b64decode
from decimal import Decimal
from functools import cached_property
from os import remove
from pathlib import Path
from typing import cast

from django.core.files import File
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.request import Request

from company.models import Company
from facturation_backend.utils import ImageProcessor
from parameter.models import Marque, Categorie, Unite, Emplacement
from stock.models import StockBalance
from stock.services import (
    ZERO,
    ArticleStockSnapshot,
    article_stock_snapshot,
    evaluate_low_stock,
)
from .models import Article


class ArticleBaseSerializer(serializers.ModelSerializer):
    """Common fields and validation for all article serializers."""

    # Handle photo as a string field (for base64 or URLs)
    photo = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    stock_management_enabled = serializers.SerializerMethodField()
    physical_quantity = serializers.SerializerMethodField()
    reserved_quantity = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()
    incoming_quantity = serializers.SerializerMethodField()
    projected_quantity = serializers.SerializerMethodField()
    stock_state = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id",
            "reference",
            "designation",
            "type_article",
            "company",
            "marque",
            "categorie",
            "emplacement",
            "unite",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "devise_prix_vente",
            "tva",
            "stock_minimum",
            "remarque",
            "photo",
            "archived",
            "date_created",
            "date_updated",
            "stock_management_enabled",
            "physical_quantity",
            "reserved_quantity",
            "available_quantity",
            "incoming_quantity",
            "projected_quantity",
            "stock_state",
        ]
        read_only_fields = [
            "id",
            "date_created",
            "date_updated",
            "stock_management_enabled",
            "physical_quantity",
            "reserved_quantity",
            "available_quantity",
            "incoming_quantity",
            "projected_quantity",
            "stock_state",
        ]

    @cached_property
    def stock_snapshots(self) -> dict[int, ArticleStockSnapshot]:
        configured = self.context.get("stock_snapshots")
        if isinstance(configured, dict):
            return configured.copy()
        return {}

    def _stock_value(self, instance: Article, key: str):
        snapshot = self.stock_snapshots.get(instance.pk)
        if snapshot is None:
            snapshot = article_stock_snapshot(instance)
            self.stock_snapshots[instance.pk] = snapshot
        values = cast(dict[str, Decimal | bool | str], snapshot)
        return values[key]

    def get_stock_management_enabled(self, instance):
        return self._stock_value(instance, "stock_management_enabled")

    def get_physical_quantity(self, instance):
        return self._stock_value(instance, "physical_quantity")

    def get_reserved_quantity(self, instance):
        return self._stock_value(instance, "reserved_quantity")

    def get_available_quantity(self, instance):
        return self._stock_value(instance, "available_quantity")

    def get_incoming_quantity(self, instance):
        return self._stock_value(instance, "incoming_quantity")

    def get_projected_quantity(self, instance):
        return self._stock_value(instance, "projected_quantity")

    def get_stock_state(self, instance):
        return self._stock_value(instance, "stock_state")

    def validate(self, attrs):
        errors = {}
        required = {
            "reference": "Référence",
            "designation": "Désignation",
            "company": "Société",
        }
        for field, label in required.items():
            if not attrs.get(field) and not (
                self.instance and getattr(self.instance, field)
            ):
                errors[field] = _("%(label)s est obligatoire.") % {"label": label}
        stock_minimum = attrs.get(
            "stock_minimum", getattr(self.instance, "stock_minimum", 0)
        )
        if stock_minimum is not None and stock_minimum < 0:
            errors["stock_minimum"] = _("Le stock minimum ne peut pas être négatif.")
        company: Company | None = attrs.get("company") or getattr(
            self.instance, "company", None
        )
        emplacement: Emplacement | None = attrs.get(
            "emplacement", getattr(self.instance, "emplacement", None)
        )
        type_article = attrs.get(
            "type_article", getattr(self.instance, "type_article", "")
        )
        if (
            emplacement is not None
            and company is not None
            and emplacement.company_id != company.id
        ):
            errors["emplacement"] = _(
                "L'emplacement doit appartenir à la société de l'article."
            )
        if (
            company is not None
            and company.stock_management_enabled
            and (type_article or "").lower() == "produit"
            and not emplacement
        ):
            errors["emplacement"] = _(
                "Un emplacement est requis pour un produit géré en stock."
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @staticmethod
    def _process_image_field(
        field_name: str, validated_data, instance: Article | None
    ) -> File | None:
        """
        Process image field - handle base64, multipart files, and existing URLs, convert to WebP
        """
        field_value = validated_data.get(field_name)
        if not field_value:
            # If empty/null, clear the field
            return None
        # If it's a URL (existing image), don't change it
        if isinstance(field_value, str) and field_value.startswith("http"):
            # Return the existing file instance, don't update
            return getattr(instance, field_name) if instance else None
        # If it's a multipart file upload (InMemoryUploadedFile or TemporaryUploadedFile)
        if hasattr(field_value, "read"):
            uploaded_file = cast(File, field_value)
            try:
                # Read the file content
                uploaded_file.seek(0)  # Reset pointer to start
                data = uploaded_file.read()
                # Convert to WebP (pass as bytes)
                return ImageProcessor.convert_to_webp(data)
            except Exception as e:
                raise serializers.ValidationError(
                    _("Invalid file upload for %(field_name)s: %(error)s")
                    % {"field_name": field_name, "error": str(e)}
                )
        # If it's base64 data, process it
        if isinstance(field_value, str) and field_value.startswith("data:image"):
            try:
                # Extract format and base64 data
                format_, imgstr = field_value.split(";base64,")
                # Decode base64
                data = b64decode(imgstr)
                # Convert to WebP
                return ImageProcessor.convert_to_webp(data)
            except Exception as e:
                raise serializers.ValidationError(
                    _("Invalid base64 image data for %(field_name)s: %(error)s")
                    % {"field_name": field_name, "error": str(e)}
                )
        # If we get here, it's an unexpected format
        raise serializers.ValidationError(
            _("Invalid image format for %(field_name)s") % {"field_name": field_name}
        )

    def to_representation(self, instance):
        """
        Convert photo field to URL for output
        """
        representation = super().to_representation(instance)
        request: Request | None = self.context.get("request")

        # Convert photo field to full URL
        if instance.photo:
            if request is not None:
                representation["photo"] = request.build_absolute_uri(instance.photo.url)
            else:
                representation["photo"] = instance.photo.url
        else:
            representation["photo"] = None

        return representation


class ArticleSerializer(ArticleBaseSerializer):
    """Used for creation (POST) and full update (PUT)."""

    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    marque = serializers.PrimaryKeyRelatedField(
        queryset=Marque.objects.all(), required=False, allow_null=True
    )
    categorie = serializers.PrimaryKeyRelatedField(
        queryset=Categorie.objects.all(), required=False, allow_null=True
    )
    emplacement = serializers.PrimaryKeyRelatedField(
        queryset=Emplacement.objects.all(), required=False, allow_null=True
    )
    unite = serializers.PrimaryKeyRelatedField(
        queryset=Unite.objects.all(), required=False, allow_null=True
    )

    def create(self, validated_data) -> Article:
        # Process photo field
        photo = self._process_image_field("photo", validated_data, None)

        # Remove from validated_data (we'll set it directly)
        validated_data.pop("photo", None)

        # Create instance without saving yet
        instance = Article(**validated_data)

        # Set photo field
        if photo is not None:
            self._save_photo(instance, photo)

        # Save once - creates only one history entry as "created"
        instance.save()
        self._ensure_stock_balance(instance)
        return instance

    def update(self, instance: Article, validated_data) -> Article:
        # Process photo field
        photo = self._process_image_field("photo", validated_data, instance)

        # Detect explicit null and delete both file and reference
        if "photo" in validated_data and validated_data["photo"] is None:
            field = getattr(instance, "photo")
            if field:  # Only if there's an existing file
                try:
                    # Delete physical file from disk
                    if field.path and Path(field.path).exists():
                        remove(field.path)
                except (ValueError, FileNotFoundError, OSError):
                    # Log error but continue
                    pass
                # Delete database reference
                field.delete(save=False)
            setattr(instance, "photo", None)

        # Remove photo key from validated_data
        validated_data.pop("photo", None)

        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update photo field - also delete old file when replacing
        if photo is not None:
            old_field = instance.photo
            if photo != old_field:
                # Delete old file before saving new one
                if old_field:
                    try:
                        if old_field.path and Path(old_field.path).exists():
                            remove(old_field.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                # Save new file
                self._save_photo(instance, cast(File, photo))

        instance.save()
        self._ensure_stock_balance(instance)
        return instance

    @staticmethod
    def _save_photo(instance: Article, photo: File) -> None:
        instance.photo.save(photo.name or "article.webp", photo, save=False)

    @staticmethod
    def _ensure_stock_balance(instance):
        if (
            instance.company.stock_management_enabled
            and (instance.type_article or "").lower() == "produit"
            and instance.emplacement_id
        ):
            balance = StockBalance.objects.get_or_create(
                company=instance.company,
                article=instance,
                emplacement=instance.emplacement,
                defaults={"physical_quantity": ZERO, "reserved_quantity": ZERO},
            )[0]
            evaluate_low_stock(balance.pk)


class ArticleDetailSerializer(ArticleSerializer):
    """Read‑only view for retrieve (GET)."""

    company_name = serializers.ReadOnlyField(source="company.raison_sociale")
    marque_name = serializers.ReadOnlyField(source="marque.nom")
    categorie_name = serializers.ReadOnlyField(source="categorie.nom")
    emplacement_name = serializers.ReadOnlyField(source="emplacement.nom")
    unite_name = serializers.ReadOnlyField(source="unite.nom")

    class Meta(ArticleSerializer.Meta):
        fields = ArticleSerializer.Meta.fields + [
            "company_name",
            "marque_name",
            "categorie_name",
            "emplacement_name",
            "unite_name",
        ]
        read_only_fields = ArticleSerializer.Meta.read_only_fields + [
            "company_name",
            "marque_name",
            "categorie_name",
            "emplacement_name",
            "unite_name",
            "archived",
        ]


class ArticleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view."""

    type_article = serializers.SerializerMethodField()
    company_name = serializers.ReadOnlyField(source="company.raison_sociale")
    marque_name = serializers.ReadOnlyField(source="marque.nom")
    categorie_name = serializers.ReadOnlyField(source="categorie.nom")
    emplacement_name = serializers.ReadOnlyField(source="emplacement.nom")
    unite_name = serializers.ReadOnlyField(source="unite.nom")
    stock_management_enabled = serializers.SerializerMethodField()
    physical_quantity = serializers.SerializerMethodField()
    reserved_quantity = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()
    incoming_quantity = serializers.SerializerMethodField()
    projected_quantity = serializers.SerializerMethodField()
    stock_state = serializers.SerializerMethodField()

    @staticmethod
    def get_type_article(instance):
        return instance.get_type_article_display() if instance.type_article else None

    class Meta:
        model = Article
        fields = [
            "id",
            "reference",
            "designation",
            "type_article",
            "company",
            "company_name",
            "marque",
            "marque_name",
            "categorie",
            "categorie_name",
            "emplacement",
            "emplacement_name",
            "unite",
            "unite_name",
            "prix_achat",
            "devise_prix_achat",
            "prix_vente",
            "devise_prix_vente",
            "photo",
            "tva",
            "stock_minimum",
            "remarque",
            "archived",
            "date_created",
            "stock_management_enabled",
            "physical_quantity",
            "reserved_quantity",
            "available_quantity",
            "incoming_quantity",
            "projected_quantity",
            "stock_state",
        ]
        read_only_fields = [
            "company_name",
            "marque_name",
            "categorie_name",
            "emplacement_name",
            "unite_name",
            "stock_management_enabled",
            "physical_quantity",
            "reserved_quantity",
            "available_quantity",
            "incoming_quantity",
            "projected_quantity",
            "stock_state",
        ]

    @cached_property
    def stock_snapshots(self) -> dict[int, ArticleStockSnapshot]:
        configured = self.context.get("stock_snapshots")
        if isinstance(configured, dict):
            return configured.copy()
        return {}

    def _stock_value(self, instance: Article, key: str):
        snapshot = self.stock_snapshots.get(instance.pk)
        if snapshot is None:
            snapshot = article_stock_snapshot(instance)
            self.stock_snapshots[instance.pk] = snapshot
        values = cast(dict[str, Decimal | bool | str], snapshot)
        return values[key]

    def get_stock_management_enabled(self, instance):
        return self._stock_value(instance, "stock_management_enabled")

    def get_physical_quantity(self, instance):
        return self._stock_value(instance, "physical_quantity")

    def get_reserved_quantity(self, instance):
        return self._stock_value(instance, "reserved_quantity")

    def get_available_quantity(self, instance):
        return self._stock_value(instance, "available_quantity")

    def get_incoming_quantity(self, instance):
        return self._stock_value(instance, "incoming_quantity")

    def get_projected_quantity(self, instance):
        return self._stock_value(instance, "projected_quantity")

    def get_stock_state(self, instance):
        return self._stock_value(instance, "stock_state")

    def to_representation(self, instance):
        """
        Convert photo field to URL for output
        """
        representation = super().to_representation(instance)
        request: Request | None = self.context.get("request")

        # Convert photo field to full URL
        if instance.photo:
            if request is not None:
                representation["photo"] = request.build_absolute_uri(instance.photo.url)
            else:
                representation["photo"] = instance.photo.url
        else:
            representation["photo"] = None

        return representation
