from rest_framework import serializers

from .models import (
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)


class VilleSerializer(serializers.ModelSerializer):
    """Serializer for Ville (id, nom, company)."""

    class Meta:
        model = Ville
        fields = ("id", "nom", "company")


class MarqueSerializer(serializers.ModelSerializer):
    """Serializer for Marque (id, nom, company)."""

    class Meta:
        model = Marque
        fields = ("id", "nom", "company")


class CategorieSerializer(serializers.ModelSerializer):
    """Serializer for Categorie (id, nom, company)."""

    class Meta:
        model = Categorie
        fields = ("id", "nom", "company")


class UniteSerializer(serializers.ModelSerializer):
    """Serializer for Unite (id, nom, company)."""

    class Meta:
        model = Unite
        fields = ("id", "nom", "company")


class EmplacementSerializer(serializers.ModelSerializer):
    """Serializer for Emplacement (id, nom, company)."""

    class Meta:
        model = Emplacement
        fields = ("id", "nom", "company")


class ModePaiementSerializer(serializers.ModelSerializer):
    """Serializer for ModePaiement (id, nom, company)."""

    class Meta:
        model = ModePaiement
        fields = ("id", "nom", "company")


class LivreParSerializer(serializers.ModelSerializer):
    """Serializer for LivrePar (id, nom, company)."""

    class Meta:
        model = LivrePar
        fields = ("id", "nom", "company")
