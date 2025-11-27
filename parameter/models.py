from django.db import models


class Ville(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom de la ville", unique=True)

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"

    def __str__(self):
        return self.nom


# class ModePaiement(models.Model):
#     nom = models.CharField(
#         max_length=255, unique=True, verbose_name="Nom du mode de paiement"
#     )
#
#     class Meta:
#         verbose_name = "Mode de paiement"
#         verbose_name_plural = "Modes de paiement"
#
#     def __str__(self):
#         return self.nom


class Marque(models.Model):
    nom = models.CharField(max_length=255, unique=True, verbose_name="Nom de la marque")

    class Meta:
        verbose_name = "Marque"
        verbose_name_plural = "Marques"

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    nom = models.CharField(
        max_length=255, unique=True, verbose_name="Nom de la catégorie"
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.nom


class Unite(models.Model):
    nom = models.CharField(max_length=255, unique=True, verbose_name="Nom de l'unité")

    class Meta:
        verbose_name = "Unité"
        verbose_name_plural = "Unités"

    def __str__(self):
        return self.nom


# class ModeReglement(models.Model):
#     nom = models.CharField(
#         max_length=255, unique=True, verbose_name="Nom du mode de règlement"
#     )
#
#     class Meta:
#         verbose_name = "Mode de règlement"
#         verbose_name_plural = "Modes de règlement"
#
#     def __str__(self):
#         return self.nom


class Emplacement(models.Model):
    nom = models.CharField(
        max_length=255, unique=True, verbose_name="Nom de l'emplacement"
    )

    class Meta:
        verbose_name = "Emplacement"
        verbose_name_plural = "Emplacements"

    def __str__(self):
        return self.nom
