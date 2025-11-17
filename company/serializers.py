from base64 import b64decode
from os import remove
from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from rest_framework import serializers

from account.models import Membership
from .models import Company


class MembershipUserSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="user.id", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "first_name", "last_name", "role"]
        read_only_fields = fields


class MembershipCompanySerializer(serializers.ModelSerializer):
    membership_id = serializers.IntegerField(source="pk", read_only=True)
    company_id = serializers.IntegerField(source="company.pk", read_only=True)
    raison_sociale = serializers.CharField(
        source="company.raison_sociale", read_only=True
    )
    role = serializers.CharField(read_only=True)

    class Meta:
        model = Membership
        fields = ["membership_id", "company_id", "raison_sociale", "role"]
        read_only_fields = fields


class CompanyListSerializer(serializers.ModelSerializer):
    # Return absolute URLs for the image fields
    logo = serializers.SerializerMethodField()
    cachet = serializers.SerializerMethodField()

    def get_logo(self, obj):
        request = self.context.get("request")
        if not obj.logo:
            return None
        url = obj.logo.url
        return request.build_absolute_uri(url) if request else url

    def get_cachet(self, obj):
        request = self.context.get("request")
        if not obj.cachet:
            return None
        url = obj.cachet.url
        return request.build_absolute_uri(url) if request else url

    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ["date_created"]


