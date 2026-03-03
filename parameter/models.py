from django.db import models
from simple_history.models import HistoricalRecords


class Ville(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="villes",
        verbose_name="Société",
        help_text="Société propriétaire de cette ville",
    )
    nom = models.CharField(
        max_length=100,
        verbose_name="Nom de la ville",
        help_text="Nom de la ville",
    )

    history = HistoricalRecords(
        verbose_name="Historique Ville", verbose_name_plural="Historiques Villes"
    )

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_ville_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class ModePaiement(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="modes_paiement",
        verbose_name="Société",
        help_text="Société propriétaire de ce mode de paiement",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom du mode de paiement",
        help_text="Nom du mode de paiement (ex: Espèces, Virement)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Mode de paiement",
        verbose_name_plural="Historiques Modes de paiement",
    )

    class Meta:
        verbose_name = "Mode de paiement"
        verbose_name_plural = "Modes de paiement"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_mode_paiement_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class Marque(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="marques",
        verbose_name="Société",
        help_text="Société propriétaire de cette marque",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom de la marque",
        help_text="Nom de la marque",
    )

    history = HistoricalRecords(
        verbose_name="Historique Marque", verbose_name_plural="Historiques Marques"
    )

    class Meta:
        verbose_name = "Marque"
        verbose_name_plural = "Marques"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_marque_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name="Société",
        help_text="Société propriétaire de cette catégorie",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom de la catégorie",
        help_text="Nom de la catégorie",
    )

    history = HistoricalRecords(
        verbose_name="Historique Catégorie",
        verbose_name_plural="Historiques Catégories",
    )

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_categorie_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class Unite(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="unites",
        verbose_name="Société",
        help_text="Société propriétaire de cette unité",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom de l'unité",
        help_text="Nom de l'unité (ex: pièce, kg)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Unité", verbose_name_plural="Historiques Unités"
    )

    class Meta:
        verbose_name = "Unité"
        verbose_name_plural = "Unités"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_unite_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class Emplacement(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="emplacements",
        verbose_name="Société",
        help_text="Société propriétaire de cet emplacement",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom de l'emplacement",
        help_text="Nom de l'emplacement (ex: Entrepôt A)",
    )

    history = HistoricalRecords(
        verbose_name="Historique Emplacement",
        verbose_name_plural="Historiques Emplacements",
    )

    class Meta:
        verbose_name = "Emplacement"
        verbose_name_plural = "Emplacements"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_emplacement_per_company",
            ),
        ]

    def __str__(self):
        return self.nom


class LivrePar(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="livres_par",
        verbose_name="Société",
        help_text="Société propriétaire de ce livreur",
    )
    nom = models.CharField(
        max_length=255,
        verbose_name="Nom du livreur",
        help_text="Nom du livreur",
    )

    history = HistoricalRecords(
        verbose_name="Historique Livré par", verbose_name_plural="Historiques Livré par"
    )

    class Meta:
        verbose_name = "Livré par"
        verbose_name_plural = "Livré par"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_livre_par_per_company",
            ),
        ]

    def __str__(self):
        return self.nom
