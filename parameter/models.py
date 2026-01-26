from django.db import models
from simple_history.models import HistoricalRecords


class Ville(models.Model):
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de la ville",
        unique=True,
        help_text="Nom unique de la ville",
    )

    history = HistoricalRecords(
        verbose_name="Historique Ville",
        verbose_name_plural="Historiques Villes"
    )

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"

    def __str__(self):
        return self.nom


class ModePaiement(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom du mode de paiement",
        help_text="Nom unique du mode de paiement (ex: Espèces, Virement)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Mode de paiement",
        verbose_name_plural="Historiques Modes de paiement"
    )

    class Meta:
        verbose_name = "Mode de paiement"
        verbose_name_plural = "Modes de paiement"

    def __str__(self):
        return self.nom


class Marque(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de la marque",
        help_text="Nom unique de la marque",
    )

    history = HistoricalRecords(
        verbose_name="Historique Marque",
        verbose_name_plural="Historiques Marques"
    )

    class Meta:
        verbose_name = "Marque"
        verbose_name_plural = "Marques"

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de la catégorie",
        help_text="Nom unique de la catégorie",
    )

    history = HistoricalRecords(
        verbose_name="Historique Catégorie",
        verbose_name_plural="Historiques Catégories"
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.nom


class Unite(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de l'unité",
        help_text="Nom unique de l'unité (ex: pièce, kg)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Unité",
        verbose_name_plural="Historiques Unités"
    )

    class Meta:
        verbose_name = "Unité"
        verbose_name_plural = "Unités"

    def __str__(self):
        return self.nom


class Emplacement(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom de l'emplacement",
        help_text="Nom unique de l'emplacement (ex: Entrepôt A)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Emplacement",
        verbose_name_plural="Historiques Emplacements"
    )

    class Meta:
        verbose_name = "Emplacement"
        verbose_name_plural = "Emplacements"

    def __str__(self):
        return self.nom


class LivrePar(models.Model):
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nom du livreur",
        help_text="Nom unique du livreur",
    )

    history = HistoricalRecords(
        verbose_name="Historique Livré par",
        verbose_name_plural="Historiques Livré par"
    )

    class Meta:
        verbose_name = "Livré par"
        verbose_name_plural = "Livré par"

    def __str__(self):
        return self.nom
