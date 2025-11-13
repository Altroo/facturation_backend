from base64 import b64decode
from io import BytesIO
from os import remove
from pathlib import Path
from uuid import uuid4

from django.contrib.auth.password_validation import validate_password
from django.core.files.base import ContentFile
from rest_framework import serializers

from .models import CustomUser


class CreateAccountSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={"input_type": "password"}, write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "gender",
            "is_staff",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def save(self):
        account = CustomUser(
            email=self.validated_data["email"],
            first_name=self.validated_data["first_name"],
            last_name=self.validated_data["last_name"],
            gender=self.validated_data["gender"],
            is_staff=self.validated_data["is_staff"],
        )
        account.set_password(self.validated_data["password"])
        account.save()
        return account


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
    gender = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format="%d/%m/%Y")

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.gender
        return None

    class Meta:
        model = CustomUser
        fields = ["id", "first_name", "last_name", "gender", "avatar", "date_joined"]


class ProfilePutSerializer(serializers.ModelSerializer):
    # Handle avatar as CharField to accept both base64 and URLs
    avatar = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    avatar_thumbnail = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    # Accept gender as display value, we'll convert it
    gender = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "gender", "avatar", "avatar_thumbnail"]

    @staticmethod
    def validate_gender(value):
        """Convert gender display value to code"""
        if value == "Homme":
            return "H"
        elif value == "Femme":
            return "F"
        return ""

    @staticmethod
    def _process_image_field(field_name, validated_data, instance):
        """
        Process image field - handle base64, multipart files, and existing URLs
        Returns: (file_content, avatar_bytes_for_celery)
        """
        field_value = validated_data.get(field_name)
        if not field_value:
            # If empty/null, clear the field
            return None, None
        # If it's a URL (existing image), don't change it
        if isinstance(field_value, str) and field_value.startswith("http"):
            # Return the existing file instance, don't update
            return getattr(instance, field_name) if instance else None, None
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
                # Return both ContentFile and BytesIO for Celery
                return ContentFile(data, name=filename), BytesIO(data)
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
                # Return both ContentFile and BytesIO for Celery
                return ContentFile(data, name=filename), BytesIO(data)
            except Exception as e:
                raise serializers.ValidationError(
                    f"Invalid base64 image data for {field_name}: {str(e)}"
                )
        # If we get here, it's an unexpected format
        raise serializers.ValidationError(f"Invalid image format for {field_name}")

    def update(self, instance, validated_data):
        """Handle avatar upload and update profile fields"""
        # Process avatar field
        # avatar_file = None
        avatar_bytes = None
        if "avatar" in validated_data:
            avatar_file, avatar_bytes = self._process_image_field(
                "avatar", validated_data, instance
            )
            # If we have a new avatar file, cleanup old files
            if avatar_file and avatar_file != getattr(instance, "avatar"):
                # Delete old avatar
                if instance.avatar:
                    try:
                        if instance.avatar.path and Path(instance.avatar.path).exists():
                            remove(instance.avatar.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                    instance.avatar.delete(save=False)
                # Delete old thumbnail
                if instance.avatar_thumbnail:
                    try:
                        if (
                            instance.avatar_thumbnail.path
                            and Path(instance.avatar_thumbnail.path).exists()
                        ):
                            remove(instance.avatar_thumbnail.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                    instance.avatar_thumbnail.delete(save=False)
            # Handle explicit null (user wants to remove avatar)
            elif validated_data["avatar"] is None:
                if instance.avatar:
                    try:
                        if instance.avatar.path and Path(instance.avatar.path).exists():
                            remove(instance.avatar.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                    instance.avatar.delete(save=False)
                if instance.avatar_thumbnail:
                    try:
                        if (
                            instance.avatar_thumbnail.path
                            and Path(instance.avatar_thumbnail.path).exists()
                        ):
                            remove(instance.avatar_thumbnail.path)
                    except (ValueError, FileNotFoundError, OSError):
                        pass
                    instance.avatar_thumbnail.delete(save=False)
            # Remove avatar from validated_data
            validated_data.pop("avatar", None)
            validated_data.pop("avatar_thumbnail", None)
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        # Store avatar_bytes on instance for Celery task (temporary attribute)
        instance._avatar_bytes_for_celery = avatar_bytes
        return instance

    def to_representation(self, instance):
        """Convert avatar to URL for output"""
        representation = super().to_representation(instance)
        request = self.context.get("request")
        # Convert avatar to full URL
        if instance.avatar:
            if request:
                representation["avatar"] = request.build_absolute_uri(
                    instance.avatar.url
                )
            else:
                representation["avatar"] = instance.avatar.url
        else:
            representation["avatar"] = (
                instance.get_absolute_avatar_img
                if hasattr(instance, "get_absolute_avatar_img")
                else None
            )
        # Remove avatar_thumbnail from output (internal field)
        representation.pop("avatar_thumbnail", None)
        return representation


class UsersListSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="get_absolute_avatar_img")
    avatar_thumbnail = serializers.CharField(source="get_absolute_avatar_thumbnail_img")
    gender = serializers.SerializerMethodField()

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.gender
        return None

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "avatar",
            "avatar_thumbnail",
            "email",
            "gender",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ("date_joined", "last_login")


class UserDetailSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source="get_absolute_avatar_img")
    avatar_thumbnail = serializers.CharField(source="get_absolute_avatar_thumbnail_img")
    gender = serializers.SerializerMethodField()

    @staticmethod
    def get_gender(instance):
        if instance.gender != "":
            return instance.gender
        return None

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "avatar",
            "avatar_thumbnail",
            "email",
            "gender",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ("id", "date_joined", "last_login")


class UserPatchSerializer(ProfilePutSerializer):
    class Meta:
        model = CustomUser
        fields = [
            "id",
            "first_name",
            "last_name",
            "avatar",
            "avatar_thumbnail",
            "email",
            "gender",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ("id", "email", "date_joined", "last_login")
