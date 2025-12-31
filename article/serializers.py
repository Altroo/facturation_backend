from base64 import b64decode
from os import remove
from pathlib import Path

from rest_framework import serializers

from company.models import Company
from facturation_backend.utils import ImageProcessor
from parameter.models import Marque, Categorie, Unite, Emplacement
from .models import Article


class ArticleBaseSerializer(serializers.ModelSerializer):
    """Common fields and validation for all article serializers."""

    # Handle photo as a string field (for base64 or URLs)
    photo = serializers.CharField(required=False, allow_null=True, allow_blank=True)

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
            "prix_vente",
            "tva",
            "remarque",
            "photo",
            "archived",
            "date_created",
        ]
        read_only_fields = ["id", "date_created"]

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
                errors[field] = f"{label} est obligatoire."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @staticmethod
    def _process_image_field(field_name, validated_data, instance):
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
            try:
                # Read the file content
                field_value.seek(0)  # Reset pointer to start
                data = field_value.read()
                # Convert to WebP (pass as bytes)
                return ImageProcessor.convert_to_webp(data)
            except Exception as e:
                raise serializers.ValidationError(
                    f"Invalid file upload for {field_name}: {str(e)}"
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
                    f"Invalid base64 image data for {field_name}: {str(e)}"
                )
        # If we get here, it's an unexpected format
        raise serializers.ValidationError(f"Invalid image format for {field_name}")

    def to_representation(self, instance):
        """
        Convert photo field to URL for output
        """
        representation = super().to_representation(instance)
        request = self.context.get("request")

        # Convert photo field to full URL
        if instance.photo:
            if request:
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

    def create(self, validated_data):
        # Process photo field
        photo = self._process_image_field("photo", validated_data, None)

        # Remove from validated_data (we'll set it directly)
        validated_data.pop("photo", None)

        # Create instance
        instance = Article.objects.create(**validated_data)

        # Set photo field
        if photo:
            instance.photo.save(photo.name, photo, save=False)

        instance.save()
        return instance

    def update(self, instance, validated_data):
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
        if photo and photo != getattr(instance, "photo"):
            old_field = getattr(instance, "photo")
            # Delete old file before saving new one
            if old_field:
                try:
                    if old_field.path and Path(old_field.path).exists():
                        remove(old_field.path)
                except (ValueError, FileNotFoundError, OSError):
                    pass
            # Save new file
            getattr(instance, "photo").save(photo.name, photo, save=False)

        instance.save()
        return instance


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
            "prix_vente",
            "photo",
            "tva",
            "remarque",
            "archived",
            "date_created",
        ]
        read_only_fields = [
            "company_name",
            "marque_name",
            "categorie_name",
            "emplacement_name",
            "unite_name",
        ]

    def to_representation(self, instance):
        """
        Convert photo field to URL for output
        """
        representation = super().to_representation(instance)
        request = self.context.get("request")

        # Convert photo field to full URL
        if instance.photo:
            if request:
                representation["photo"] = request.build_absolute_uri(instance.photo.url)
            else:
                representation["photo"] = instance.photo.url
        else:
            representation["photo"] = None

        return representation
