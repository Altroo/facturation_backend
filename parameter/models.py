from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Ville(models.Model):
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="villes",
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de cette ville"),
    )
    nom = models.CharField(
        max_length=100,
        verbose_name=_("Nom de la ville"),
        help_text=_("Nom de la ville"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Ville"), verbose_name_plural=_("Historiques Villes")
    )

    class Meta:
        verbose_name = _("Ville")
        verbose_name_plural = _("Villes")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de ce mode de paiement"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom du mode de paiement"),
        help_text=_("Nom du mode de paiement (ex: Espèces, Virement)"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Mode de paiement"),
        verbose_name_plural=_("Historiques Modes de paiement"),
    )

    class Meta:
        verbose_name = _("Mode de paiement")
        verbose_name_plural = _("Modes de paiement")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de cette marque"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom de la marque"),
        help_text=_("Nom de la marque"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Marque"), verbose_name_plural=_("Historiques Marques")
    )

    class Meta:
        verbose_name = _("Marque")
        verbose_name_plural = _("Marques")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de cette catégorie"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom de la catégorie"),
        help_text=_("Nom de la catégorie"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Catégorie"),
        verbose_name_plural=_("Historiques Catégories"),
    )

    class Meta:
        verbose_name = _("Catégorie")
        verbose_name_plural = _("Catégories")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de cette unité"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom de l'unité"),
        help_text=_("Nom de l'unité (ex: pièce, kg)"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Unité"), verbose_name_plural=_("Historiques Unités")
    )

    class Meta:
        verbose_name = _("Unité")
        verbose_name_plural = _("Unités")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de cet emplacement"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom de l'emplacement"),
        help_text=_("Nom de l'emplacement (ex: Entrepôt A)"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Emplacement"),
        verbose_name_plural=_("Historiques Emplacements"),
    )

    class Meta:
        verbose_name = _("Emplacement")
        verbose_name_plural = _("Emplacements")
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
        verbose_name=_("Société"),
        help_text=_("Société propriétaire de ce livreur"),
    )
    nom = models.CharField(
        max_length=255,
        verbose_name=_("Nom du livreur"),
        help_text=_("Nom du livreur"),
    )

    history = HistoricalRecords(
        verbose_name=_("Historique Livré par"), verbose_name_plural=_("Historiques Livré par")
    )

    class Meta:
        verbose_name = _("Livré par")
        verbose_name_plural = _("Livré par")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nom"],
                name="unique_livre_par_per_company",
            ),
        ]

    def __str__(self):
        return self.nom
