from rest_framework import serializers

from .models import Ville


class VilleSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Ville
        fields = ("id", "nom")
