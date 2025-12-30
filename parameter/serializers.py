from rest_framework import serializers

from .models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    ModeReglement,
    LivrePar,
)


class VilleSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Ville
        fields = ("id", "nom")


class MarqueSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Marque
        fields = ("id", "nom")


class CategorieSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Categorie
        fields = ("id", "nom")


class UniteSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Unite
        fields = ("id", "nom")


class EmplacementSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = Emplacement
        fields = ("id", "nom")


class ModePaiementSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = ModePaiement
        fields = ("id", "nom")


class ModeRegelementSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = ModeReglement
        fields = ("id", "nom")


class LivreParSerializer(serializers.ModelSerializer):
    """Serializer for the flat list view (id and name only)."""

    class Meta:
        model = LivrePar
        fields = ("id", "nom")
