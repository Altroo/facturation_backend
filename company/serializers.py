from rest_framework import serializers

from .models import Company


class CompanySerializer(serializers.ModelSerializer):
    date_created = serializers.DateTimeField(format="%d/%m/%Y")

    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ("date_created",)
