from base64 import b64decode
from io import BytesIO
from os import remove
from pathlib import Path
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from company.models import Company
from company.serializers import MembershipCompanySerializer
from facturation_backend.utils import ImageProcessor
from .models import CustomUser, Membership, Role


class MembershipSerializer(serializers.ModelSerializer):
    """Serializer for a single membership entry sent by the frontend."""

    # ID of the existing membership (optional for creates)
    membership_id = serializers.IntegerField(source="id", required=False)

    # Company is sent as an integer id
    company_id = serializers.IntegerField(write_only=True)

    # Role is sent as a string (e.g. "Caissier")
    role = serializers.CharField(write_only=True)

    # Returned for read‑only purposes
    raison_sociale = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Membership
        fields = ["membership_id", "company_id", "role", "raison_sociale"]

    def to_representation(self, instance):
        """Handle None company gracefully."""
        representation = super().to_representation(instance)

        # Handle None company
        if instance.company is None:
            representation["raison_sociale"] = None

        return representation

    @staticmethod
    def _get_role(role_name: str) -> Role:
        """Return the Role instance matching the supplied name."""
        try:
            return Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            raise serializers.ValidationError(f"The role '{role_name}' does not exist.")

    def create(self, validated_data):
        user = self.context["user"]
        company_id = validated_data.pop("company_id")
        role_name = validated_data.pop("role")

        # Check for existing membership
        existing = Membership.objects.filter(user=user, company_id=company_id).first()

        if existing:
            raise serializers.ValidationError(
                f"L'utilisateur a déjà une adhésion pour la société {company_id}"
            )

        # Validate role exists
        role = self._get_role(role_name)

        # Validate company exists
        try:
            company = Company.objects.get(pk=company_id)
        except Company.DoesNotExist:
            raise serializers.ValidationError(
                f"The company {company_id} does not exist."
            )

        return Membership.objects.create(
            user=user, company=company, role=role, **validated_data
        )

    def update(self, instance, validated_data):
        user = self.context["user"]
        if "company_id" in validated_data:
            new_company_id = validated_data.pop("company_id")

            # Check for duplicate when changing company
            existing = (
                Membership.objects.filter(user=user, company_id=new_company_id)
                .exclude(pk=instance.pk)
                .first()
            )

            if existing:
                raise serializers.ValidationError(
                    f"L'utilisateur a déjà une adhésion pour la société {new_company_id}"
                )

            instance.company = Company.objects.get(pk=new_company_id)

        if "role" in validated_data:
            role_name = validated_data.pop("role")
            instance.role = self._get_role(role_name)

        instance.save()
        return instance


class CreateAccountSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    avatar_cropped = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    gender = serializers.CharField(required=False, allow_blank=True)

    # Accept memberships (companies) on create
    companies = MembershipSerializer(
        many=True,
        required=False,
        source="memberships",  # alias to the related name on CustomUser
    )

    @staticmethod
    def validate_gender(value):
        """Convert gender display value to code"""
        if not value:
            return ""
        if value == "Homme":
            return "H"
        elif value == "Femme":
            return "F"
        else:
            raise serializers.ValidationError(
                f"Valeur du sexe invalide : {value}. Doit être 'Homme' ou 'Femme'."
            )

    @staticmethod
    def _create_memberships(user, items):
        """
        Create Membership objects from a list of dicts.
        Items with a falsy ``membership_id`` (e.g. 0) are treated as new.
        """
        ctx = {"user": user}  # Pass the newly created user, not the request
        for item in items:
            # Drop a zero/false membership_id so the serializer creates a new one
            if not item.get("membership_id"):
                item.pop("membership_id", None)

            serializer = MembershipSerializer(data=item, context=ctx)
            serializer.is_valid(raise_exception=True)
            serializer.save()

    @staticmethod
    def _process_image_field(field_name, validated_data):
        """
        Process image field - handle base64, multipart files, and convert to WebP
        """
        field_value = validated_data.get(field_name)
        if not field_value:
            # If empty/null, clear the field
            return None
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
                # Validate format before splitting
                if ";base64," not in field_value:
                    raise serializers.ValidationError(
                        f"Format d'image base64 invalide pour {field_name}"
                    )

                # Use maxsplit=1 to handle edge cases
                parts = field_value.split(";base64,", 1)
                if len(parts) != 2:
                    raise serializers.ValidationError(
                        f"Données base64 mal formées pour {field_name}"
                    )

                format_, imgstr = parts

                # Validate MIME type
                if not format_.startswith("data:image/"):
                    raise serializers.ValidationError(
                        f"Type MIME d'image invalide pour {field_name}"
                    )

                # Validate base64 size before decoding (15MB limit)
                max_base64_length = getattr(settings, 'MAX_BASE64_IMAGE_SIZE', 15 * 1024 * 1024)
                if len(imgstr) > max_base64_length:
                    raise serializers.ValidationError(
                        f"Image trop grande pour {field_name}: {len(imgstr)} octets (max {max_base64_length}). "
                        "Veuillez télécharger une image plus petite."
                    )

                # Decode base64
                try:
                    data = b64decode(imgstr)
                except Exception as decode_error:
                    raise serializers.ValidationError(
                        f"Encodage base64 invalide pour {field_name}: {str(decode_error)}"
                    )

                # Convert to WebP (pass as bytes)
                return ImageProcessor.convert_to_webp(data)

            except serializers.ValidationError:
                raise  # Re-raise validation errors
            except Exception as e:
                raise serializers.ValidationError(
                    f"Données d'image base64 invalides pour {field_name}: {str(e)}"
                )
        # If we get here, it's an unexpected format
        raise serializers.ValidationError(f"Format d'image invalide pour {field_name}")

    def create(self, validated_data):
        # Extract the companies/memberships payload
        memberships_data = validated_data.pop("memberships", None)

        # Extract and hash the password
        password = validated_data.pop("password", None)

        # Process avatar fields
        avatar = self._process_image_field("avatar", validated_data)
        avatar_cropped = self._process_image_field("avatar_cropped", validated_data)
        validated_data.pop("avatar", None)
        validated_data.pop("avatar_cropped", None)

        # Create the user instance without saving yet
        instance = CustomUser(**validated_data)

        # Set the hashed password
        if password:
            instance.set_password(password)

        if avatar:
            instance.avatar.save(avatar.name, avatar, save=False)
        if avatar_cropped:
            instance.avatar_cropped.save(
                avatar_cropped.name, avatar_cropped, save=False
            )

        # Save once - creates only one history entry as "created"
        instance.save()

        # Create memberships (companies) if any were sent
        if memberships_data:
            self._create_memberships(instance, memberships_data)

        return instance

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "gender",
            "avatar",
            "avatar_cropped",
            "is_staff",
            "is_active",
            "default_password_set",
            "companies",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "default_password_set": {"default": False},
        }

    def to_representation(self, instance):
        """
        Convert image fields to URLs for output
        """
        representation = super().to_representation(instance)
        request = self.context.get("request")

        # Convert image fields to full URLs
        for field in ["avatar", "avatar_cropped"]:
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


class ChangePasswordSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        pass

    def create(self, validated_data):
        pass

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    @staticmethod
    def validate_new_password(value):
        validate_password(value)
        return value


class PasswordResetSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        pass

    def create(self, validated_data):
        pass

    new_password = serializers.CharField(required=True)
    new_password2 = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs.get("new_password") != attrs.get("new_password2"):
            raise serializers.ValidationError(
                {"new_password2": "Les mots de passe ne correspondent pas."}
            )
        return attrs


class UserEmailSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255)

    class Meta:
        model = CustomUser
        fields = ["email"]
        extra_kwargs = {"email": {"write_only": True}}


class ProfileGETSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="get_absolute_avatar_img")
    avatar_cropped = serializers.CharField(source="get_absolute_avatar_cropped_img")
    gender = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format="%d/%m/%Y")

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.get_gender_display()
        return None

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "gender",
            "avatar",
            "avatar_cropped",
            "is_staff",
            "default_password_set",
            "date_joined",
            "last_login",
        ]


