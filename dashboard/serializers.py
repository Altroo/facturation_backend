from rest_framework import serializers

from .models import MonthlyObjectives


class MonthlyObjectivesSerializer(serializers.ModelSerializer):
    """Serializer for MonthlyObjectives model."""

    class Meta:
        model = MonthlyObjectives
        fields = [
            "id",
            "company",
            "objectif_ca",
            "objectif_factures",
            "objectif_conversion",
            "date_created",
            "date_updated",
        ]
        read_only_fields = ["id", "date_created", "date_updated"]
