from rest_framework import serializers

from .models import (
    Incoterm,
    OrigineMarchandise,
    NatureMarchandise,
    Ville,
    Marque,
    Categorie,
    Unite,
    Emplacement,
    ModePaiement,
    LivrePar,
)


class IncotermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incoterm
        fields = ("id", "nom", "company")

    def validate(self, attrs):
        company = attrs.get("company", getattr(self.instance, "company", None))
        name = attrs.get("nom", getattr(self.instance, "nom", ""))
        if (
            self.Meta.model.objects.filter(company=company, nom__iexact=name)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError(
                {"nom": "Cette valeur existe déjà pour cette société."}
            )
        return attrs


class OrigineMarchandiseSerializer(IncotermSerializer):
    class Meta(IncotermSerializer.Meta):
        model = OrigineMarchandise


class NatureMarchandiseSerializer(IncotermSerializer):
    class Meta(IncotermSerializer.Meta):
        model = NatureMarchandise


class VilleSerializer(serializers.ModelSerializer):
    """Serializer for Ville (id, nom, company)."""

    class Meta:
        model = Ville
        fields = ("id", "nom", "company")


class MarqueSerializer(serializers.ModelSerializer):
    """Company brand directory, including the supplier contact address."""

    class Meta:
        model = Marque
        fields = ("id", "nom", "email", "company")


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