class ProfilePutSerializer(serializers.ModelSerializer):
    # Handle avatar as CharField to accept both base64 and URLs
    avatar = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    avatar_cropped = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    # Accept gender as display value, we'll convert it
    gender = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "gender", "avatar", "avatar_cropped"]

    @staticmethod
    def validate_gender(value):
        """Convert gender display value to code"""
        if not value:
            return ""
        if value == "Homme":
            return "H"
        elif value == "Femme":
            return "F"
        else:
            raise serializers.ValidationError(
                f"Valeur du sexe invalide : {value}. Doit être 'Homme' ou 'Femme'."
            )

    @staticmethod
    def _process_image_field(field_name, validated_data):
        field_value = validated_data.get(field_name)
        if not field_value:
            return None, None, False

        # Existing URL – do not modify the field
        if isinstance(field_value, str) and field_value.startswith("http"):
            return None, None, True

        # Multipart upload
        if hasattr(field_value, "read"):
            try:
                field_value.seek(0)
                data = field_value.read()
                field_value.seek(0)
                # Convert to WebP
                webp_file = ImageProcessor.convert_to_webp(data)
                # Return WebP file and original bytes for Celery processing
                return webp_file, BytesIO(data), False
            except Exception as e:
                raise serializers.ValidationError(
                    f"Invalid file upload for {field_name}: {str(e)}"
                )

        # Base64 data
        if isinstance(field_value, str) and field_value.startswith("data:image"):
            try:
                # Validate format before splitting
                if ";base64," not in field_value:
                    raise serializers.ValidationError(
                        f"Format d'image base64 invalide pour {field_name}"
                    )

                # Use maxsplit=1 to handle edge cases
                parts = field_value.split(";base64,", 1)
                if len(parts) != 2:
                    raise serializers.ValidationError(
                        f"Données base64 mal formées pour {field_name}"
                    )

                format_, imgstr = parts

                # Validate MIME type
                if not format_.startswith("data:image/"):
                    raise serializers.ValidationError(
                        f"Type MIME d'image invalide pour {field_name}"
                    )

                # Validate base64 size before decoding (15MB limit)
                max_base64_length = getattr(settings, 'MAX_BASE64_IMAGE_SIZE', 15 * 1024 * 1024)
                if len(imgstr) > max_base64_length:
                    raise serializers.ValidationError(
                        f"Image trop grande pour {field_name}: {len(imgstr)} octets (max {max_base64_length}). "
                        "Veuillez télécharger une image plus petite."
                    )

                # Decode base64
                try:
                    data = b64decode(imgstr)
                except Exception as decode_error:
                    raise serializers.ValidationError(
                        f"Encodage base64 invalide pour {field_name}: {str(decode_error)}"
                    )

                # Convert to WebP
                webp_file = ImageProcessor.convert_to_webp(data)
                # Return WebP file and original bytes for Celery processing
                return webp_file, BytesIO(data), False

            except serializers.ValidationError:
                raise  # Re-raise validation errors
            except Exception as e:
                raise serializers.ValidationError(
                    f"Données d'image base64 invalides pour {field_name}: {str(e)}"
                )

        raise serializers.ValidationError(f"Format d'image invalide pour {field_name}")

    def update(self, instance, validated_data):
        """Handle avatar/avatar_cropped upload and removal."""
        avatar_file = None
        avatar_cropped_file = None
        avatar_bytes = None
        old_avatar = instance.avatar
        old_avatar_cropped = instance.avatar_cropped

        # ----- Avatar handling -------------------------------------------------
        if "avatar" in validated_data:
            avatar_file, avatar_bytes, is_url = self._process_image_field(
                "avatar", validated_data
            )
            # Explicit null or empty string → remove both files
            if validated_data["avatar"] is None or validated_data["avatar"] == "":
                instance.avatar = None
                instance.avatar_cropped = None
            # New file (not a URL) → replace old avatar and clear cropped
            elif avatar_file:
                instance.avatar = avatar_file
                # When new avatar is uploaded, clear the old cropped version
                # since it's tied to the old avatar
                instance.avatar_cropped = None
            # is_url=True → existing URL, preserve as-is (no change to instance fields)
        # ----- Avatar cropped handling ----------------------------------------
        if "avatar_cropped" in validated_data:
            avatar_cropped_file, _, is_url = self._process_image_field(
                "avatar_cropped", validated_data
            )
            # Explicit null or empty string → clear cropped
            if (
                validated_data["avatar_cropped"] is None
                or validated_data["avatar_cropped"] == ""
            ):
                instance.avatar_cropped = None
            # New file (not a URL) → replace old cropped avatar
            elif avatar_cropped_file:
                instance.avatar_cropped = avatar_cropped_file
            # is_url=True → existing URL, preserve as-is
        # Remove processed fields from validated_data
        validated_data.pop("avatar", None)
        validated_data.pop("avatar_cropped", None)
        # ----- Other fields ----------------------------------------------------
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        # Store bytes for Celery only when a new avatar file was provided
        instance._avatar_bytes_for_celery = avatar_bytes if avatar_file else None
        # Save first, then delete old files (avoid data loss if save fails)
        instance.save()
        # Now safely delete old files after successful save
        if "avatar" in validated_data:
            if avatar_file and old_avatar:
                self._delete_file(old_avatar)
            if avatar_file and old_avatar_cropped:
                # New avatar uploaded, so old cropped is orphaned
                self._delete_file(old_avatar_cropped)
            if (
                validated_data.get("avatar") is None
                or validated_data.get("avatar") == ""
            ) and old_avatar:
                self._delete_file(old_avatar)
                if old_avatar_cropped:
                    self._delete_file(old_avatar_cropped)

        if "avatar_cropped" in validated_data:
            if avatar_cropped_file and old_avatar_cropped:
                self._delete_file(old_avatar_cropped)
            if (
                validated_data.get("avatar_cropped") is None
                or validated_data.get("avatar_cropped") == ""
            ) and old_avatar_cropped:
                self._delete_file(old_avatar_cropped)

        return instance

    @staticmethod
    def _delete_file(field):
        """Remove the file from storage and delete the model field."""
        try:
            if field.path and Path(field.path).exists():
                remove(field.path)
        except (ValueError, FileNotFoundError, OSError):
            pass
        field.delete(save=False)

    def to_representation(self, instance):
        """Convert avatar to URL for output"""
        representation = super().to_representation(instance)
        request = self.context.get("request")
        # Convert avatar fields to full URLs
        for field in ["avatar", "avatar_cropped"]:
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


class UsersListSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="get_absolute_avatar_img")
    avatar_cropped = serializers.CharField(source="get_absolute_avatar_cropped_img")
    gender = serializers.SerializerMethodField()

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.get_gender_display()
        return None

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "avatar",
            "avatar_cropped",
            "email",
            "gender",
            "is_active",
            "is_staff",
            "date_joined",
            "date_updated",
            "last_login",
        ]
        read_only_fields = ("date_joined", "date_updated", "last_login")


class UserDetailSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="get_absolute_avatar_img")
    avatar_cropped = serializers.CharField(source="get_absolute_avatar_cropped_img")
    gender = serializers.SerializerMethodField()

    companies = MembershipCompanySerializer(
        source="memberships",
        many=True,
        read_only=True,
    )

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.get_gender_display()
        return None

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "avatar",
            "avatar_cropped",
            "email",
            "gender",
            "is_active",
            "is_staff",
            "date_joined",
            "date_updated",
            "last_login",
            "companies",
        ]
        read_only_fields = ("id", "date_joined", "date_updated", "last_login")


class UserPatchSerializer(ProfilePutSerializer):
    memberships = MembershipSerializer(many=True, required=False)
    companies = MembershipSerializer(many=True, required=False)

    class Meta(ProfilePutSerializer.Meta):
        model = CustomUser
        fields = ProfilePutSerializer.Meta.fields + [
            "id",
            "email",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
            "companies",
            "memberships",
        ]
        read_only_fields = ("id", "email", "date_joined", "last_login")

    @staticmethod
    def _process_membership_items(instance, items):
        """
        Create / update Membership objects from a list of dicts.
        Returns a set of membership IDs that were processed (created or updated).
        """
        ctx = {"user": instance}
        processed_ids = set()

        for item in items:
            # Validate required fields
            if not item.get("company_id"):
                raise serializers.ValidationError(
                    "company_id est requis pour chaque adhésion"
                )
            if not item.get("role"):
                raise serializers.ValidationError(
                    "role est requis pour chaque adhésion"
                )

            # Try to locate an existing membership:
            membership = None
            if item.get("membership_id"):
                try:
                    membership = Membership.objects.get(
                        id=item["membership_id"], user=instance
                    )
                except Membership.DoesNotExist:
                    membership = None
            if not membership and item.get("company_id"):
                try:
                    membership = Membership.objects.get(
                        company_id=item["company_id"], user=instance
                    )
                except Membership.DoesNotExist:
                    membership = None

            if membership:
                # Existing → update
                serializer = MembershipSerializer(
                    membership, data=item, context=ctx, partial=True
                )
                serializer.is_valid(raise_exception=True)
                updated = serializer.save()
                processed_ids.add(updated.id)
            else:
                # New → create
                serializer = MembershipSerializer(data=item, context=ctx)
                serializer.is_valid(raise_exception=True)
                created = serializer.save()
                processed_ids.add(created.id)

        return processed_ids

    def update(self, instance, validated_data):
        memberships_data = validated_data.pop("memberships", None)
        companies_data = validated_data.pop("companies", None)

        # Prevent users from modifying their own memberships (unless admin)
        request = self.context.get("request")
        if request:
            request_user = request.user
            if instance.pk != request_user.pk and not request_user.is_staff:
                raise PermissionDenied(
                    "Vous ne pouvez pas modifier les memberships d'autres utilisateurs."
                )

        # Update basic profile fields (avatar, gender, …)
        instance = super().update(instance, validated_data)

        incoming = memberships_data if memberships_data is not None else companies_data
        if incoming is not None:
            kept_ids = self._process_membership_items(instance, incoming)
            # Remove memberships that were not sent back
            Membership.objects.filter(user=instance).exclude(id__in=kept_ids).delete()

        return instance
