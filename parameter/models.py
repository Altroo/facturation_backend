from django.db import models


class Ville(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom de la ville", unique=True)

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"

    def __str__(self):
        return self.nom