class CompanySerializer(serializers.ModelSerializer):
    date_created = serializers.DateTimeField(format="%d/%m/%Y", read_only=True)

    # Change these to regular fields, we'll handle the logic ourselves
    logo = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    cachet = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    logo_cropped = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    cachet_cropped = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )

    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ["date_created"]

    @staticmethod
    def _process_image_field(field_name, validated_data, instance):
        """
        Process image field - handle base64, multipart files, and existing URLs
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
                field_value.seek(0)  # Reset again for potential reuse
                # Get extension from content_type or name
                ext = (
                    field_value.name.split(".")[-1]
                    if "." in field_value.name
                    else "jpg"
                )
                # Create a unique filename
                filename = f"{uuid4()}.{ext}"
                # Return ContentFile
                return ContentFile(data, name=filename)
            except Exception as e:
                raise serializers.ValidationError(
                    f"Invalid file upload for {field_name}: {str(e)}"
                )
        # If it's base64 data, process it
        if isinstance(field_value, str) and field_value.startswith("data:image"):
            try:
                # Extract format and base64 data
                format_, imgstr = field_value.split(";base64,")
                ext = format_.split("/")[-1]  # Get extension (png, jpg, etc.)
                # Decode base64
                data = b64decode(imgstr)
                # Create a unique filename
                filename = f"{uuid4()}.{ext}"
                # Return ContentFile
                return ContentFile(data, name=filename)
            except Exception as e:
                raise serializers.ValidationError(
                    f"Invalid base64 image data for {field_name}: {str(e)}"
                )
        # If we get here, it's an unexpected format
        raise serializers.ValidationError(f"Invalid image format for {field_name}")

    def create(self, validated_data):
        # Process image fields
        logo = self._process_image_field("logo", validated_data, None)
        logo_cropped = self._process_image_field("logo_cropped", validated_data, None)
        cachet = self._process_image_field("cachet", validated_data, None)
        cachet_cropped = self._process_image_field(
            "cachet_cropped", validated_data, None
        )

        # Remove from validated_data (we'll set them directly)
        validated_data.pop("logo", None)
        validated_data.pop("logo_cropped", None)
        validated_data.pop("cachet", None)
        validated_data.pop("cachet_cropped", None)

        # Create instance
        instance = Company.objects.create(**validated_data)

        # Set image fields
        if logo:
            instance.logo.save(logo.name, logo, save=False)
        if logo_cropped:
            instance.logo_cropped.save(logo_cropped.name, logo_cropped, save=False)
        if cachet:
            instance.cachet.save(cachet.name, cachet, save=False)
        if cachet_cropped:
            instance.cachet_cropped.save(
                cachet_cropped.name, cachet_cropped, save=False
            )

        instance.save()
        return instance

    def update(self, instance, validated_data):
        # Process image fields
        logo = self._process_image_field("logo", validated_data, instance)
        logo_cropped = self._process_image_field(
            "logo_cropped", validated_data, instance
        )
        cachet = self._process_image_field("cachet", validated_data, instance)
        cachet_cropped = self._process_image_field(
            "cachet_cropped", validated_data, instance
        )

        # Detect explicit nulls and delete both file and reference
        for field_name in ("logo", "logo_cropped", "cachet", "cachet_cropped"):
            if field_name in validated_data and validated_data[field_name] is None:
                field = getattr(instance, field_name)
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
                setattr(instance, field_name, None)

        # Remove image keys from validated_data
        validated_data.pop("logo", None)
        validated_data.pop("logo_cropped", None)
        validated_data.pop("cachet", None)
        validated_data.pop("cachet_cropped", None)

        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update image fields - also delete old files when replacing
        for field_name, new_file in [
            ("logo", logo),
            ("logo_cropped", logo_cropped),
            ("cachet", cachet),
            ("cachet_cropped", cachet_cropped),
        ]:
            if new_file and new_file != getattr(instance, field_name):
                old_field = getattr(instance, field_name)
                # Delete old file before saving new one
                if old_field:
                    try:
                        if old_field.path and Path(old_field.path).exists():
                            remove(old_field.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                # Save new file
                getattr(instance, field_name).save(new_file.name, new_file, save=False)

        instance.save()
        return instance

    def to_representation(self, instance):
        """
        Convert image fields to URLs for output
        """
        representation = super().to_representation(instance)
        request = self.context.get("request")

        # Convert image fields to full URLs
        for field in ["logo", "logo_cropped", "cachet", "cachet_cropped"]:
            if getattr(instance, field):
                if request:
                    representation[field] = request.build_absolute_uri(
                        getattr(instance, field).url
                    )
                else:
                    representation[field] = getattr(instance, field).url
            else:
                representation[field] = None

        return representation


class ManagedByItemSerializer(serializers.Serializer):
    pk = serializers.IntegerField()
    role = serializers.CharField()

    class Meta:
        fields = ["pk", "role"]


class CompanyDetailSerializer(CompanySerializer):
    # Write‑only list of {pk, role} objects
    managed_by = ManagedByItemSerializer(many=True, write_only=True, required=False)

    # Read‑only detailed admin list (kept for backward compatibility)
    admins = MembershipUserSerializer(
        source="memberships",
        many=True,
        read_only=True,
    )

    class Meta(CompanySerializer.Meta):
        fields = "__all__"

    @staticmethod
    def update_memberships(company, items):
        """
        Replace the company's memberships with the supplied list of
        {'pk': user_id, 'role': role_name} dictionaries.
        """
        # Remove all existing memberships for this company
        Membership.objects.filter(company=company).delete()

        for item in items:
            user_id = item["pk"]
            role_name = item["role"]
            try:
                role_group = Group.objects.get(name=role_name)
            except Group.DoesNotExist:
                raise serializers.ValidationError(f"Rôle '{role_name}' n'existe pas.")
            Membership.objects.create(
                company=company,
                user_id=user_id,
                role=role_group,
            )

    def update(self, instance, validated_data):
        # Extract the writable field before delegating to the parent update
        managed_items = validated_data.pop("managed_by", None)

        # Perform the standard update (including image handling)
        instance = super().update(instance, validated_data)

        # Sync memberships if the client supplied a list
        if managed_items is not None:
            self.update_memberships(instance, managed_items)

        return instance

    def to_representation(self, instance):
        """
        Output `managed_by` as a list of {pk, role} objects and keep
        the detailed admin objects under `admins`.
        """
        representation = super().to_representation(instance)

        # Build the list of {pk, role}
        representation["managed_by"] = [
            {"pk": m.user.id, "role": m.role.name}
            for m in instance.memberships.select_related("user", "role")
        ]

        # Preserve detailed admin objects under `admins`
        representation["admins"] = representation.pop("admins", [])
        return representation
