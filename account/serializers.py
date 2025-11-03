from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import CustomUser


class CreateAccountSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = CustomUser
        fields = ['email', 'password', 'password2', 'first_name', 'last_name', 'gender',
                  'is_staff', 'is_superuser']
        extra_kwargs = {
           'password': {'write_only': True},
        }

    def save(self):
        account = CustomUser(
            email=self.validated_data['email'],
            first_name=self.validated_data['first_name'],
            last_name=self.validated_data['last_name'],
            gender=self.validated_data['gender'],
            is_staff=self.validated_data['is_staff'],
            is_superuser=self.validated_data['is_superuser'],
        )
        account.set_password(self.validated_data['password'])
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
            raise serializers.ValidationError({"new_password2": "Les mots de passe ne correspondent pas."})
        return attrs


class UserEmailSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=255)

    class Meta:
        model = CustomUser
        fields = ['email']
        extra_kwargs = {
            'email': {'write_only': True}
        }


class ProfileGETSerializer(serializers.ModelSerializer):
    avatar = serializers.CharField(source='get_absolute_avatar_img')
    gender = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format='%d/%m/%Y')

    @staticmethod
    def get_gender(instance):
        if instance.gender != '':
            return instance.gender
        return None

    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name',
                  'gender', 'avatar', 'date_joined']


class ProfilePutSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'gender']
