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
        fields = ("id", "first_name", "last_name", "role")
        read_only_fields = fields


class CompanySerializer(serializers.ModelSerializer):
    date_created = serializers.DateTimeField(format="%d/%m/%Y", read_only=True)

    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ("date_created",)


class CompanyDetailSerializer(CompanySerializer):
    # All admin memberships for the company
    managed_by = MembershipUserSerializer(
        source="memberships",
        many=True,
        read_only=True,
    )

    class Meta(CompanySerializer.Meta):
        fields = "__all__"
